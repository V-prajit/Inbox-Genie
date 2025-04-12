import requests
import openai
import json
from dotenv import load_dotenv
import os
import webbrowser
import hashlib
import base64
import threading
import queue
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import datetime
import email
from email import policy
from email.parser import BytesParser
import sys
import html2text

load_dotenv()

MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8000")
OLLAMA_API_URL = os.getenv('BASE_URL') 
MODEL_NAME = os.getenv('MODEL_NAME', "llama3.1:8b-instruct-q4_K_M")

REDIRECT_URI = os.getenv('REDIRECT_URI', 'http://localhost:8989/callback')
REDIRECT_PORT = int(os.getenv('REDIRECT_PORT', '8989'))
SCOPES = os.getenv('SCOPES', '').split()

TOKEN_FILE = "gmail_token.json"

# Setup the LLM Client
llm_client = None
if OLLAMA_API_URL:
    try:
        llm_client = openai.OpenAI(
            base_url=OLLAMA_API_URL,
            api_key="ollama",
        )
        llm_client.models.list()
        print(f"LLM Client configured for {MODEL_NAME} at {OLLAMA_API_URL}")
    except Exception as e:
        print(f"Error configuring LLM client: {e}")
        llm_client = None  
else:
    print("Warning: OLLAMA_API_URL not set in .env. LLM features will be disabled.") 

session = requests.Session()

def save_tokens(token_data):
    """Write token_data to Token file"""
    try:
        if 'expires_in' in token_data and token_data['expires_in']:
            expires_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=token_data['expires_in'] -60 )
            token_data['expires_at'] = expires_at.isoformat()
        elif 'expires_at' not in token_data:
            expires_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1) 
            token_data['expires_at'] = expires_at.isoformat()

        with open(TOKEN_FILE, 'w') as f:
            json.dump(token_data, f)
        os.chmod(TOKEN_FILE, 0o600)   
        print(f"Tokens saved to {TOKEN_FILE}")
    except Exception as e:
        print(f"Error saving tokens to file: {e}")

def load_tokens():
    """Loads token data from a file."""
    if not os.path.exists(TOKEN_FILE):
        return None
    try:
        with open(TOKEN_FILE, 'r') as f:
            token_data = json.load(f)
        return token_data
    except (IOError, json.JSONDecodeError) as e:
        print(f"Error loading tokens from file: {e}")

        return None
    except Exception as e: # Catch any other potential errors
        print(f"Unexpected error in load_tokens: {e}")
        return None
    
def clear_tokens():
    """Remove Stored Tokens"""
    if os.path.exists(TOKEN_FILE):
        try:
            os.remove(TOKEN_FILE)
            print(f"Token file {TOKEN_FILE} removed.")
        except OSError as e:
            print(f"Error removing token file: {e}")

def get_active_access_token():
    """Load tokens, refresh them if necessary, return valid tokens"""
    token_data = load_tokens()

    if not token_data:
        print("No token data found.")
        return None

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
    client_secrets_file = os.getenv('CLIENT_SECRETS_FILE')
    if not client_secrets_file:
        print("Error: CLIENT_SECRETS_FILE environment variable not set. Cannot refresh.")
        return None 
    try:
        with open(client_secrets_file, 'r') as f:
            secrets = json.load(f).get('installed', json.load(f).get('web', {}))
            client_id = secrets.get('client_id')
            client_secret = secrets.get('client_secret')
    except Exception as e:
        print(f"Error loading client secrets ({client_secrets_file}) for refresh: {e}")
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
        response = requests.post("https://oauth2.googleapis.com/token", date=refresh_payload)
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
        if e.response is not None:
            print(f"Response status: {e.response.status_code}")
            print(f"Response body: {e.response.text}")
            if e.response.status_code in [400, 401]:
                print("Refresh failed (invalid grant/token). Clearing tokens. Please re-authenticate.")
                clear_tokens()
        return None
    
def generate_pkce_codes():
    """Generates PKCE code verifier and challenge."""
    code_verifier = base64.urlsafe_b64encode(os.urandom(32)).rstrip(b'=').decode('utf-8')
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode('utf-8')).digest()
    ).rstrip(b'=').decode('utf-8')
    return code_verifier, code_challenge

auth_code_queue = queue.Queue()
auth_state_received = queue.Queue()

class CallbackHandler(BaseHTTPRequestHandler):
    """Handles the redirect callback from Google."""

    def do_GET(self):
        global auth_code_queue, auth_state_received
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
        # Silences the default logging
        return

