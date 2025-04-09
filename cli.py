# cli.py
import requests
import openai
import json
from dotenv import load_dotenv
import os
import time
import webbrowser
import hashlib
import base64
import threading
import queue # For communication between callback server thread and main thread
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import datetime
# Optional: for more secure storage than a file
# import keyring

load_dotenv()

# --- Configuration ---
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8000")
OLLAMA_API_URL = os.getenv('BASE_URL') # For LLM
MODEL_NAME = os.getenv('MODEL_NAME', "llama3.1:8b-instruct-q4_K_M") # For LLM

# OAuth Config
REDIRECT_URI = os.getenv('REDIRECT_URI', 'http://localhost:8989/callback')
REDIRECT_PORT = int(os.getenv('REDIRECT_PORT', '8989'))
SCOPES = os.getenv('SCOPES', '').split() # Ensure scopes match server/client_secrets

# Token storage file (simple approach)
TOKEN_FILE = "gmail_token.json"
# For more secure storage (optional):
# SERVICE_NAME = "inbox_genie_cli"

# --- LLM Client Setup ---
llm_client = None
if OLLAMA_API_URL:
    llm_client = openai.OpenAI(
        base_url=OLLAMA_API_URL,
        api_key="ollama", # Standard key for Ollama's OpenAI compatible API
    )
else:
    # Example if using OpenAI directly
    # openai_api_key = os.getenv("OPENAI_API_KEY")
    # if openai_api_key:
    #     llm_client = openai.OpenAI(api_key=openai_api_key)
    pass

if not llm_client:
    print("Warning: LLM client not configured. Summarization will not work.")
    # Optionally, disable summarization features or exit

# --- Requests Session ---
# Use a session for potential connection pooling and header management
session = requests.Session()

# --- Token Management ---

def save_tokens(token_data):
    """Saves token data to a file."""
    # Optional: Use keyring for more secure storage
    # try:
    #     keyring.set_password(SERVICE_NAME, "refresh_token", token_data.get('refresh_token', ''))
    #     keyring.set_password(SERVICE_NAME, "access_token", token_data.get('access_token', ''))
    #     keyring.set_password(SERVICE_NAME, "expires_at", str(token_data.get('expires_at', '')))
    #     print("Tokens saved securely using keyring.")
    #     # Clean up old file if switching
    #     if os.path.exists(TOKEN_FILE):
    #         os.remove(TOKEN_FILE)
    # except Exception as e:
    #     print(f"Warning: Keyring storage failed ({e}), falling back to file storage.")
    #     with open(TOKEN_FILE, 'w') as f:
    #         json.dump(token_data, f)
    #     os.chmod(TOKEN_FILE, 0o600) # Restrict permissions
    #     print(f"Tokens saved to {TOKEN_FILE}")

    # Simple file storage:
    try:
        # Calculate expiry time
        if 'expires_in' in token_data and token_data['expires_in']:
             expires_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=token_data['expires_in'] - 60) # 60s buffer
             token_data['expires_at'] = expires_at.isoformat()

        with open(TOKEN_FILE, 'w') as f:
            json.dump(token_data, f)
        os.chmod(TOKEN_FILE, 0o600) # Restrict file permissions
        print(f"Tokens saved to {TOKEN_FILE}")
    except Exception as e:
        print(f"Error saving tokens to file: {e}")


