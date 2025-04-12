import os
from dotenv import load_dotenv

load_dotenv()

MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8000")

OLLAMA_API_URL = os.getenv('BASE_URL')
MODEL_NAME = os.getenv('MODEL_NAME', "llama3.1:8b-instruct-q4_K_M")

REDIRECT_URI = os.getenv('REDIRECT_URI', 'http://localhost:8989/callback')
REDIRECT_PORT = int(os.getenv('REDIRECT_PORT', '8989'))
SCOPES = os.getenv('SCOPES', '').split()
CLIENT_SECRETS_FILE = os.getenv('CLIENT_SECRETS_FILE')

TOKEN_FILE = "gmail_token.json"

AUTH_TIMEOUT = 300
STATE_TIMEOUT = 5

TOKEN_FILE_PERMISSIONS = 0o600