def start_callback_server(port):
    """Starts the local HTTP server in a separate thread."""
    server_address = ('localhost', port)
    httpd = HTTPServer(server_address, CallbackHandler)
    CallbackHandler.server_instance = httpd # Store instance for shutdown
    print(f"Local callback server starting on http://localhost:{port}")
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, thread

def authenticate():
    """Guides the user through the OAuth 2.0 flow."""
    code_verifier, code_challenge = generate_pkce_codes()
    state = base64.urlsafe_b64encode(os.urandom(16)).rstrip(b'=').decode('utf-8')

    httpd, server_thread = start_callback_server(REDIRECT_PORT)

    auth_url_params = {
        'redirect_uri': REDIRECT_URI,
        'state': state,
        'code_challenge': code_challenge,
        'code_challenge_method': 'S256',
        'response_type': 'code',
        'scope': ' '.join(SCOPES) # Pass scopes needed
    }
    try:
        # Call the /authenticate endpoint on YOUR MCP server
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
        if e.response is not None:
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
        auth_code = auth_code_queue.get(timeout=300)
        received_state = auth_state_received.get(timeout=5) # State should arrive quickly
    except queue.Empty:
        print("Authentication timed out or window closed.")
        # Server might shut down via handler, but ensure it does
        httpd.shutdown()
        return False
    # No explicit shutdown needed here - handler attempts it

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
        'redirect_uri': REDIRECT_URI, # Must match the URI used in the initial request
        'code_verifier': code_verifier,
    }
    try:
        # Call the /token endpoint on YOUR MCP server
        response = session.post(f"{MCP_SERVER_URL}/token", json=token_payload)
        response.raise_for_status()
        token_data = response.json()

        save_tokens(token_data)
        print("Authentication successful! Tokens saved.")
        return True

    except requests.exceptions.RequestException as e:
        print(f"Error exchanging code for tokens via MCP server: {e}")
        if e.response is not None:
             print(f"Response status: {e.response.status_code}")
             print(f"Response body: {e.response.text}")
        return False

def display_clean_email_response(response_data, tool_name, limit=None, show_full=False):
    """
    Displays email content in a clean, readable format without debug information.
    
    Args:
        response_data: The response data from the MCP server
        tool_name: The tool that was used (read_emails, search_emails, etc.)
        limit: Optional limit on number of emails to display
        show_full: Whether to show the full email body or truncate it
    """
    print("\n" + "="*60)
    print(" EMAIL RESULTS ".center(60, "="))
    print("="*60)
    
    # Extract the appropriate email list based on tool name
    emails = []
    if tool_name == 'read_emails':
        emails = response_data.get('emails', [])
    elif tool_name == 'search_emails':
        emails = response_data.get('results', [])
    
    # Handle empty results
    if not emails:
        print("\nNo emails found.")
        return
    
    # Apply limit if specified
    if limit and isinstance(limit, int) and limit > 0:
        emails = emails[:limit]
    
    # Display each email
    for i, email in enumerate(emails, 1):
        print(f"\n{'-'*60}")
        print(f" EMAIL {i} ".center(60, "-"))
        print(f"{'-'*60}")
        
        # Display header info
        print(f"From: {email.get('from_email', 'Unknown')}")
        print(f"Subject: {email.get('subject', '(No subject)')}")
        print(f"Date: {email.get('date', 'Unknown')}")
        
        # Check for unread status
        if email.get('unread', False):
            print("Status: UNREAD")
        
        print(f"{'-'*40}")
        
        # Display body
        body_text = email.get('body_text', '')
        if not body_text or not body_text.strip():
            body_text = "(No text content available)"
        
        # Truncate long emails unless show_full is True
        if not show_full and len(body_text) > 1000:
            print(f"Body:\n{body_text[:1000]}")
            print("\n... (Content truncated) ...")
            print(f"\n[Email is {len(body_text)} characters long. Use 'show full emails' to see complete content.]")
        else:
            print(f"Body:\n{body_text}")
    
    print(f"\n{'-'*60}")
    print(f" End of Results: {len(emails)} email(s) displayed ".center(60, "-"))
    print(f"{'-'*60}")