def load_tokens():
    """Loads token data from a file."""
    # Optional: Use keyring
    # try:
    #     refresh_token = keyring.get_password(SERVICE_NAME, "refresh_token")
    #     access_token = keyring.get_password(SERVICE_NAME, "access_token")
    #     expires_at_str = keyring.get_password(SERVICE_NAME, "expires_at")
    #     if refresh_token or access_token: # Check if anything was retrieved
    #         print("Tokens loaded from keyring.")
    #         expires_at = datetime.datetime.fromisoformat(expires_at_str) if expires_at_str else None
    #         return {
    #             'refresh_token': refresh_token,
    #             'access_token': access_token,
    #             'expires_at': expires_at.isoformat() if expires_at else None
    #         }
    # except Exception as e:
    #     print(f"Info: Keyring retrieval failed or no tokens stored ({e}), trying file storage.")

    # Simple file storage:
    if not os.path.exists(TOKEN_FILE):
        return None
    try:
        with open(TOKEN_FILE, 'r') as f:
            token_data = json.load(f)
        # Convert expires_at back to datetime for comparison
        if 'expires_at' in token_data and token_data['expires_at']:
             # Keep as ISO string for consistency, compare later
             pass
        print(f"Tokens loaded from {TOKEN_FILE}")
        return token_data
    except (IOError, json.JSONDecodeError) as e:
        print(f"Error loading tokens from file: {e}")
        return None

def clear_tokens():
     """Removes stored tokens."""
     # Optional: Use keyring
    # try:
    #     keyring.delete_password(SERVICE_NAME, "refresh_token")
    #     keyring.delete_password(SERVICE_NAME, "access_token")
    #     keyring.delete_password(SERVICE_NAME, "expires_at")
    #     print("Tokens cleared from keyring.")
    # except Exception as e:
    #      print(f"Warning: Keyring token clearing failed ({e}).")

     if os.path.exists(TOKEN_FILE):
        try:
            os.remove(TOKEN_FILE)
            print(f"Token file {TOKEN_FILE} removed.")
        except OSError as e:
            print(f"Error removing token file: {e}")


def get_active_access_token():
    """Loads tokens, refreshes if necessary, returns valid access token."""
    token_data = load_tokens()
    if not token_data:
        return None # Needs authentication

    expires_at_str = token_data.get('expires_at')
    access_token = token_data.get('access_token')

    # Check expiration
    is_expired = True # Assume expired if no expiry info
    if expires_at_str:
        expires_at = datetime.datetime.fromisoformat(expires_at_str)
        if expires_at > datetime.datetime.now(datetime.timezone.utc):
             is_expired = False

    if not is_expired and access_token:
        return access_token # Current token is valid

    # --- Token needs refresh ---
    print("Access token expired or missing. Attempting refresh...")
    refresh_token = token_data.get('refresh_token')
    if not refresh_token:
        print("No refresh token found. Please re-authenticate.")
        clear_tokens()
        return None

    # Perform refresh using Google's endpoint directly
    # Requires client_id and client_secret from the secrets file
    client_id = None
    client_secret = None
    client_secrets_file = os.getenv('CLIENT_SECRETS_FILE')
    try:
        with open(client_secrets_file, 'r') as f:
             secrets = json.load(f).get('installed', {}) # Adjust key if using 'web' type
             client_id = secrets.get('client_id')
             client_secret = secrets.get('client_secret')
    except Exception as e:
        print(f"Error loading client secrets for refresh: {e}")
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
        response.raise_for_status() # Raise exception for bad status codes
        new_token_data = response.json()

        # Update stored tokens
        updated_data = {
            'access_token': new_token_data['access_token'],
            'refresh_token': refresh_token, # Google often doesn't return a new refresh token
            'expires_in': new_token_data.get('expires_in'),
            'scope': new_token_data.get('scope')
        }
        save_tokens(updated_data) # Save updated tokens (this recalculates expires_at)
        print("Access token refreshed successfully.")
        return updated_data['access_token']

    except requests.exceptions.RequestException as e:
        print(f"Error refreshing token: {e}")
        if e.response is not None:
            print(f"Response status: {e.response.status_code}")
            print(f"Response body: {e.response.text}")
            if e.response.status_code in [400, 401]: # Bad request or invalid grant/token
                print("Refresh failed. Clearing tokens. Please re-authenticate.")
                clear_tokens()
        return None


