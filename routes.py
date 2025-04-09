from fastapi import APIRouter, HTTPException, Request, Depends, Cookie
from fastapi.responses import RedirectResponse, JSONResponse
from pydantic import BaseModel
from typing import Dict, List, Optional, Any
import gmail_oauth_handler
import gmail_tools

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

# Store user_id in cookies
async def get_user_id(request: Request, user_id: Optional[str] = Cookie(None)):
    return user_id

@router.get("/")
async def root():
    return {"message": "Inbox Genie MCP Server is running"}

@router.get("/authenticate")
async def authenticate(provider: str):
    if provider.lower() != "gmail":
        raise HTTPException(status_code=400, detail="Only Gmail is supported at this time")
        
    try:
        auth_url, state = gmail_oauth_handler.get_gmail_auth_url()
        return {"auth_url": auth_url, "state": state}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@router.get("/oauth_callback")
async def oauth_callback(code: str, state: Optional[str] = None):
    try:
        if not state:
            raise HTTPException(status_code=400, detail="Missing state parameter")
            
        if state not in gmail_oauth_handler.state_map:
            raise HTTPException(status_code=400, detail="Invalid state parameter")
            
        user_id = gmail_oauth_handler.handle_gmail_callback(code, state)
            
        # Set user_id in a cookie
        response = RedirectResponse(url="/auth_success")
        response.set_cookie(key="user_id", value=user_id, httponly=True)
        
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/auth_success")
async def auth_success(user_id: Optional[str] = Depends(get_user_id)):
    if not user_id or not gmail_oauth_handler.is_authenticated(user_id):
        return {"message": "Authentication failed. Please try again."}
        
    return {
        "message": "Authentication successful with Gmail! You can close this window and return to the app.",
        "user_id": user_id
    }

@router.get("/auth_status")
async def auth_status(user_id: Optional[str] = Depends(get_user_id)):
    if not user_id or not gmail_oauth_handler.is_authenticated(user_id):
        return {"authenticated": False}
        
    return {
        "authenticated": True,
        "provider": "gmail",
        "user_id": user_id
    }

@router.post("/revoke")
async def revoke_auth(user_id: Optional[str] = Depends(get_user_id)):
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
        
    success = gmail_oauth_handler.revoke_access(user_id)
    if success:
        response = JSONResponse(content={"message": "Access revoked successfully"})
        response.delete_cookie(key="user_id")
        return response
    else:
        raise HTTPException(status_code=400, detail="Failed to revoke access")

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
            }
        ]
    }

@router.post("/use_tool")
async def use_tool(request: ToolRequest, user_id: Optional[str] = Depends(get_user_id)):
    if not user_id or not gmail_oauth_handler.is_authenticated(user_id):
        raise HTTPException(status_code=401, detail="Authentication required")
    
    tool_name = request.tool_name
    params = request.parameters
    
    try:
        # Get Gmail credentials
        creds = gmail_oauth_handler.get_gmail_credentials(user_id)
        
        if tool_name == "read_emails":
            # Extract parameters with defaults
            limit = int(params.get("limit", 10))
            folder = params.get("folder", "INBOX")
            unread_only = params.get("unread_only", False)
            
            # Call the Gmail tool function
            emails = gmail_tools.read_emails(
                credentials=creds,
                limit=limit,
                folder=folder,
                unread_only=unread_only
            )
            
            return {"emails": emails}
        
        elif tool_name == "send_email":
            required_params = ["to", "subject", "body"]
            for param in required_params:
                if param not in params:
                    raise HTTPException(status_code=400, detail=f"Missing required parameter: {param}")
            
            # Extract parameters
            to = params["to"]
            subject = params["subject"]
            body = params["body"]
            html = params.get("html", False)
            
            # Call the Gmail tool function
            result = gmail_tools.send_email(
                credentials=creds,
                to=to,
                subject=subject,
                body=body,
                html=html
            )
            
            return result
        
        elif tool_name == "search_emails":
            if "query" not in params:
                raise HTTPException(status_code=400, detail="Missing required parameter: query")
            
            # Extract parameters
            query = params["query"]
            limit = int(params.get("limit", 10))
            
            # Call the Gmail tool function
            emails = gmail_tools.search_emails(
                credentials=creds,
                query=query,
                limit=limit
            )
            
            return {"query": query, "results": emails}
        
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported tool: {tool_name}")
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))