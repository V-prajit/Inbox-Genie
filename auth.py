import os
import json
import base64
import hashlib
import datetime
import threading
import webbrowser
import queue
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import requests

from config import (
    MCP_SERVER_URL, TOKEN_FILE, TOKEN_FILE_PERMISSIONS,
    REDIRECT_URI, REDIRECT_PORT, SCOPES,
    AUTH_TIMEOUT, STATE_TIMEOUT, CLIENT_SECRETS_FILE
)

session = requests.Session()

auth_code_queue = queue.Queue()
auth_state_received = queue.Queue()

# --- Token Management ---

def save_tokens(token_data):
    try:
        if 'expires_in' in token_data and token_data['expires_in']:
            expires_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=token_data['expires_in'] - 60)
            token_data['expires_at'] = expires_at.isoformat()
        elif 'expires_at' not in token_data:
            expires_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)
            token_data['expires_at'] = expires_at.isoformat()

        with open(TOKEN_FILE, 'w') as f:
            json.dump(token_data, f)
            
        os.chmod(TOKEN_FILE, TOKEN_FILE_PERMISSIONS)
        print(f"Tokens saved to {TOKEN_FILE}")
    except Exception as e:
        print(f"Error saving tokens to file: {e}")


def load_tokens():
    if not os.path.exists(TOKEN_FILE):
        return None
        
    try:
        with open(TOKEN_FILE, 'r') as f:
            token_data = json.load(f)
        return token_data
    except (IOError, json.JSONDecodeError) as e:
        print(f"Error loading tokens from file: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error in load_tokens: {e}")
        return None


def clear_tokens():
    """Removes stored tokens by deleting the token file."""
    if os.path.exists(TOKEN_FILE):
        try:
            os.remove(TOKEN_FILE)
            print(f"Token file {TOKEN_FILE} removed.")
        except OSError as e:
            print(f"Error removing token file: {e}")


def get_active_access_token():
    token_data = load_tokens()
    if not token_data:
        print("No token data found.")
        return None

    # Check if token is expired
    expires_at_str = token_data.get('expires_at')
    access_token = token_data.get('access_token')

    is_expired = True
    if expires_at_str:
        try:
            expires_at = datetime.datetime.fromisoformat(expires_at_str)
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=datetime.timezone.utc)

            if expires_at > datetime.datetime.now(datetime.timezone.utc):
                is_expired = False
        except ValueError:
            print(f"Warning: Could not parse expires_at value '{expires_at_str}'. Assuming token is expired.")
            is_expired = True

    if not is_expired and access_token:
        return access_token
    
    print("Access token expired or missing. Attempting refresh...")
    refresh_token = token_data.get('refresh_token')

    if not refresh_token:
        print("No refresh token found. Please re-authenticate.")
        clear_tokens()
        return None
        
    client_id = None
    client_secret = None
    
    if not CLIENT_SECRETS_FILE:
        print("Error: CLIENT_SECRETS_FILE environment variable not set. Cannot refresh.")
        return None
        
    try:
        with open(CLIENT_SECRETS_FILE, 'r') as f:
            secrets_json = json.load(f)
            secrets = secrets_json.get('installed', secrets_json.get('web', {}))
            client_id = secrets.get('client_id')
            client_secret = secrets.get('client_secret')
    except Exception as e:
        print(f"Error loading client secrets ({CLIENT_SECRETS_FILE}) for refresh: {e}")
        return None

    if not client_id or not client_secret:
        print("Client ID or Client Secret not found in secrets file. Cannot refresh.")
        return None

    refresh_payload = {
        'client_id': client_id,
        'client_secret': client_secret,
        'refresh_token': refresh_token,
        'grant_type': 'refresh_token',    
    }    

    try:
        response = requests.post("https://oauth2.googleapis.com/token", data=refresh_payload)
        response.raise_for_status()
        new_token_data = response.json()

        updated_data = {
            'access_token': new_token_data['access_token'],
            'refresh_token': refresh_token,
            'expires_in': new_token_data.get('expires_in'),
            'scope': new_token_data.get('scope', token_data.get('scope'))
        }
        save_tokens(updated_data)
        print("Access token refreshed successfully.")
        return updated_data['access_token']
    
    except requests.exceptions.RequestException as e:
        print(f"Error refreshing token: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response status: {e.response.status_code}")
            print(f"Response body: {e.response.text}")
            if e.response.status_code in [400, 401]:
                print("Refresh failed (invalid grant/token). Clearing tokens. Please re-authenticate.")
                clear_tokens()
        return None

