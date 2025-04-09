from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer # Re-use for Bearer token extraction
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google.auth import exceptions as google_auth_exceptions
import os
from dotenv import load_dotenv
import json

load_dotenv()
CLIENT_SECRETS_FILE = os.getenv('CLIENT_SECRETS_FILE')

client_id = None
try:
    with open(CLIENT_SECRETS_FILE, 'r') as f:
        secrets = json.load(f).get('installed', {}) # Adjust if using 'web' type
        client_id = secrets.get('client_id')
except Exception as e:
    print(f"Warning: Could not load client_id from secrets file: {e}")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/token") 

async def verify_token(token: str = Depends(oauth2_scheme)) -> Credentials:
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    credentials = Credentials(token=token)

    return credentials
