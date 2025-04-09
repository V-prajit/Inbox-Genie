import base64
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from bs4 import BeautifulSoup
from typing import List, Dict, Any, Optional
import email.message
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

def read_emails(credentials, limit=10, folder="INBOX", unread_only=False):
    try:
        service = build('gmail', 'v1', credentials=credentials)

        query = []
        if folder.upper() != "INBOX":
            query.append(f"in:{folder}")
        if unread_only:
            query.append("is:unread")

        query_string = " ".join(query) if query else " "

        results = service.users().messages().list(
            userId='me',
            q=query_string,
            maxResults=limit
        ).execute()

        messages = results.get('messages', [])

        emails = []
        for message in messages:
            msg = service.users().messages().get(
                userId='me',
                id=message['id'],
                format='full'
            ).execute()

            headers = msg['payload']['headers']
            subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), '(No subject)')
            from_email = next((h['value'] for h in headers if h['name'].lower() == 'from'), 'Unknown')
            date = next((h['value'] for h in headers if h['name'].lower() == 'date'), '')

            body_html, body_text = extract_body(msg['payload'])

            email_data = {
                'id': msg['id'],
                'threadId': msg['threadId'],
                'labelIds': msg.get('labelIds', []),
                'snippet': msg.get('snippet', ''),
                'from_email': from_email,
                'subject': subject,
                'date': date,
                'body_html': body_html,
                'body_text': body_text,
                'unread': 'UNREAD' in msg.get('labelIds', [])                
            }

            emails.append(email_data)

        return emails
    except HttpError as error:
        print(f'An error occurred: {error}')
        return []   
    

def extract_body(payload):
    html_body = None
    text_body = None
    
    if 'parts' in payload:
        for part in payload['parts']:
            mime_type = part.get('mimeType', '')
            
            if mime_type == 'text/html':
                data = part['body'].get('data', '')
                if data:
                    html_body = base64.urlsafe_b64decode(data).decode('utf-8')
            
            elif mime_type == 'text/plain':
                data = part['body'].get('data', '')
                if data:
                    text_body = base64.urlsafe_b64decode(data).decode('utf-8')
            
            elif 'parts' in part:
                html, text = extract_body(part)
                if html:
                    html_body = html
                if text:
                    text_body = text
    
    elif 'body' in payload and 'data' in payload['body']:
        data = payload['body']['data']
        body = base64.urlsafe_b64decode(data).decode('utf-8')
        
        if payload.get('mimeType') == 'text/html':
            html_body = body
        elif payload.get('mimeType') == 'text/plain':
            text_body = body

    if html_body and not text_body:
        soup = BeautifulSoup(html_body, 'html.parser')
        text_body = soup.get_text(separator=' ', strip=True)
    
    return html_body, text_body

def send_email(credentials, to, subject, body, html=False):
    try:
        service = build('gmail', 'v1', credentials=credentials)
        
        if html:
            message = MIMEMultipart('alternative')
            plain_text = BeautifulSoup(body, 'html.parser').get_text(separator=' ', strip=True)
            text_part = MIMEText(plain_text, 'plain')
            message.attach(text_part)
            html_part = MIMEText(body, 'html')
            message.attach(html_part)
        else:
            message = MIMEText(body)
        
        message['to'] = to
        message['subject'] = subject
        
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
        
        result = service.users().messages().send(
            userId='me', 
            body={'raw': raw}
        ).execute()
        
        return {
            'success': True,
            'message': f"Email sent successfully",
            'email_id': result['id']
        }
    except HttpError as error:
        return {
            'success': False,
            'message': f"An error occurred: {str(error)}"
        }

def search_emails(credentials, query, limit=10):
    try:
        service = build('gmail', 'v1', credentials=credentials)
        
        results = service.users().messages().list(
            userId='me', 
            q=query,
            maxResults=limit
        ).execute()
        
        messages = results.get('messages', [])
        
        if not messages:
            return []
        
        emails = []
        for message in messages:
            msg = service.users().messages().get(
                userId='me', 
                id=message['id'],
                format='full'
            ).execute()
            
            headers = msg['payload']['headers']
            subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), '(No subject)')
            from_email = next((h['value'] for h in headers if h['name'].lower() == 'from'), 'Unknown')
            date = next((h['value'] for h in headers if h['name'].lower() == 'date'), '')
            
            body_html, body_text = extract_body(msg['payload'])
            
            email_data = {
                'id': msg['id'],
                'threadId': msg['threadId'],
                'labelIds': msg.get('labelIds', []),
                'snippet': msg.get('snippet', ''),
                'from_email': from_email,
                'subject': subject,
                'date': date,
                'body_html': body_html,
                'body_text': body_text,
                'unread': 'UNREAD' in msg.get('labelIds', [])
            }
            
            emails.append(email_data)
        
        return emails
    except HttpError as error:
        print(f'An error occurred: {error}')
        return []