import sys
import json
from dotenv import load_dotenv

from config import (
    MCP_SERVER_URL, 
    OLLAMA_API_URL, 
    MODEL_NAME,
    TOKEN_FILE
)
from auth import (
    authenticate, 
    get_active_access_token,
    clear_tokens, 
    load_tokens
)
from api import make_api_call
from llm_utils import get_llm_client, get_llm_tool_request
from email_utils import display_clean_email_response, process_email_response

# Global cache for tool definitions
TOOL_DEFINITIONS_CACHE = None

def fetch_tool_definitions():
    global TOOL_DEFINITIONS_CACHE
    if TOOL_DEFINITIONS_CACHE:
        return TOOL_DEFINITIONS_CACHE

    print("Fetching available tools from server...")
    response_data = make_api_call('GET', '/tools')

    if response_data and 'tools' in response_data:
        print("Successfully fetched tool definitions.")
        TOOL_DEFINITIONS_CACHE = response_data['tools']
        return TOOL_DEFINITIONS_CACHE
    else:
        print("Failed to fetch tool definitions from server.")
        return None

def handle_reauth_command():
    print("Forcing re-authentication...")
    clear_tokens()
    if authenticate():
        print("Re-fetching tool definitions after re-authentication...")
        fetch_tool_definitions()
    else:
        print("Re-authentication failed.")

def handle_revoke_command():
    print("Attempting to revoke access...")
    token_data = load_tokens()
    refresh_token = token_data.get('refresh_token') if token_data else None
    if not refresh_token:
        print("No refresh token found to revoke. Cannot proceed.")
        return

    revoke_payload = {'refresh_token': refresh_token}
    response_data = make_api_call('POST', '/revoke', json=revoke_payload)

    if response_data:
        print(response_data.get("message", "Revocation request processed by server."))
        clear_tokens()
    else:
        print("Failed to send revocation request or server denied it.")

def process_email_request(user_input, tool_definitions, llm_client):
    if not llm_client:
        print("LLM client not available. Please configure OLLAMA_API_URL.")
        return
    if not tool_definitions:
        print("Tool definitions not available. Cannot process request via LLM.")
        return

    tool_request_json = get_llm_tool_request(user_input, tool_definitions, llm_client, MODEL_NAME)

    if not tool_request_json:
        print("Could not generate a valid tool request from your input.")
        return

    tool_name = tool_request_json.get('tool_name')
    print(f"Executing tool: {tool_name}...")
    
    mcp_response = make_api_call(
        'POST',
        '/use_tool',
        json=tool_request_json
    )

    if not mcp_response:
        print("Failed to execute tool or get response from MCP server.")
        return

    process_email_response(mcp_response, tool_name)
    
    display_clean_email_response(mcp_response, tool_name)

def main():
    # Load environment variables
    load_dotenv()
    
    print("="*50)
    print("INBOX GENIE - LLM CLI")
    print("="*50)

    llm_client = get_llm_client(OLLAMA_API_URL)
    if not llm_client and OLLAMA_API_URL:
        print("Warning: Failed to initialize LLM client. Some features will be unavailable.")

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

    tool_definitions = fetch_tool_definitions()
    if not tool_definitions:
        print("Could not retrieve tool definitions. Functionality will be limited.")

    print("\nEnter your email requests in natural language.")
    print("Type 'reauth' to authenticate again, 'revoke' to remove access, or 'exit'.")
    
    while True:
        print("\n" + "-"*50)
        try:
            user_input = input("Your request: ").strip()
        except EOFError:
            print("\nExiting...")
            break

        if not user_input:
            continue

        command = user_input.lower()

        if command in ["exit", "quit", "q"]:
            print("Exiting Inbox Genie. Goodbye!")
            break
        elif command == "reauth":
            handle_reauth_command()
        elif command == "revoke":
            handle_revoke_command()
        else:
            process_email_request(user_input, tool_definitions, llm_client)

if __name__ == "__main__":
    main()