def clean_email_content(raw_content):
    body = ""
    is_html_only = False
    #assuming that is there is no < or > it is an plain text email
    if isinstance(raw_content, str) and '<'not in raw_content and '>' not in raw_content:
        return raw_content
    
    try:
        if isinstance(raw_content, str):
            raw_bytes = raw_content.encode('utf-8', errors='ignore')
        elif isinstance(raw_bytes, bytes):
            raw_bytes = raw_content
        else:
            raw_bytes = str(raw_content).encode('utf-8', errors='ignore')

        msg = BytesParser(policy=policy.default).parsebytes(raw_bytes)

        if msg.is_multipart():
            plain_part = msg.get_body(preferencelist=('plain',))
            if plain_part:
                payload = plain_part.get_payload(decode=True)
                charset = plain_part.get_content_charset() or 'utf-8'
                body = payload.decode(charset, errors='replace')
            else:
                html_part = msg.get_body(preferencelist=('html',))
                if html_part:
                    payload = plain_part.get_payload(decode=True)
                    charset = plain_part.get_content_charset() or 'utf-8'
                    body = payload.decode(charset, errors='replace') 
        elif msg.get_content_type().startswith('text/'):
            payload = msg.get_payload(decode=True)
            charset = msg.get_content_charset() or 'utf-8'
            body = payload.decode(charset, errors='replace')
        else:
            is_html_only = True

    except Exception as e:
        is_html_only = True

    if is_html_only:
        if isinstance(raw_content, bytes):
            try:
                body = raw_content.decode('utf-8', errors='replace') # Try decoding if bytes
            except UnicodeDecodeError:
                body = raw_content.decode('latin-1', errors='replace') # Fallback encoding
        elif isinstance(raw_content, str):
            body = raw_content
        else:
             body = str(raw_content)
    
    if '<' in body and '>' in body and ('<html' in body.lower() or '<p>' in body.lower() or '<div' in body.lower() or '<br' in body.lower()):
        try:
            h = html2text.HTML2Text()
            h.ignore_links = False
            h.body_width = 0 
            plain_text = h.handle(body)
            return plain_text.strip() # Remove leading/trailing whitespace
        except Exception as html_e:
             return body.strip() 
    else:
        # It's likely already plain text
        return body.strip()

def make_api_call(method, endpoint, **kwargs):
    """Makes an authenticated API call to the MCP server."""
    access_token = get_active_access_token()
    if not access_token:
        print("Authentication required or token invalid.")
        # Optional: Automatically trigger authentication
        # print("Attempting to authenticate...")
        # if not authenticate():
        #     print("Authentication failed. Cannot make API call.")
        #     return None
        # access_token = get_active_access_token()
        # if not access_token:
        #     print("Authentication succeeded but failed to get token. Cannot make API call.")
        #     return None
        # print("Authentication successful, retrying API call...")
        return None # Indicate auth needed or failed

    headers = kwargs.pop('headers', {})
    headers['Authorization'] = f"Bearer {access_token}"
    # Add content-type if sending JSON data
    if 'json' in kwargs and 'Content-Type' not in headers:
         headers['Content-Type'] = 'application/json'

    url = f"{MCP_SERVER_URL}/{endpoint.lstrip('/')}"

    try:
        response = session.request(method, url, headers=headers, **kwargs)

        if response.status_code == 401:
             print("Server reported token is invalid/expired (401).")
             # Token might be actually expired, or just invalid.
             # Attempting refresh is handled by get_active_access_token on next call.
             # For now, just report and fail. Consider clearing tokens if this happens often.
             # clear_tokens() # Be careful with auto-clearing, might hide other issues
             return None # Indicate failure due to auth

        response.raise_for_status() # Raise errors for other bad statuses (4xx, 5xx)

        # Handle potential empty responses for non-GET requests
        if response.status_code == 204: # No Content
            return {"success": True, "message": "Operation successful (No Content)"}
        try:
             return response.json()
        except json.JSONDecodeError:
             # If response is not JSON but status was OK (e.g., 200)
             if response.ok:
                 return {"success": True, "message": "Operation successful", "content": response.text}
             else:
                 # This case should be caught by raise_for_status, but included for safety
                 print(f"API Error ({response.status_code}) calling {method} {url}: Non-JSON response")
                 print(response.text)
                 return None

    except requests.exceptions.HTTPError as e:
         print(f"API Error ({e.response.status_code}) calling {method} {url}:")
         try:
             error_detail = e.response.json()
             print(json.dumps(error_detail, indent=2))
         except json.JSONDecodeError:
             print(e.response.text)
         return None
    except requests.exceptions.RequestException as e:
        print(f"Network error calling {method} {url}: {e}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred during API call to {method} {url}: {e}")
        return None

# --- NEW: Fetch Tool Definitions ---
TOOL_DEFINITIONS_CACHE = None

