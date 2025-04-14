import sys
import json
from dotenv import load_dotenv
import openai

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

def summarize_email(email_data, llm_client, max_words=50):
    """Summarize a single email using the LLM."""
    try:
        # Extract relevant info from email
        from_email = email_data.get('from_email', 'Unknown')
        subject = email_data.get('subject', '(No subject)')
        text_content = email_data.get('body_text', '')
        date = email_data.get('date', '')
        
        # If text is too long, truncate it to prevent token overflow
        if len(text_content) > 2000:
            text_content = text_content[:2000] + "..."
        
        # Create prompt for LLM
        prompt = f"""
        Summarize the following email in {max_words} words or less:
        
        From: {from_email}
        Subject: {subject}
        Date: {date}
        
        {text_content}
        
        Provide only the key points and important details.
        """
        
        response = llm_client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=100  # Limiting tokens to keep summary short
        )
        
        summary = response.choices[0].message.content.strip()
        return {
            "from": from_email,
            "subject": subject,
            "date": date,
            "summary": summary
        }
    except Exception as e:
        print(f"Error summarizing email: {str(e)}")
        return {
            "from": email_data.get('from_email', 'Unknown'),
            "subject": email_data.get('subject', '(No subject)'),
            "date": email_data.get('date', ''),
            "summary": f"Failed to summarize: {str(e)}"
        }

def fetch_and_summarize_emails(limit=5, max_words=50):
    """
    Use the summarize_emails tool to fetch and summarize recent emails.
    This version uses the server-side summarization tool rather than doing it in the client.
    """
    print(f"Fetching and summarizing the {limit} most recent emails...")

    summarize_request = {
        "tool_name": "summarize_emails",
        "parameters": {
            "limit": limit,
            "max_words": max_words
        }
    }

    # Use the authenticated API call helper
    response_data = make_api_call('POST', '/use_tool', json=summarize_request)

    if response_data is None:
        print("Failed to fetch email summaries.")
        return

    summaries = response_data.get("summaries", [])

    if not summaries:
        print("No emails found or no summaries returned by server.")
        return

    # Display summaries
    print("\n" + "="*60)
    print(" EMAIL SUMMARIES ".center(60, "="))
    print("="*60)

    for i, summary_data in enumerate(summaries, 1):
        print(f"\nEmail {i}:")
        print(f"  From: {summary_data.get('from', summary_data.get('from_email', 'Unknown'))}")
        print(f"  Subject: {summary_data.get('subject', '(No subject)')}")
        print(f"  Date: {summary_data.get('date', 'Unknown')}")
        print(f"  Summary: {summary_data.get('summary', '(No summary)')}")
        print("-" * 40)

def create_email_digest(emails, llm_client, max_emails=5):
    """
    Create a daily digest of the most important emails.
    """
    if not llm_client or not emails:
        return "Daily digest unavailable - LLM client not configured or no emails provided"
    
    # Limit number of emails to process
    emails_to_process = emails[:max_emails]
    
    # Create simplified email representations for the prompt
    email_texts = []
    for i, email in enumerate(emails_to_process):
        from_email = email.get('from_email', 'Unknown')
        subject = email.get('subject', '(No subject)')
        text = email.get('body_text', '')
        
        if len(text) > 400:  # Keep each email brief for the digest context
            text = text[:400] + "..."
            
        email_texts.append(f"Email {i+1}:\nFrom: {from_email}\nSubject: {subject}\nContent: {text}\n")
    
    all_emails = "\n".join(email_texts)
    
    # Create the prompt for the daily digest
    prompt = f"""
    Create a concise daily email digest based on these {len(emails_to_process)} emails.
    Organize them by importance and topic, highlighting key information.
    
    {all_emails}
    
    Format the digest like this:
    # EMAIL DIGEST
    
    ## High Priority
    - [Brief descriptions of important emails]
    
    ## Other Messages
    - [Brief descriptions of other emails]
    
    ## Action Items
    - [Any clear tasks or responses needed]
    """
    
    try:
        response = llm_client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500
        )
        
        digest = response.choices[0].message.content.strip()
        return digest
    except Exception as e:
        print(f"Error creating daily digest: {str(e)}")
        return f"Failed to create daily digest: {str(e)}"

