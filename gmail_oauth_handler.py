import os
import json
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from dotenv import load_dotenv
from fastapi import HTTPException
import datetime
import os


load_dotenv()

CLIENT_SECRETS_FILE = os.getenv('CLIENT_SECRETS_FILE')
SCOPES = os.getenv('SCOPES', '').split()
if not CLIENT_SECRETS_FILE or not os.path.exists(CLIENT_SECRETS_FILE):
    raise ValueError("CLIENT_SECRETS_FILE not found or not set in .env")
if not SCOPES:
    raise ValueError("SCOPES not set in .env")

def get_flow(state=None, redirect_uri=None):
    flow = Flow.from_client_secrets_file(
            CLIENT_SECRETS_FILE,
            scopes=SCOPES,
            state=state
        )
    flow.redirect_uri = redirect_uri
    return flow

def get_gmail_auth_url(state, redirect_uri, code_challenge, code_challenge_method="S256"):
    flow = get_flow(state=state, redirect_uri=redirect_uri)
    auth_url, _ = flow.authorization_url(
        access_type='offline',  # Request refresh token
        prompt='consent',       # Force consent screen for refresh token
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method
    )
    return auth_url

def exchange_code_for_tokens(code, code_verifier, redirect_uri):
    flow = get_flow(redirect_uri=redirect_uri)
    try:
        print(f"DEBUG: Exchanging token. Code starts with: {code[:10]}, Verifier starts with: {code_verifier[:10]}") # Debug print
        flow.fetch_token(code=code, code_verifier=code_verifier)
        #flow.fetch_token(code=code)
        credentials = flow.credentials
        print("DEBUG: Token exchange with Google successful.")

        expires_in_seconds = None
        if credentials.expiry:
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            if credentials.expiry.tzinfo is None:
                time_left = credentials.expiry.replace(tzinfo=datetime.timezone.utc) - now_utc
            else:
                time_left = credentials.expiry - now_utc

            expires_in_seconds = int(time_left.total_seconds())
            if expires_in_seconds < 0:
                expires_in_seconds = 0

        token_data = {
            'access_token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'expires_in': expires_in_seconds,
            'token_type': 'Bearer',
            'scope': ' '.join(credentials.scopes) if credentials.scopes else '',
            'id_token': getattr(credentials, 'id_token', None)
        }
        print(f"DEBUG: Returning token data: access_token starts {str(token_data.get('access_token'))[:10]}, expires_in={token_data.get('expires_in')}") # Add debug print
        return token_data
    
    except Exception as e:
        print(f"ERROR during flow.fetch_token: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Failed to exchange authorization code: {str(e)}") from e

    
def revoke_access_with_token(refresh_token):
    """Revokes access using a refresh token."""
    try:
        with open(CLIENT_SECRETS_FILE, 'r') as f:
            secrets = json.load(f).get('installed', {})
        client_id = secrets.get('client_id')
        client_secret = secrets.get('client_secret')

        if not client_id or not client_secret:
             raise ValueError("Client ID or Secret not found in secrets file")

        creds = Credentials(
            token=None, 
            refresh_token=refresh_token,
            token_uri='https://oauth2.googleapis.com/token',
            client_id=client_id,
            client_secret=client_secret,
            scopes=SCOPES 
        )
        authed_session = Request()
        creds.revoke(authed_session)
        print(f"Access revoked successfully for refresh token.")
        return True
    except Exception as e:
        print(f"Error revoking access: {str(e)}")
        return False