def fetch_tool_definitions():
    """Fetches available tools and parameters from the MCP server."""
    global TOOL_DEFINITIONS_CACHE
    if TOOL_DEFINITIONS_CACHE:
        return TOOL_DEFINITIONS_CACHE

    print("Fetching available tools from server...")
    response_data = make_api_call('GET', '/tools') # Assumes /tools requires auth

    if response_data and 'tools' in response_data:
        print("Successfully fetched tool definitions.")
        TOOL_DEFINITIONS_CACHE = response_data['tools']
        return TOOL_DEFINITIONS_CACHE
    else:
        print("Failed to fetch tool definitions from server.")
        # Provide fallback basic definitions if needed, or handle error
        return None

def get_llm_tool_request(user_input, tool_definitions):
    """
    Sends the user input and tool definitions to the LLM
    and expects a JSON ToolRequest in return.
    """
    if not llm_client:
        print("LLM client is not configured. Cannot process request.")
        return None
    if not tool_definitions:
        print("Tool definitions are not available. Cannot process request.")
        return None

    # Construct an improved prompt for the LLM
    prompt_system = f"""You are an expert AI assistant named Inbox Genie. Your task is to understand a user's request related to managing their Gmail emails and convert it into a specific JSON format to call an API tool.

You have the following tools available:
{json.dumps(tool_definitions, indent=2)}

COMMON USER REQUESTS AND HOW TO HANDLE THEM:
1. "Show my emails" → read_emails with default parameters
2. "Show my last 5 emails" → read_emails with limit=5
3. "Show my unread emails" → read_emails with unread_only=true
4. "Search for emails about meetings" → search_emails with query="meetings"
5. "Send an email to john@example.com" → send_email with appropriate parameters

Based on the user's request below, identify the single most appropriate tool to use and construct a JSON object with the required 'tool_name' and 'parameters'.

Rules:
- Only output the JSON object. Do not include any other text, explanation, or formatting like ```json ... ```.
- Ensure all required parameters for the chosen tool are included in the JSON.
- For 'read_emails': 
  * Extract numbers mentioned (e.g., "show last 3 emails" → limit=3)
  * If "unread" is mentioned, set unread_only=true
  * Default limit is 5 if not specified

- For 'search_emails':
  * Extract search terms (e.g., "find emails about projects" → query="projects")
  * For queries like "from John", convert to proper search syntax (query="from:John")
  * Default limit is 5 if not specified

- For 'send_email':
  * Ensure 'to', 'subject', and 'body' are filled correctly
  * If user request is unclear, set "error" field instead

- If the user's request is unclear or doesn't match a tool, output: {{"error": "Request unclear or does not match available tools."}}
"""

    prompt_user = f"User request: \"{user_input}\"\n\nGenerate the JSON ToolRequest:"

    try:
        llm_response = llm_client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": prompt_system},
                {"role": "user", "content": prompt_user}
            ],
            max_tokens=500,
            temperature=0.1
        )
        llm_output = llm_response.choices[0].message.content.strip()

        # Attempt to parse the LLM output as JSON
        try:
            # Handle potential markdown code fences
            if llm_output.startswith("```json"):
                llm_output = llm_output.split("```json")[1].split("```")[0].strip()
            elif llm_output.startswith("```"):
                 llm_output = llm_output.split("```")[1].strip()

            tool_request_json = json.loads(llm_output)

            # Basic validation
            if "error" in tool_request_json:
                 print(f"I don't understand that email command: {tool_request_json['error']}")
                 print("Try something like 'show my emails', 'search for emails about meetings', etc.")
                 return None
                 
            if "tool_name" not in tool_request_json or "parameters" not in tool_request_json:
                print("Sorry, I couldn't interpret your request. Please try a different phrasing.")
                return None

            print(f"Processing: {tool_request_json.get('tool_name')}...")
            return tool_request_json

        except json.JSONDecodeError:
            print("Sorry, I couldn't process that request. Please try again with different wording.")
            return None

    except Exception as e:
        print(f"Error calling LLM: {e}")
        return None

