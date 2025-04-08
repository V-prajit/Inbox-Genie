from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from typing import Dict, List, Optional, Any

class ToolRequest(BaseModel):
    tool_name: str
    parameters: Dict[str, Any]

class EmailData(BaseModel):
    id: str
    from_email: str
    subject: str
    date: str
    body_text: str
    body_html: Optional[str] = None

router = APIRouter()

# TODO: storing token in memory for now, look into if that is the best way later
tokens = {}

@router.get("/")
async def root():
    return {"message": "Inbox Genie MCP Server is running"}

@router.post("/authenticate")
async def authenticate(provider: str):
    if provider.lower() == "gmail":
        # TODO: Implement Gmail OAuth flow. For now, return a placeholder
        return {"auth_url": "https://accounts.google.com/o/oauth2/auth?placeholder=true"}
    elif provider.lower() in ["outlook", "microsoft", "microsoft365"]:
        # TODO: Implement Microsoft OAuth flow
        return {"auth_url": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize?placeholder=true"}
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")
    
@router.get("/oauth_callback")
async def oauth_callback(code: str, state: Optional[str] = None):
    # TODO: Exchange code for tokens and store them. This is a placeholder implementation
    user_id = "default_user"
    tokens[user_id] = {
        "access_token": f"placeholder_access_token_{code[:5]}",
        "refresh_token": f"placeholder_refresh_token_{code[:5]}",
    }
    
    return RedirectResponse(url="/auth_success")

@router.get("/auth_success")
async def auth_success():
    return {"message": "Authentication successful! You can close this window and return to the app."}

@router.get("/tools")
async def list_tools():
    return{
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
                "name": "send_emails",
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
            }
        ]
    }

@router.post("/use_tool")
async def use_tool(request: ToolRequest):
    tool_name = request.tool_name
    params = request.parameters
    user_id = "default_user" # TODO: get from auth token

    if user_id not in tokens:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    if tool_name == "read_emails":
        #Actually fetch the emails, return Mock Data for now
        return {
            "emails": [
                {
                   "id": "email1",
                    "from_email": "john.doe@example.com",
                    "subject": "Meeting tomorrow",
                    "date": "2025-04-07T15:30:00Z",
                    "body_text": "Let's meet tomorrow at 10am to discuss the project." 
                },
                {
                    "id": "email2",
                    "from_email": "support@service.com",
                    "subject": "Your subscription renewal",
                    "date": "2025-04-07T12:15:00Z",
                    "body_text": "Your subscription will renew on April 15, 2025."
                }
            ]
        }
    
    elif tool_name == "send_email":
        required_params = ["to", "subject", "body"]
        for param in required_params:
            if param not in params:
                raise HTTPException(status_code=400, detail=f"Missing required parameter: {param}")
        
        # TODO: implement actually sending the mail
        return {
            "success": True,
            "message": f"Email to {params['to']} queued for sending",
            "email_id": "mock_email_id_12345"
        }
    
    elif tool_name == "search_emails":
        if "query" not in params:
            raise HTTPException(status_code=400, detail="Missing required parameter: query")
        # TODO: Implement actual email search
        query = params["query"]
        return {
            "query": query,
            "results": [
                {
                    "id": "search1",
                    "from_email": "alice@example.com",
                    "subject": f"About the {query}",
                    "date": "2025-04-05T10:25:00Z",
                    "body_text": f"I wanted to discuss the {query} with you."
                }
            ]  
        }
    
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported tool: {tool_name}")