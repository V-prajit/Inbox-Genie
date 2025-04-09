import requests
import openai
from dotenv import load_dotenv
import os

load_dotenv()

MCP_SERVER_URL = "http://localhost:8000"
OLLAMA_API_URL = os.getenv('BASE_URL')
MODEL_NAME = "llama3.1:8b-instruct-q4_K_M"

llm_client = openai.OpenAI(
    base_url=OLLAMA_API_URL,
    api_key="ollama",
)

def fetch_recent_emails(limit=5, unread_only=False, session=None):
    """Fetch the most recent emails from Gmail via the MCP server."""
    try:
        tool_request = {
            "tool_name": "read_emails",
            "parameters": {
                "limit": limit,
                "unread_only": unread_only
            }
        }
        
        # Use the provided session or create a new one
        if session is None:
            session = requests.Session()
        
        response = session.post(f"{MCP_SERVER_URL}/use_tool", json=tool_request)
        if response.status_code == 200:
            return response.json().get("emails", [])
        elif response.status_code == 401:
            print("Authentication failed. Please authenticate first.")
            return []
        else:
            print(f"Error fetching emails: {response.status_code}")
            print(f"Response: {response.text}")
            return []
    except Exception as e:
        print(f"Exception when fetching emails: {str(e)}")
        return []

def summarize_email(email_data, max_words=50):
    """Use LLM to summarize a single email."""
    try:
        # Extract relevant info from email
        from_email = email_data.get('from_email', 'Unknown')
        subject = email_data.get('subject', '(No subject)')
        text_content = email_data.get('body_text', '')
        
        # If text is too long, truncate it to prevent token overflow
        if len(text_content) > 2000:
            text_content = text_content[:2000] + "..."
        
        # Create prompt for LLM
        prompt = f"""
        Summarize the following email in under {max_words} words:
        
        From: {from_email}
        Subject: {subject}
        
        {text_content}
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
            "summary": summary
        }
    except Exception as e:
        print(f"Error summarizing email: {str(e)}")
        return {
            "from": email_data.get('from_email', 'Unknown'),
            "subject": email_data.get('subject', '(No subject)'),
            "summary": f"Failed to summarize: {str(e)}"
        }

def summarize_recent_emails(limit=5, unread_only=False, session=None):
    """Fetch and summarize recent emails."""
    emails = fetch_recent_emails(limit, unread_only, session=session)
    
    if not emails:
        return "No emails found or couldn't connect to email server."
    
    print(f"Fetched {len(emails)} emails. Summarizing...")
    summaries = []
    
    for email in emails:
        summary = summarize_email(email)
        summaries.append(summary)
    
    return summaries

if __name__ == "__main__":
    print("Summarizing your 5 most recent emails...")
    results = summarize_recent_emails(5)
    
    if isinstance(results, str):
        print(results)
    else:
        print("\n=== Email Summaries ===\n")
        for i, result in enumerate(results, 1):
            print(f"Email {i}:")
            print(f"From: {result['from']}")
            print(f"Subject: {result['subject']}")
            print(f"Summary: {result['summary']}")
            print()