def generate_email_digest(limit=10):
    """
    Use the create_digest tool to generate a digest of recent emails.
    This version uses the server-side digest creation rather than doing it in the client.
    """
    print(f"Creating digest from {limit} most recent emails...")

    digest_request = {
        "tool_name": "create_digest",
        "parameters": {
            "limit": limit
        }
    }

    # Use the authenticated API call helper
    response_data = make_api_call('POST', '/use_tool', json=digest_request)

    if not response_data:
        print("Failed to create email digest.")
        return

    digest = response_data.get("digest", "No digest content returned.")
    email_count = response_data.get("email_count", 0)
    
    print("\n" + "="*60)
    print(f" EMAIL DIGEST ({email_count} emails) ".center(60, "="))
    print("="*60 + "\n")
    print(digest)
    print("\n" + "="*60)

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
    print("Type 'summarize', 'digest', 'reauth', 'revoke', or 'exit'.")
    
    while True:
        print("\n" + "-"*50)
        print("Available commands:")
        print("1. summarize [limit] [max_words] - Summarize recent emails")
        print("   Example: summarize 10 75  - Summarize 10 emails with 75 words max")
        print("2. digest [limit] - Create a daily digest of recent emails")
        print("   Example: digest 10  - Create digest from 10 most recent emails")
        print("3. reauth - Force re-authentication")
        print("4. revoke - Revoke Google access")
        print("5. search [query] - Search for specific emails")
        print("   Example: search meeting - Find emails about meetings")
        print("6. read [limit] - Show recent emails without summarizing")
        print("   Example: read 5 - Show the 5 most recent emails")
        print("7. unread - Show unread emails only")
        print("8. help - Show this help message")
        print("9. exit - Exit the application")
        print("10. Any other input will be interpreted as a specific request or general conversation")
        print("-"*50)
        
        try:
            user_input = input("Your request: ").strip()
        except EOFError:
            print("\nExiting...")
            break

        if not user_input:
            continue

        parts = user_input.lower().split()
        command = parts[0] if parts else ""

        if command in ["exit", "quit", "q"]:
            print("Exiting Inbox Genie. Goodbye!")
            break
            
        elif command == "reauth":
            handle_reauth_command()
            
        elif command == "revoke":
            handle_revoke_command()
            
        elif command == "summarize":
            # Extract limit and max_words if provided
            limit = 5  # Default
            max_words = 50  # Default
            
            # Check for limit
            if len(parts) > 1 and parts[1].isdigit():
                limit = int(parts[1])
                if limit <= 0 or limit > 50:
                    print("Please enter a number between 1 and 50 for limit.")
                    continue
            
            # Check for max_words
            if len(parts) > 2 and parts[2].isdigit():
                max_words = int(parts[2])
                if max_words <= 0 or max_words > 200:
                    print("Please enter a number between 1 and 200 for max words.")
                    continue
            
            fetch_and_summarize_emails(limit, max_words)
            
        elif command == "digest":
            # Extract limit if provided
            limit = 10  # Default
            if len(parts) > 1 and parts[1].isdigit():
                limit = int(parts[1])
                if limit <= 0 or limit > 20:
                    print("Please enter a number between 1 and 20.")
                    continue
            
            generate_email_digest(limit)
            
        elif command == "read":
            # Directly use the read_emails tool
            limit = 5  # Default
            if len(parts) > 1 and parts[1].isdigit():
                limit = int(parts[1])
            
            read_request = {
                "tool_name": "read_emails",
                "parameters": {
                    "limit": limit
                }
            }
            
            response_data = make_api_call('POST', '/use_tool', json=read_request)
            if response_data:
                display_clean_email_response(response_data, "read_emails")
                
        elif command == "unread":
            # Directly use the read_emails tool with unread_only=True
            unread_request = {
                "tool_name": "read_emails",
                "parameters": {
                    "limit": 5,
                    "unread_only": True
                }
            }
            
            response_data = make_api_call('POST', '/use_tool', json=unread_request)
            if response_data:
                display_clean_email_response(response_data, "read_emails")
                
        elif command == "search" and len(parts) > 1:
            # Get the search query from the rest of the input
            query = ' '.join(parts[1:])
            
            search_request = {
                "tool_name": "search_emails",
                "parameters": {
                    "query": query,
                    "limit": 5
                }
            }
            
            response_data = make_api_call('POST', '/use_tool', json=search_request)
            if response_data:
                display_clean_email_response(response_data, "search_emails")
                
        elif command == "help":
            # Just continue to show the help text again
            continue
            
        else:
            # Use the LLM to determine what the user wants to do
            if llm_client:
                # This is where we would have the complex LLM classification logic
                # to determine whether to summarize, digest, or process as an email request
                # But now we'll just check if it's an email related query and
                # send direct email requests to the server
                
                try:
                    # Simple classification to determine if this is an email-related query
                    classification_prompt = f"""
                    Determine if the following user query is related to email operations or if it's a general conversation query.
                    
                    User query: "{user_input}"
                    
                    If this query is about reading, searching, sending, summarizing emails or creating a digest,
                    respond with exactly "EMAIL_RELATED". 
                    
                    If this is a general conversation or question not related to email operations,
                    respond with exactly "GENERAL_QUERY".
                    
                    Your response should be only one of these two options, nothing else.
                    """
                    
                    classification_response = llm_client.chat.completions.create(
                        model=MODEL_NAME,
                        messages=[{"role": "user", "content": classification_prompt}],
                        max_tokens=20,
                        temperature=0.1
                    )
                    
                    classification = classification_response.choices[0].message.content.strip()
                    
                    if "EMAIL_RELATED" in classification:
                        # Process as an email request through the server
                        process_email_request(user_input, tool_definitions, llm_client)
                    else:
                        # Handle as a general conversation
                        response = llm_client.chat.completions.create(
                            model=MODEL_NAME,
                            messages=[{"role": "user", "content": user_input}],
                            max_tokens=500
                        )
                        print("\nResponse:")
                        print(response.choices[0].message.content)
                        
                except Exception as e:
                    print(f"Error processing query: {e}")
                    # Fall back to tool processing if classification fails
                    process_email_request(user_input, tool_definitions, llm_client)
            else:
                print("LLM client not available. Trying to process as email request...")
                process_email_request(user_input, tool_definitions, llm_client)

if __name__ == "__main__":
    main()