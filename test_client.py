import requests
import openai
import json
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

def test_mcp_server():
    try:
        response = requests.get(f"{MCP_SERVER_URL}/")
        if response.status_code == 200:
            print("MCP Server is running!")
            print(f"Response: {response.json()}")
            return True
        else:
            print(f"MCP Server returned unexpected status: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Failed to connect to MCP Server: {str(e)}")
        return False

def test_list_tools():
    try:
        response = requests.get(f"{MCP_SERVER_URL}/tools")
        if response.status_code == 200:
            print("Successfully retrieved tools!")
            tools = response.json().get("tools", [])
            print(f"Available tools: {[tool['name'] for tool in tools]}")
            return True
        else:
            print(f"Failed to retrieve tools: {response.status_code}")
            return False
    except Exception as e:
        print(f"Error retrieving tools: {str(e)}")
        return False

def test_ollama():
    try:
        response = llm_client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": "Hello, are you working? Reply with a short message."}],
            max_tokens=50
        )
        
        if response.choices and len(response.choices) > 0:
            print("Ollama is responding!")
            print(f"Response: {response.choices[0].message.content}")
            return True
        else:
            print("Ollama returned empty response")
            return False
    except Exception as e:
        print(f"Failed to connect to Ollama: {str(e)}")
        return False
    
def test_integration():
    try:
        # Test reading emails
        tool_request = {
            "tool_name": "read_emails",
            "parameters": {
                "limit": 5,
                "user_id": "default_user"
            }
        }
        
        tool_response = requests.post(f"{MCP_SERVER_URL}/use_tool", json=tool_request)
        if tool_response.status_code != 200:
            print(f"Failed to use tool: {tool_response.status_code}")
            print(f"Error details: {tool_response.text}")
            return False

        response_data = tool_response.json()
        emails = response_data.get("emails", [])
        print(f"Retrieved {len(emails)} real emails from Gmail")
        
        # Print email subjects
        for i, email in enumerate(emails):
            print(f"Email {i+1}: {email.get('subject', '(No subject)')}")
        
        # Test searching
        search_request = {
            "tool_name": "search_emails",
            "parameters": {
                "query": "important",
                "limit": 2,
                "user_id": "default_user"
            }
        }
        
        search_response = requests.post(f"{MCP_SERVER_URL}/use_tool", json=search_request)
        if search_response.status_code == 200:
            search_data = search_response.json()
            results = search_data.get("results", [])
            print(f"\nFound {len(results)} emails matching search query 'important'")
            
        return True
    
    except Exception as e:
        print(f"Integration test failed: {str(e)}")
        return False

if __name__ == "__main__":
    print("=" * 50)
    print("INBOX-GENIE TEST CLIENT")
    print("=" * 50)
    print()
    
    # Run the tests
    print("\n--- Testing MCP Server connection ---")
    server_ok = test_mcp_server()
    
    if server_ok:
        print("\n--- Testing available tools ---")
        test_list_tools()
    
    print("\n--- Testing Ollama connection ---")
    ollama_ok = test_ollama()
    
    if server_ok and ollama_ok:
        print("\n--- Testing integration between MCP server and Ollama ---")
        test_integration()
    
    print("\nTests completed!")