# --- PKCE Utils ---
def generate_pkce_codes():
    """Generates PKCE code verifier and challenge."""
    code_verifier = base64.urlsafe_b64encode(os.urandom(32)).rstrip(b'=').decode('utf-8')
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode('utf-8')).digest()
    ).rstrip(b'=').decode('utf-8')
    return code_verifier, code_challenge

# --- Local Callback Server ---
auth_code_queue = queue.Queue() # Used to pass the auth code back to main thread
auth_state_received = queue.Queue() # Used to pass the state back

class CallbackHandler(BaseHTTPRequestHandler):
    """Handles the redirect callback from Google."""
    def do_GET(self):
        global auth_code_queue, auth_state_received
        # Parse query parameters
        query_components = parse_qs(urlparse(self.path).query)
        code = query_components.get('code', [None])[0]
        state = query_components.get('state', [None])[0]
        error = query_components.get('error', [None])[0]

        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()

        if error:
            message = f"<h1>Authentication Failed</h1><p>Error: {error}</p><p>Please close this window and try again.</p>"
            auth_code_queue.put(None) # Signal failure
            auth_state_received.put(state) # Still put state for verification
        elif code:
            message = "<h1>Authentication Successful!</h1><p>You can close this window and return to the application.</p>"
            auth_code_queue.put(code)
            auth_state_received.put(state)
        else:
             message = "<h1>Authentication Error</h1><p>Invalid callback received.</p>"
             auth_code_queue.put(None)
             auth_state_received.put(state) # Or None if state is also missing

        self.wfile.write(message.encode('utf-8'))

    def log_message(self, format, *args):
        # Silences the default logging of requests to stderr
        return


def start_callback_server(port):
    """Starts the local HTTP server in a separate thread."""
    server_address = ('localhost', port)
    httpd = HTTPServer(server_address, CallbackHandler)
    print(f"Local callback server started on http://localhost:{port}")
    # Run indefinitely until shutdown is called
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, thread

# --- Authentication Flow ---
def authenticate():
    """Guides the user through the OAuth 2.0 flow."""
    # 1. Generate PKCE codes and state
    code_verifier, code_challenge = generate_pkce_codes()
    # State should be unique per auth request to prevent CSRF
    state = base64.urlsafe_b64encode(os.urandom(16)).rstrip(b'=').decode('utf-8')

    # 2. Start local callback server
    httpd, server_thread = start_callback_server(REDIRECT_PORT)

    # 3. Get authorization URL from our server
    auth_url_params = {
        'redirect_uri': REDIRECT_URI,
        'state': state,
        'code_challenge': code_challenge,
        'code_challenge_method': 'S256',
        'response_type': 'code', # Standard parameter
        'scope': ' '.join(SCOPES) # Let server know required scopes
    }
    try:
        response = session.get(f"{MCP_SERVER_URL}/authenticate", params=auth_url_params)
        response.raise_for_status()
        auth_data = response.json()
        auth_url = auth_data.get("auth_url")
        if not auth_url:
            print("Error: Did not receive authentication URL from server.")
            httpd.shutdown() # Ensure server stops
            return False
    except requests.exceptions.RequestException as e:
        print(f"Error getting authentication URL: {e}")
        httpd.shutdown()
        return False

    # 4. Open browser for user authorization
    print("Opening browser for authentication...")
    webbrowser.open(auth_url)
    print("Please complete the authentication in your browser.")

    # 5. Wait for callback to local server
    print("Waiting for authorization callback...")
    auth_code = None
    received_state = None
    try:
        # Wait for code/error from the queue (blocking)
        auth_code = auth_code_queue.get(timeout=300) # 5 minute timeout
        received_state = auth_state_received.get(timeout=1) # State should arrive almost instantly
    except queue.Empty:
        print("Authentication timed out.")
        httpd.shutdown()
        return False
    finally:
         # Ensure server is shut down regardless of outcome
         print("Shutting down local callback server...")
         httpd.shutdown()
         # server_thread.join() # Wait for thread to finish

    # 6. Verify state and check for errors
    if received_state != state:
        print("Error: State mismatch. Potential CSRF attack.")
        return False
    if auth_code is None:
        print("Authentication failed in browser or invalid callback received.")
        return False

    print("Authorization code received.")

    # 7. Exchange authorization code for tokens
    print("Exchanging code for tokens...")
    token_payload = {
        'grant_type': 'authorization_code',
        'code': auth_code,
        'redirect_uri': REDIRECT_URI,
        'code_verifier': code_verifier,
        # 'client_id': client_id # Server might infer this
    }
    try:
        response = session.post(f"{MCP_SERVER_URL}/token", json=token_payload)
        response.raise_for_status()
        token_data = response.json()

        # 8. Save tokens
        save_tokens(token_data)
        print("Authentication successful! Tokens saved.")
        return True

    except requests.exceptions.RequestException as e:
        print(f"Error exchanging code for tokens: {e}")
        if e.response is not None:
             print(f"Response status: {e.response.status_code}")
             print(f"Response body: {e.response.text}")
        return False


