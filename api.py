import json
import requests
from auth import get_active_access_token
from config import MCP_SERVER_URL

session = requests.Session()

def make_api_call(method, endpoint, **kwargs):
    access_token = get_active_access_token()
    if not access_token:
        print("Authentication required or token invalid.")
        return None

    headers = kwargs.pop('headers', {})
    headers['Authorization'] = f"Bearer {access_token}"
    
    if 'json' in kwargs and 'Content-Type' not in headers:
        headers['Content-Type'] = 'application/json'

    url = f"{MCP_SERVER_URL}/{endpoint.lstrip('/')}"

    try:
        response = session.request(method, url, headers=headers, **kwargs)

        if response.status_code == 401:
            print("Server reported token is invalid/expired (401).")
            return None

        response.raise_for_status()

        if response.status_code == 204:  # No Content
            return {"success": True, "message": "Operation successful (No Content)"}
            
        # Parse JSON response
        try:
            return response.json()
        except json.JSONDecodeError:
            if response.ok:
                return {
                    "success": True, 
                    "message": "Operation successful", 
                    "content": response.text
                }
            else:
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