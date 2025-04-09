from fastapi import HTTPException
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
import os
import secrets
from datetime import datetime

token_store = {}
state_map = {}

GMAIL_CLIENT_ID = os.getenv('GMAIL_CLIENT_ID')
GMAIL_CLIENT_SECRET = os.getenv('GMAIL_CLIENT_SECRET')
GMAIL_REDIRECT_URI = os.getenv('GMAIL_REDIRECT_URI')

GMAIL_SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly', 
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.modify'
    ]

def get_gmail_auth_url():
    if not GMAIL_CLIENT_ID or not GMAIL_CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="Gmail OAuth credentials not configured")
    
    state = secrets.token_urlsafe(32)
    
    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": GMAIL_CLIENT_ID,
                "client_secret": GMAIL_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [GMAIL_REDIRECT_URI] 
            }
        },
        scopes=GMAIL_SCOPES,
        redirect_uri = GMAIL_REDIRECT_URI
    )

    auth_url, _ = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        state=state,
        prompt='consent'  
    )

    state_map[state] = {
        "flow": flow
    }

    return auth_url, state

def handle_gmail_callback(code, state):
    if state not in state_map:
        raise HTTPException(status_code=400, detail="Invalid state parameter")

    flow = state_map[state]["flow"]

    flow.fetch_token(code=code)

    credentials = flow.credentials

    user_id = "default_user"

    token_store[user_id] = {
        "token_data": {
            "token": credentials.token,
            "refresh_token": credentials.refresh_token,
            "token_uri": credentials.token_uri,
            "client_id": credentials.client_id,
            "client_secret": credentials.client_secret,
            "scopes": credentials.scopes,
            "expiry": credentials.expiry.isoformat() if credentials.expiry else None
        },
        "created_at": datetime.now().isoformat()
    }

    del state_map[state]

    return user_id

def get_gmail_credentials(user_id):
    if user_id not in token_store:
        raise HTTPException(status_code=401, detail="User not authenticated with Gmail")
    
    token_data = token_store[user_id]["token_data"]

    creds = Credentials(
        token=token_data["token"],
        refresh_token=token_data["refresh_token"],
        token_uri=token_data["token_uri"],
        client_id=token_data["client_id"],
        client_secret=token_data["client_secret"],
        scopes=token_data["scopes"]
    )

    if token_data["expiry"]:
        creds.expiry = datetime.fromisoformat(token_data["expiry"])

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        
        token_store[user_id]["token_data"].update({
            "token": creds.token,
            "refresh_token": creds.refresh_token,
            "expiry": creds.expiry.isoformat() if creds.expiry else None
        })
    
    return creds

def is_authenticated(user_id):
    return user_id in token_store

def revoke_access(user_id):
    if user_id in token_store:
        del token_store[user_id]
        return True
    return False