# --- API Call Helper ---
def make_api_call(method, endpoint, **kwargs):
    """Makes an authenticated API call to the MCP server."""
    access_token = get_active_access_token()
    if not access_token:
        print("Authentication required. Please run authenticate command or restart.")
        # Optionally trigger authentication here
        # if not authenticate():
        #     return None # Auth failed
        # access_token = get_active_access_token() # Try getting token again
        # if not access_token: return None
        return None # Indicate auth needed

    headers = kwargs.pop('headers', {})
    headers['Authorization'] = f"Bearer {access_token}"

    url = f"{MCP_SERVER_URL}/{endpoint.lstrip('/')}"

    try:
        response = session.request(method, url, headers=headers, **kwargs)
        if response.status_code == 401:
             # Specific handling for expired/invalid token detected by server
             print("Server reported token is invalid or expired. Attempting refresh...")
             clear_tokens() # Clear potentially bad token before retry/reauth
             access_token = get_active_access_token() # Try refresh
             if not access_token:
                 print("Refresh failed or not possible. Please re-authenticate.")
                 return None
             # Retry the request once with the new token
             print("Retrying API call with new token...")
             headers['Authorization'] = f"Bearer {access_token}"
             response = session.request(method, url, headers=headers, **kwargs)
             response.raise_for_status() # Raise error if retry also fails

        response.raise_for_status() # Raise errors for other bad statuses (4xx, 5xx)
        return response.json()

    except requests.exceptions.HTTPError as e:
         print(f"API Error ({e.response.status_code}) calling {method} {url}:")
         try:
             # Try to print JSON error detail from server if available
             error_detail = e.response.json()
             print(json.dumps(error_detail, indent=2))
         except json.JSONDecodeError:
             print(e.response.text) # Print raw text if not JSON
         return None # Indicate error
    except requests.exceptions.RequestException as e:
        print(f"Network error calling {method} {url}: {e}")
        return None # Indicate error