# --- Main CLI Loop ---
def main():
    print("="*50)
    print("INBOX GENIE - LLM CLI")
    print("="*50)

    # --- Initial Authentication Check ---
    access_token = get_active_access_token()
    if not access_token:
        print("Not authenticated. Attempting authentication...")
        if not authenticate():
            print("Authentication failed. Exiting.")
            return
        else:
            print("\nAuthentication check passed.")
    else:
        print("Authenticated using stored tokens.")

    # --- Fetch Tool Definitions ---
    tool_definitions = fetch_tool_definitions()
    if not tool_definitions:
         print("Could not retrieve tool definitions. Functionality will be limited.")
         # Decide whether to exit or continue with limited functionality
         # return

    # --- Main Command Loop ---
    print("\nEnter your email requests in natural language.")
    print("Type 'reauth' to authenticate again, 'revoke' to remove access, or 'exit'.")
    while True:
        print("\n" + "-"*50)
        try:
            user_input = input("Your request: ").strip()
        except EOFError: # Handle Ctrl+D
             print("\nExiting...")
             break

        if not user_input:
            continue

        command = user_input.lower()

        if command == "exit" or command == "quit" or command == "q":
            print("Exiting Inbox Genie. Goodbye!")
            break

        elif command == "reauth":
             print("Forcing re-authentication...")
             clear_tokens()
             if authenticate():
                 # Re-fetch tools if needed, in case auth change affects available tools
                 print("Re-fetching tool definitions after re-authentication...")
                 fetch_tool_definitions()
             else:
                 print("Re-authentication failed.")
             continue # Go back to prompt

        elif command == "revoke":
            print("Attempting to revoke access...")
            token_data = load_tokens()
            refresh_token = token_data.get('refresh_token') if token_data else None
            if not refresh_token:
                print("No refresh token found to revoke. Cannot proceed.")
                continue

            revoke_payload = {'refresh_token': refresh_token}
            # Use make_api_call to send revoke request to YOUR MCP server's /revoke endpoint
            response_data = make_api_call('POST', '/revoke', json=revoke_payload)

            if response_data:
                print(response_data.get("message", "Revocation request processed by server."))
                clear_tokens() # Clear local tokens after successful revoke
            else:
                print("Failed to send revocation request or server denied it.")
            continue # Go back to prompt

        # --- Process natural language request using LLM ---
        else:
            if not llm_client:
                print("LLM client not available. Please configure OLLAMA_API_URL.")
                continue
            if not tool_definitions:
                 print("Tool definitions not available. Cannot process request via LLM.")
                 continue

            # Get the JSON tool request from the LLM
            tool_request_json = get_llm_tool_request(user_input, tool_definitions)

            if tool_request_json:
                # Send the LLM-generated request to the MCP server
                tool_name = tool_request_json.get('tool_name')

                print(f"Executing tool: {tool_name}...")
                mcp_response = make_api_call(
                    'POST',
                    '/use_tool',
                    json=tool_request_json # Send the JSON generated by the LLM
                )

                if mcp_response:
                    try:
                        tools_returning_email = ['read_emails', 'search_emails']

                        if tool_name in tools_returning_email:
                            # Process emails silently
                            if tool_name == 'read_emails' and 'emails' in mcp_response and isinstance(mcp_response.get('emails'), list):
                                for email_item in mcp_response['emails']:
                                    if isinstance(email_item, dict) and 'body' in email_item:
                                        raw_body = email_item.get('body', '')
                                        if raw_body:
                                            cleaned_body = clean_email_content(raw_body)
                                            email_item['body'] = cleaned_body
                                    
                                    # Convert body_html to body_text if body_text is missing
                                    if isinstance(email_item, dict) and 'body_html' in email_item and (not email_item.get('body_text') or not email_item.get('body_text').strip()):
                                        html_content = email_item.get('body_html', '')
                                        if html_content:
                                            email_item['body_text'] = clean_email_content(html_content)

                            elif tool_name == 'search_emails' and 'results' in mcp_response and isinstance(mcp_response.get('results'), list):
                                for email_item in mcp_response['results']:
                                    if isinstance(email_item, dict) and 'body' in email_item:
                                        raw_body = email_item.get('body', '')
                                        if raw_body:
                                            cleaned_body = clean_email_content(raw_body)
                                            email_item['body'] = cleaned_body
                                    
                                    # Convert body_html to body_text if body_text is missing
                                    if isinstance(email_item, dict) and 'body_html' in email_item and (not email_item.get('body_text') or not email_item.get('body_text').strip()):
                                        html_content = email_item.get('body_html', '')
                                        if html_content:
                                            email_item['body_text'] = clean_email_content(html_content)
                    
                    except Exception as clean_e:
                        print(f"Error processing email content: {clean_e}")
                    
                    # Use our new display function instead of raw JSON dump
                    display_clean_email_response(mcp_response, tool_name)
                else:
                    print("Failed to execute tool or get response from MCP server.")
            else:
                print("Could not generate a valid tool request from your input.")


if __name__ == "__main__":
    main()