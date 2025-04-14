import html2text
from email.parser import BytesParser
from email import policy

def clean_email_content(raw_content):
    """
    Clean and convert email content to readable text.
    Handles both HTML and plain text emails.
    """
    body = ""
    is_html_only = False
    
    if isinstance(raw_content, str) and '<' not in raw_content and '>' not in raw_content:
        return raw_content
    
    try:
        # Convert to bytes if needed
        if isinstance(raw_content, str):
            raw_bytes = raw_content.encode('utf-8', errors='ignore')
        elif isinstance(raw_content, bytes):
            raw_bytes = raw_content
        else:
            raw_bytes = str(raw_content).encode('utf-8', errors='ignore')

        # Parse email message
        msg = BytesParser(policy=policy.default).parsebytes(raw_bytes)

        # Handle multipart messages
        if msg.is_multipart():
            # Try to get plain text part first
            plain_part = msg.get_body(preferencelist=('plain',))
            if plain_part:
                payload = plain_part.get_payload(decode=True)
                charset = plain_part.get_content_charset() or 'utf-8'
                body = payload.decode(charset, errors='replace')
            else:
                html_part = msg.get_body(preferencelist=('html',))
                if html_part:
                    payload = html_part.get_payload(decode=True)
                    charset = html_part.get_content_charset() or 'utf-8'
                    body = payload.decode(charset, errors='replace')
                    is_html_only = True
        # Handle single part messages
        elif msg.get_content_type().startswith('text/'):
            payload = msg.get_payload(decode=True)
            charset = msg.get_content_charset() or 'utf-8'
            body = payload.decode(charset, errors='replace')
            if msg.get_content_type() == 'text/html':
                is_html_only = True
        else:
            is_html_only = True

    except Exception as e:
        is_html_only = True
        if isinstance(raw_content, bytes):
            try:
                body = raw_content.decode('utf-8', errors='replace')
            except UnicodeDecodeError:
                body = raw_content.decode('latin-1', errors='replace')
        elif isinstance(raw_content, str):
            body = raw_content
        else:
            body = str(raw_content)
    
    # Convert HTML to plain text if needed
    if is_html_only or ('<' in body and '>' in body and 
                       ('<html' in body.lower() or '<p>' in body.lower() or 
                        '<div' in body.lower() or '<br' in body.lower())):
        try:
            h = html2text.HTML2Text()
            h.ignore_links = False
            h.body_width = 0  # Don't wrap text
            plain_text = h.handle(body)
            return plain_text.strip()
        except Exception:
            return body.strip()
    else:
        return body.strip()

def display_clean_email_response(response_data, tool_name, limit=None, show_full=False):
    """Display email results from various tools."""
    
    # Based on the tool_name, use the appropriate display function
    if tool_name == 'read_emails' or tool_name == 'search_emails':
        display_email_list(response_data, tool_name, limit, show_full)
    elif tool_name == 'summarize_emails':
        display_email_summaries(response_data, limit)
    elif tool_name == 'create_digest':
        display_email_digest(response_data)
    else:
        print(f"\nUnknown tool response for '{tool_name}'")

def display_email_list(response_data, tool_name, limit=None, show_full=False):
    """Display a list of emails from read_emails or search_emails tools."""
    print("\n" + "="*60)
    print(" EMAIL RESULTS ".center(60, "="))
    print("="*60)
    
    emails = []
    if tool_name == 'read_emails':
        emails = response_data.get('emails', [])
    elif tool_name == 'search_emails':
        emails = response_data.get('results', [])
    
    if not emails:
        print("\nNo emails found.")
        return
    
    if limit and isinstance(limit, int) and limit > 0:
        emails = emails[:limit]
    
    for i, email in enumerate(emails, 1):
        print(f"\n{'-'*60}")
        print(f" EMAIL {i} ".center(60, "-"))
        print(f"{'-'*60}")
        
        print(f"From: {email.get('from_email', 'Unknown')}")
        print(f"Subject: {email.get('subject', '(No subject)')}")
        print(f"Date: {email.get('date', 'Unknown')}")
        
        if email.get('unread', False):
            print("Status: UNREAD")
        
        print(f"{'-'*40}")
        
        body_text = email.get('body_text', '')
        if not body_text or not body_text.strip():
            body_text = "(No text content available)"
        
        if not show_full and len(body_text) > 2000:
            print(f"Body:\n{body_text[:2000]}")
            print("\n... (Content truncated) ...")
            print(f"\n[Email is {len(body_text)} characters long. Use 'show full emails' to see complete content.]")
        else:
            print(f"Body:\n{body_text}")
    
    print(f"\n{'-'*60}")
    print(f" End of Results: {len(emails)} email(s) displayed ".center(60, "-"))
    print(f"{'-'*60}")

def display_email_summaries(response_data, limit=None):
    """Display email summaries from summarize_emails tool."""
    print("\n" + "="*60)
    print(" EMAIL SUMMARIES ".center(60, "="))
    print("="*60)
    
    summaries = response_data.get('summaries', [])
    
    if not summaries:
        print("\nNo email summaries found.")
        return
    
    if limit and isinstance(limit, int) and limit > 0:
        summaries = summaries[:limit]
    
    for i, summary in enumerate(summaries, 1):
        print(f"\n{'-'*60}")
        print(f" SUMMARY {i} ".center(60, "-"))
        print(f"{'-'*60}")
        
        print(f"From: {summary.get('from', summary.get('from_email', 'Unknown'))}")
        print(f"Subject: {summary.get('subject', '(No subject)')}")
        print(f"Date: {summary.get('date', 'Unknown')}")
        print(f"\nSummary:\n{summary.get('summary', '(No summary available)')}")
    
    print(f"\n{'-'*60}")
    print(f" End of Summaries: {len(summaries)} email(s) summarized ".center(60, "-"))
    print(f"{'-'*60}")

def display_email_digest(response_data):
    """Display email digest from create_digest tool."""
    print("\n" + "="*60)
    email_count = response_data.get('email_count', 0)
    print(f" EMAIL DIGEST ({email_count} emails) ".center(60, "="))
    print("="*60)
    
    digest = response_data.get('digest', '')
    
    if not digest:
        print("\nNo digest content available.")
        return
    
    print(f"\n{digest}")
    
    print(f"\n{'-'*60}")
    print(" End of Digest ".center(60, "-"))
    print(f"{'-'*60}")

def process_email_response(response, tool_name):
    """Process and clean email content from various tools."""
    try:
        # Add all tools that return email content
        tools_returning_email = ['read_emails', 'search_emails', 'summarize_emails']
        if tool_name not in tools_returning_email:
            return
            
        email_list = None
        if tool_name == 'read_emails' and 'emails' in response:
            email_list = response['emails']
        elif tool_name == 'search_emails' and 'results' in response:
            email_list = response['results']
        elif tool_name == 'summarize_emails' and 'summaries' in response:
            email_list = response['summaries']
            
        if not email_list or not isinstance(email_list, list):
            return
            
        for email_item in email_list:
            if not isinstance(email_item, dict):
                continue
                
            if 'body' in email_item:
                raw_body = email_item.get('body', '')
                if raw_body:
                    email_item['body'] = clean_email_content(raw_body)
                
            if ('body_html' in email_item and 
                (not email_item.get('body_text') or not email_item.get('body_text').strip())):
                html_content = email_item.get('body_html', '')
                if html_content:
                    email_item['body_text'] = clean_email_content(html_content)
                    
    except Exception as e:
        print(f"Error processing email content: {e}")