# --- PKCE Utils ---

def generate_pkce_codes():
    code_verifier = base64.urlsafe_b64encode(os.urandom(32)).rstrip(b'=').decode('utf-8')
    
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode('utf-8')).digest()
    ).rstrip(b'=').decode('utf-8')
    
    return code_verifier, code_challenge

# --- Local Callback Server ---

class CallbackHandler(BaseHTTPRequestHandler):
    server_instance = None  
    
    def do_GET(self):
        query_components = parse_qs(urlparse(self.path).query)
        code = query_components.get('code', [None])[0]
        state = query_components.get('state', [None])[0]
        error = query_components.get('error', [None])[0]

        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()

        if error:
            message = f"<h1>Authentication Failed</h1><p>Error: {error}</p><p>You can close this window.</p>"
            auth_code_queue.put(None)
            auth_state_received.put(state)
        elif code:
            message = "<h1>Authentication Successful!</h1><p>You can close this window and return to the application.</p>"
            auth_code_queue.put(code)
            auth_state_received.put(state)
        else:
            message = "<h1>Authentication Error</h1><p>Invalid callback received.</p>"
            auth_code_queue.put(None)
            auth_state_received.put(state)

        self.wfile.write(message.encode('utf-8'))

        if CallbackHandler.server_instance:
            threading.Thread(target=CallbackHandler.server_instance.shutdown, daemon=True).start()
   
    def log_message(self, format, *args):
        """Override to silence HTTP server logs."""
        return


def start_callback_server(port):
    server_address = ('localhost', port)
    httpd = HTTPServer(server_address, CallbackHandler)
    CallbackHandler.server_instance = httpd
    print(f"Local callback server starting on http://localhost:{port}")
    
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    
    return httpd, thread

# --- Authentication Flow ---

def authenticate():
    code_verifier, code_challenge = generate_pkce_codes()
    state = base64.urlsafe_b64encode(os.urandom(16)).rstrip(b'=').decode('utf-8')

    httpd, server_thread = start_callback_server(REDIRECT_PORT)

    auth_url_params = {
        'redirect_uri': REDIRECT_URI,
        'state': state,
        'code_challenge': code_challenge,
        'code_challenge_method': 'S256',
        'response_type': 'code',
        'scope': ' '.join(SCOPES)
    }
    
    try:
        response = session.get(f"{MCP_SERVER_URL}/authenticate", params=auth_url_params)
        response.raise_for_status()
        auth_data = response.json()
        auth_url = auth_data.get("auth_url")
        
        if not auth_url:
            print("Error: Did not receive authentication URL from server.")
            httpd.shutdown()
            return False
    except requests.exceptions.RequestException as e:
        print(f"Error getting authentication URL from MCP server: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Status: {e.response.status_code}, Body: {e.response.text}")
        httpd.shutdown()
        return False

    print("\n" + "="*60)
    print("ACTION REQUIRED: Please authenticate in your web browser.")
    print("Opening browser to Google authentication page...")
    print("If the browser does not open, please copy and paste this URL:")
    print(auth_url)
    print("="*60 + "\n")
    
    webbrowser.open(auth_url)

    print("Waiting for authorization callback (up to 5 minutes)...")
    auth_code = None
    received_state = None
    
    try:
        auth_code = auth_code_queue.get(timeout=AUTH_TIMEOUT)
        received_state = auth_state_received.get(timeout=STATE_TIMEOUT)
    except queue.Empty:
        print("Authentication timed out or window closed.")
        httpd.shutdown()
        return False

    if received_state != state:
        print("Error: State mismatch. Potential security issue.")
        return False
        
    if auth_code is None:
        print("Authentication failed in browser or callback error.")
        return False

    print("Authorization code received.")
    print("Exchanging code for tokens via MCP server...")
    
    token_payload = {
        'grant_type': 'authorization_code',
        'code': auth_code,
        'redirect_uri': REDIRECT_URI,
        'code_verifier': code_verifier,
    }
    
    try:
        response = session.post(f"{MCP_SERVER_URL}/token", json=token_payload)
        response.raise_for_status()
        token_data = response.json()

        save_tokens(token_data)
        print("Authentication successful! Tokens saved.")
        return True

    except requests.exceptions.RequestException as e:
        print(f"Error exchanging code for tokens via MCP server: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response status: {e.response.status_code}")
            print(f"Response body: {e.response.text}")
        return False