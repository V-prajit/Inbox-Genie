# Inbox-Genie
## AI-Powered Email Assistant That Respects Your Privacy

Inbox-Genie is an AI-powered email assistant that runs entirely on your machine. It uses Gmail's API to access your emails and a local Large Language Model (LLM) to process and summarize them, ensuring your data never leaves your computer.

## Key Features
- **Privacy-First Architecture**: All email processing happens locally - no data sent to external servers
- **Secure Authentication**: Implements Gmail OAuth 2.0 with PKCE for secure account access
- **Local LLM Processing**: Uses Llama 3.1 via Ollama running on your machine
- **MCP Design Pattern**: Based on Anthropic's Model-Context-Protocol architecture
- **Command-Line Interface**: Simple and efficient CLI for quick email management
- **FastAPI Server**: Handles secure API communication with Gmail
- **Email Summarization**: Generate concise summaries of your emails
- **Email Digests**: Create comprehensive digests of your inbox
- **Automatic Token Refresh**: Seamless authentication without constant re-login

## Architecture
Inbox-Genie follows Anthropic's Model-Context-Protocol (MCP) architecture, which cleanly separates:
- **Model**: The LLM (Llama 3.1) running locally via Ollama
- **Context**: Your email data fetched securely via Gmail's API
- **Protocol**: The interaction logic between the components

This architecture ensures modularity, security, and privacy.

## Prerequisites
- Python 3.8+
- NVIDIA GPU recommended (GTX 1660 or better) for faster LLM inference
- Gmail account

## Installation and Setup
1.  Clone the repository:
    ```bash
    git clone [https://github.com/V-prajit/Inbox-Genie.git](https://github.com/V-prajit/Inbox-Genie.git)
    cd Inbox-Genie
    ```
2.  Create a virtual environment and install dependencies:
    ```bash
    python -m venv .venv
    .\.venv\Scripts\activate
    pip install -r requirements.txt
    ```
3.  Install Ollama:
    Download from ollama.com and follow installation instructions.
4.  Pull the Llama 3.1 model:
    ```bash
    ollama pull llama3.1:8b-instruct-q4_K_M
    ```
5.  Set up your Gmail OAuth credentials:
    * Go to the Google Cloud Console
    * Create a new project
    * Enable the Gmail API
    * Create OAuth 2.0 credentials (Client ID and Client Secret)
    * Configure Redirect URIs (e.g., `http://localhost:8989/callback`)
    * Download the credentials as `client_secret.json` and place it in the project directory
6.  Create a `.env` file with the following:
    ```dotenv
    BASE_URL=http://localhost:11434/v1
    MODEL_NAME=llama3.1:8b-instruct-q4_K_M
    MCP_SERVER_URL=http://localhost:8000
    CLIENT_SECRETS_FILE=client_secret.json
    REDIRECT_URI=http://localhost:8989/callback
    REDIRECT_PORT=8989
    SCOPES=[https://www.googleapis.com/auth/gmail.readonly](https://www.googleapis.com/auth/gmail.readonly) [https://www.googleapis.com/auth/gmail.send](https://www.googleapis.com/auth/gmail.send) [https://www.googleapis.com/auth/gmail.modify](https://www.googleapis.com/auth/gmail.modify)
    ```

## Usage
1.  Start the MCP server:
    ```bash
    python mcp_server.py
    ```
2.  In a new terminal, start the CLI:
    ```bash
    python llm_cli.py
    ```

## Example Commands
summarize my last 5 emails
search for emails about meetings
show my unread emails
create a digest of my last 10 emails

## Privacy and Security
Inbox-Genie is designed with privacy as a top priority:

- Your emails are processed entirely on your local machine
- The application uses OAuth 2.0 with PKCE for secure authentication
- Tokens are stored securely and refreshed automatically
- No data is sent to external servers for processing
- All communication with Gmail's API is encrypted
- You can revoke access at any time