# Inbox-Genie

**Status: Experimental**

I built Inbox-Genie to summarize and manage Gmail entirely on my own machine. It calls the Gmail API for mail access and a local Llama 3.1 model (via Ollama) for summarization, so email content stays on the machine it runs on rather than going to a third-party LLM API.

## What it does

- Summarizes recent emails and builds inbox digests from a CLI
- Authenticates against Gmail with OAuth 2.0 (PKCE) and refreshes tokens automatically
- Runs a small FastAPI server that separates the model (local LLM), the context (Gmail data), and the tool-calling logic between them
- Exposes the assistant through both an HTTP API and a command-line client

## Layout

- `mcp_server.py`, `routes.py`, `api.py` — FastAPI server exposing email tools
- `gmail_oauth_handler.py`, `auth.py`, `auth_utils.py` — OAuth flow and token handling
- `gmail_tools.py`, `email_utils.py`, `email_summarizer.py` — Gmail access and summarization logic
- `llm_utils.py`, `llm_cli.py`, `cli.py` — local LLM calls and the CLI entry point

## Setup

1. `python -m venv .venv && .\.venv\Scripts\activate` then `pip install -r requirements.txt`
2. Install [Ollama](https://ollama.com) and pull the model: `ollama pull llama3.1:8b-instruct-q4_K_M`
3. In Google Cloud Console, create OAuth 2.0 credentials for the Gmail API and download them as `client_secret.json` in the project root (this file is git-ignored — never commit it)
4. Create a `.env`:
   ```
   BASE_URL=http://localhost:11434/v1
   MODEL_NAME=llama3.1:8b-instruct-q4_K_M
   MCP_SERVER_URL=http://localhost:8000
   CLIENT_SECRETS_FILE=client_secret.json
   REDIRECT_URI=http://localhost:8989/callback
   REDIRECT_PORT=8989
   SCOPES=https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/gmail.send https://www.googleapis.com/auth/gmail.modify
   ```

## Usage

```bash
python mcp_server.py      # start the server
python llm_cli.py         # in a second terminal
```

Example commands: `summarize my last 5 emails`, `search for emails about meetings`, `show my unread emails`, `create a digest of my last 10 emails`.

## Notes

The internal "model / context / protocol" split here was my own design vocabulary from when I built this, not an implementation of Anthropic's Model Context Protocol spec — the naming overlap is coincidental. This covers the basic summarize/digest/search flows; it is a personal tool, not a maintained library, and I have not hardened it for untrusted input or production use.

## License

No license file yet — treat as all-rights-reserved until one is added.
