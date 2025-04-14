from fastapi import APIRouter, HTTPException, Depends, Body, Query, status
from pydantic import BaseModel, Field
from typing import Dict, Optional, Any, List
from google.oauth2.credentials import Credentials

import gmail_oauth_handler as gmail_oauth_handler
import gmail_tools as gmail_tools
from auth_utils import verify_token
import email_summarizer  # Import the summarizer module

class ToolRequest(BaseModel):
    tool_name: str
    parameters: Dict[str, Any]

class TokenRequest(BaseModel):
    grant_type: str = Field(..., pattern="authorization_code")
    code: str
    redirect_uri: str
    code_verifier: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    expires_in: Optional[int] = None
    token_type: str = "Bearer"
    scope: Optional[str] = None
    id_token: Optional[str] = None

class EmailSummary(BaseModel):
    from_email: str
    subject: str
    date: Optional[str] = None
    summary: str

router = APIRouter()

@router.get("/")
async def root():
    return {"message": "Inbox Genie MCP Server is running (Token Auth Mode)"}

@router.get("/authenticate")
async def authenticate(
    redirect_uri: str = Query(...),
    state: str = Query(...), #
    code_challenge: str = Query(...),
    code_challenge_method: str = Query("S256", pattern="S256") 
):
    """Initiates the OAuth flow by providing the Google Auth URL."""
    try:
        auth_url = gmail_oauth_handler.get_gmail_auth_url(
            state=state,
            redirect_uri=redirect_uri,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method
        )
        return {"auth_url": auth_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate auth URL: {str(e)}")


@router.post("/token", response_model=TokenResponse)
async def get_token(request_body: TokenRequest = Body(...)):
    """Exchanges the authorization code for tokens."""
    if request_body.grant_type != "authorization_code":
        raise HTTPException(status_code=400, detail="Unsupported grant_type")

    try:
        token_data = gmail_oauth_handler.exchange_code_for_tokens(
            code=request_body.code,
            code_verifier=request_body.code_verifier,
            redirect_uri=request_body.redirect_uri
        )
        return TokenResponse(**token_data)
    except HTTPException as http_exc: 
        raise http_exc
    except Exception as e:
        print(f"Unexpected error during token exchange: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error during token exchange.")


@router.post("/revoke")
async def revoke_auth(refresh_token: str = Body(..., embed=True)):
    """Revokes Google access using the provided refresh token."""
    success = gmail_oauth_handler.revoke_access_with_token(refresh_token)
    if success:
        return {"message": "Access revocation initiated successfully."}
    else:
        raise HTTPException(status_code=400, detail="Failed to revoke access. Token might be invalid or already revoked.")


@router.get("/tools")
async def list_tools(creds: Credentials = Depends(verify_token)):
    return {
        "tools": [
             {
                "name": "read_emails",
                "description": "Read emails from the inbox",
                "parameters": {
                    "limit": "Number of emails to fetch (default: 10)",
                    "folder": "Email folder to fetch from (default: INBOX)",
                    "unread_only": "Only fetch unread emails (default: false)"
                }
            },
            {
                "name": "send_email",
                "description": "Send an email",
                "parameters": {
                    "to": "Recipient email address",
                    "subject": "Email subject",
                    "body": "Email body content",
                    "html": "Whether body is HTML (default: false)"
                }
            },
            {
                "name": "search_emails",
                "description": "Search for emails",
                "parameters": {
                    "query": "Search query",
                    "limit": "Maximum number of results (default: 10)"
                }
            },
            {
                "name": "summarize_emails",
                "description": "Fetch and summarize emails",
                "parameters": {
                    "limit": "Number of emails to summarize (default: 5)",
                    "max_words": "Maximum words per summary (default: 50)",
                    "unread_only": "Only summarize unread emails (default: false)"
                }
            },
            {
                "name": "create_digest",
                "description": "Create a digest of recent emails",
                "parameters": {
                    "limit": "Number of emails to include in digest (default: 10)",
                    "unread_only": "Only include unread emails (default: false)"
                }
            }
        ]
    }

@router.post("/use_tool")
async def use_tool(
    request: ToolRequest,
    creds: Credentials = Depends(verify_token) 
):
    tool_name = request.tool_name
    params = request.parameters

    try:
        if tool_name == "read_emails":
            limit = int(params.get("limit", 10))
            folder = params.get("folder", "INBOX")
            unread_only = params.get("unread_only", False)
            emails = gmail_tools.read_emails(
                credentials=creds, 
                limit=limit,
                folder=folder,
                unread_only=unread_only
            )
            return {"emails": emails}

        elif tool_name == "send_email":
            required_params = ["to", "subject", "body"]
            if not all(param in params for param in required_params):
                missing = [p for p in required_params if p not in params]
                raise HTTPException(status_code=400, detail=f"Missing required parameters: {', '.join(missing)}")

            to = params["to"]
            subject = params["subject"]
            body = params["body"]
            html = params.get("html", False)
            result = gmail_tools.send_email(
                credentials=creds, # Pass creds
                to=to,
                subject=subject,
                body=body,
                html=html
            )
            if not result.get('success'):
                 raise HTTPException(status_code=502, detail=f"Gmail API Error: {result.get('message', 'Unknown error sending email')}")
            return result

        elif tool_name == "search_emails":
            if "query" not in params:
                raise HTTPException(status_code=400, detail="Missing required parameter: query")

            query = params["query"]
            limit = int(params.get("limit", 10))
            emails = gmail_tools.search_emails(
                credentials=creds, # Pass creds
                query=query,
                limit=limit
            )
            return {"query": query, "results": emails}
            
        elif tool_name == "summarize_emails":
            limit = int(params.get("limit", 5))
            max_words = int(params.get("max_words", 50))
            unread_only = params.get("unread_only", False)
            
            # First, fetch the emails using the existing read_emails function
            emails = gmail_tools.read_emails(
                credentials=creds, 
                limit=limit,
                folder="INBOX",
                unread_only=unread_only
            )
            
            if not emails:
                return {"summaries": [], "message": "No emails found to summarize"}
                
            # Use the email_summarizer to summarize each email
            summaries = []
            for email in emails:
                summary = email_summarizer.summarize_email(email, max_words)
                summaries.append(summary)
                
            return {"summaries": summaries}
            
        elif tool_name == "create_digest":
            limit = int(params.get("limit", 10))
            unread_only = params.get("unread_only", False)
            
            # First, fetch the emails
            emails = gmail_tools.read_emails(
                credentials=creds, 
                limit=limit,
                folder="INBOX",
                unread_only=unread_only
            )
            
            if not emails:
                return {"digest": "No emails found to create digest", "email_count": 0}
                
            # Create the digest using the email_summarizer module
            digest = email_summarizer.create_email_digest(emails)
            
            return {"digest": digest, "email_count": len(emails)}

        else:
            raise HTTPException(status_code=400, detail=f"Unsupported tool: {tool_name}")


    except gmail_tools.HttpError as google_error:
        if google_error.resp.status in [401, 403]:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Authentication error with Google API: {google_error}",
                headers={"WWW-Authenticate": "Bearer error=\"invalid_token\""},
             )
        else:
             raise HTTPException(status_code=502, detail=f"Google API Error: {google_error}")
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        print(f"Error in use_tool ({tool_name}): {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error processing tool '{tool_name}'.")