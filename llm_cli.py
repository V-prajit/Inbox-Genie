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

    if tool_name == 'summarize_emails':
        summaries = mcp_response.get("summaries", [])
        if not summaries:
            print("\nNo emails found or no summaries returned by server.")
            return
            
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
            
    elif tool_name == 'create_digest':
        digest = mcp_response.get("digest", "No digest content returned.")
        email_count = mcp_response.get("email_count", 0)
        
        print("\n" + "="*60)
        print(f" EMAIL DIGEST ({email_count} emails) ".center(60, "="))
        print("="*60 + "\n")
        print(digest)
        print("\n" + "="*60)
    else:
        process_email_response(mcp_response, tool_name)
        display_clean_email_response(mcp_response, tool_name)

def summarize_email(email_data, llm_client, max_words=50):
    try:
        from_email = email_data.get('from_email', 'Unknown')
        subject = email_data.get('subject', '(No subject)')
        text_content = email_data.get('body_text', '')
        date = email_data.get('date', '')
        
        if len(text_content) > 2000:
            text_content = text_content[:2000] + "..."
        
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
    print(f"Fetching and summarizing the {limit} most recent emails...")

    summarize_request = {
        "tool_name": "summarize_emails",
        "parameters": {
            "limit": limit,
            "max_words": max_words
        }
    }

    response_data = make_api_call('POST', '/use_tool', json=summarize_request)

    if response_data is None:
        print("Failed to fetch email summaries.")
        return

    summaries = response_data.get("summaries", [])

    if not summaries:
        print("No emails found or no summaries returned by server.")
        return

    print("\n" + "="*60)
    print(" EMAIL SUMMARIES ".center(60, "="))
    print("="*60)

    for i, summary_data in enumerate(summaries, 1):
        print(f"\n{'-'*60}")
        print(f" SUMMARY {i} ".center(60, "-"))
        print(f"{'-'*60}")
        
        print(f"From: {summary_data.get('from', summary_data.get('from_email', 'Unknown'))}")
        print(f"Subject: {summary_data.get('subject', '(No subject)')}")
        print(f"Date: {summary_data.get('date', 'Unknown')}")
        print(f"\nSummary:\n{summary_data.get('summary', '(No summary available)')}")
    
    print(f"\n{'-'*60}")
    print(f" End of Summaries: {len(summaries)} email(s) summarized ".center(60, "-"))
    print(f"{'-'*60}")

def create_email_digest(emails, llm_client, max_emails=5):
    if not llm_client or not emails:
        return "Daily digest unavailable - LLM client not configured or no emails provided"
    
    emails_to_process = emails[:max_emails]
    
    email_texts = []
    for i, email in enumerate(emails_to_process):
        from_email = email.get('from_email', 'Unknown')
        subject = email.get('subject', '(No subject)')
        text = email.get('body_text', '')
        
        if len(text) > 400: 
            text = text[:400] + "..."
            
        email_texts.append(f"Email {i+1}:\nFrom: {from_email}\nSubject: {subject}\nContent: {text}\n")
    
    all_emails = "\n".join(email_texts)
    
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
    print(f"Creating digest from {limit} most recent emails...")

    digest_request = {
        "tool_name": "create_digest",
        "parameters": {
            "limit": limit
        }
    }

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

def classify_user_input(user_input, llm_client, model_name):
    if not llm_client:
        return "EMAIL_RELATED"
        
    try:
        classification_prompt = f"""
        Determine if the following user query is related to email operations or if it's a general conversation query.
        
        User query: "{user_input}"
        
        EMAIL_RELATED queries include:
        - Reading emails (e.g., "show my emails", "get my latest messages")
        - Searching emails (e.g., "find emails about meetings", "search for emails from John")
        - Summarizing emails (e.g., "summarize my last 4 emails", "give me a summary of recent messages")
        - Creating digests (e.g., "create a digest of my emails", "make a summary of today's emails")
        - Sending emails (e.g., "send an email to John", "write a message to HR")
        - Checking for unread emails (e.g., "do I have any unread emails", "check my unread messages")
        - Any input that begins with words like: read, show, get, display, find, search, summarize, digest, send, write
        
        GENERAL_QUERY includes:
        - General questions not about email (e.g., "what's the weather today", "who is the president")
        - Conversation (e.g., "how are you", "tell me a joke")
        - Questions about the assistant (e.g., "what can you do", "who are you")
        
        If this query is related to email operations, respond with exactly "EMAIL_RELATED".
        If this is a general conversation or question not related to email operations, respond with exactly "GENERAL_QUERY".
        
        Your response should be only one of these two options, nothing else.
        """
        
        classification_response = llm_client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": classification_prompt}],
            max_tokens=20,
            temperature=0.1
        )
        
        classification = classification_response.choices[0].message.content.strip()
        
        if "GENERAL_QUERY" in classification:
            return "GENERAL_QUERY"
        else:
            return "EMAIL_RELATED"
            
    except Exception as e:
        print(f"Error in classification: {e}")
        return "EMAIL_RELATED"


def handle_user_input(user_input, tool_definitions, llm_client, model_name):
    if not llm_client:
        print("LLM client not available. Cannot process natural language requests.")
        return
        
    input_type = classify_user_input(user_input, llm_client, model_name)
    
    if input_type == "EMAIL_RELATED":
        process_email_request(user_input, tool_definitions, llm_client)
    else:
        try:
            response = llm_client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": user_input}],
                max_tokens=500
            )
            print("\nResponse:")
            print(response.choices[0].message.content)
        except Exception as e:
            print(f"Error getting response: {e}")

def main():
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
    print("Type 'reauth', 'revoke', 'exit', or 'help' for system commands.")
    
    while True:
        print("\n" + "-"*50)
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
            continue
            
        elif command == "revoke":
            handle_revoke_command()
            continue
            
        elif command == "help":
            print("\nAvailable commands:")
            print("- Natural language requests like:")
            print("  'summarize my last 4 emails'")
            print("  'search for emails about meetings'")
            print("  'show my unread emails'")
            print("  'create a digest of my last 7 emails'")
            print("- System commands:")
            print("  'reauth' - Force re-authentication")
            print("  'revoke' - Revoke Google access")
            print("  'exit' - Exit the application")
            print("  'help' - Show this help message")
            continue
        
        if llm_client:
            handle_user_input(user_input, tool_definitions, llm_client, MODEL_NAME)
        else:
            print("LLM client not available. Cannot process natural language requests.")

if __name__ == "__main__":
    main()