# --- Email Summarization Logic ---
def fetch_and_summarize_emails(limit=5):
    """Fetch and summarize recent emails using authenticated API call."""
    if not llm_client:
        print("LLM client not available. Cannot summarize.")
        return

    print(f"Fetching the {limit} most recent emails via server...")

    email_request = {
        "tool_name": "read_emails",
        "parameters": {
            "limit": limit
        }
    }

    # Use the authenticated API call helper
    response_data = make_api_call('POST', '/use_tool', json=email_request)

    if response_data is None:
        print("Failed to fetch emails.")
        return # Error handled by make_api_call

    emails = response_data.get("emails", [])

    if not emails:
        print("No emails found or returned by server.")
        return

    print(f"Found {len(emails)} emails. Summarizing...")

    summaries = []
    for email in emails:
        from_email = email.get('from_email', 'Unknown')
        subject = email.get('subject', '(No subject)')
        text_content = email.get('body_text', '')

        # Truncate text if too long for LLM context/cost
        max_len = 2000 # Adjust as needed
        if len(text_content) > max_len:
            text_content = text_content[:max_len] + "..."

        # Create prompt for LLM
        prompt = f"""
        Summarize the following email concisely (under 50 words):

        From: {from_email}
        Subject: {subject}

        Body:
        {text_content}

        Summary:"""

        print(f"Summarizing email: {subject}")

        try:
            # Use the configured LLM client
            llm_response = llm_client.chat.completions.create(
                model=MODEL_NAME,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=100, # Limit summary length
                temperature=0.5 # Adjust creativity/factuality
            )
            summary = llm_response.choices[0].message.content.strip()

            summaries.append({
                "from": from_email,
                "subject": subject,
                "summary": summary
            })

        except Exception as e:
            print(f"Error calling LLM for email '{subject}': {str(e)}")
            summaries.append({
                "from": from_email,
                "subject": subject,
                "summary": f"Error generating summary: {str(e)}"
            })

    # Display summaries
    print("\n" + "="*50)
    print("EMAIL SUMMARIES")
    print("="*50)

    for i, summary_data in enumerate(summaries, 1):
        print(f"\nEmail {i}:")
        print(f"  From: {summary_data['from']}")
        print(f"  Subject: {summary_data['subject']}")
        print(f"  Summary: {summary_data['summary']}")

# --- Main CLI Loop ---
def main():
    print("="*50)
    print("INBOX GENIE - CLI (Token Auth Mode)")
    print("="*50)

    # Check initial authentication status (do we have a potentially valid token?)
    access_token = get_active_access_token()
    if not access_token:
        print("Not authenticated. Attempting authentication...")
        if not authenticate():
            print("Authentication failed. Exiting.")
            return
        else:
            print("Authentication successful.")
    else:
        print("Authenticated using stored tokens.")


    # Main command loop
    while True:
        print("\n" + "-"*50)
        print("Available commands:")
        print("1. summarize (or summarize <number>) - Summarize recent emails")
        print("2. reauth - Force re-authentication")
        print("3. revoke - Revoke Google access")
        print("4. exit - Exit the application")
        print("-"*50)

        command_line = input("\nEnter command: ").strip().lower()
        parts = command_line.split()
        command = parts[0] if parts else ""

        if command == "exit" or command == "quit" or command == "q":
            print("Exiting Inbox Genie. Goodbye!")
            break

        elif command == "reauth":
             print("Forcing re-authentication...")
             clear_tokens()
             if not authenticate():
                 print("Authentication failed.")
             # Continue loop

        elif command == "revoke":
            print("Attempting to revoke access...")
            token_data = load_tokens()
            refresh_token = token_data.get('refresh_token') if token_data else None
            if not refresh_token:
                print("No refresh token found to revoke access. Please re-authenticate first if needed.")
                continue

            # Need to send refresh token to server's /revoke endpoint
            revoke_payload = {'refresh_token': refresh_token}
            response_data = make_api_call('POST', '/revoke', json=revoke_payload) # Use API helper

            if response_data:
                print(response_data.get("message", "Revocation request sent."))
                clear_tokens() # Clear local tokens after successful revoke
            else:
                print("Failed to send revocation request.")
                # Do not clear local tokens if revoke failed server-side

        elif command.startswith("summarize"):
            limit = 5 # Default
            if len(parts) > 1 and parts[1].isdigit():
                limit = int(parts[1])
                if limit <= 0 or limit > 50: # Add reasonable bounds
                     print("Please enter a number between 1 and 50.")
                     continue

            fetch_and_summarize_emails(limit)

        else:
            if command: # Avoid printing for empty input
                print(f"Unknown command: {command}")

if __name__ == "__main__":
    main()