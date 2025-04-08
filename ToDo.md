# Project Breakdown: Email AI Assistant (Detailed Steps)

This document outlines the detailed step-by-step plan for building the Email AI Assistant project, assuming development occurs on the Windows machine (potentially via remote access like RDP/Chrome Remote Desktop).

## Phase 0: Remote Setup (If Applicable)

1.  Set up remote access (e.g., Microsoft Remote Desktop, Chrome Remote Desktop) if developing from another machine (like the M1 Mac).
2.  Ensure the connection is stable and usable.

## Phase 1: Environment Setup - On Windows

1.  **Install Python:** Download from python.org or use Windows Store. Ensure `pip` is included and Python is added to your system PATH during installation. Verify with `python --version` and `pip --version` in Command Prompt or PowerShell.
2.  **Install Git:** Download Git for Windows (git-scm.com).
3.  **Install IDE:** Install Visual Studio Code (code.visualstudio.com).
4.  **NVIDIA Driver:** Ensure you have the latest NVIDIA Game Ready or Studio Driver installed for your GTX 1660 (from NVIDIA's website).
5.  **Install Ollama:** Download and install Ollama for Windows (ollama.com). It handles CUDA dependencies internally for GPU usage, simplifying things.
6.  **Project Folder:** Create a main folder for your project (e.g., `C:\dev\email-ai-assistant`).
7.  **Virtual Environment:** Open VS Code (or Command Prompt) in your project folder. Create and activate a Python virtual environment:
    ```bash
    python -m venv .venv
    .\.venv\Scripts\activate
    ```
    *(You should see `(.venv)` preceding your prompt)*
8.  **Initial Libraries:** Install core libraries needed later:
    ```bash
    pip install requests python-dotenv openai # openai library used for Ollama's API
    pip install streamlit # For the UI
    pip install fastapi uvicorn[standard] # For the MCP server
    pip install beautifulsoup4 # Useful for stripping HTML from emails
    # Add email libraries later when needed (Phase 4)
    ```

## Phase 2: Local LLM Deployment & Testing - On Windows

1.  **Start Ollama:** Ollama usually runs as a background service after installation. Check the system tray.
2.  **Pull Llama 3 Model:** Open Command Prompt/PowerShell:
    ```bash
    ollama pull llama3:8b-instruct
    ```
    *(This assumes you want the 8B instruct model. Wait for download)*
3.  **Test via CLI:**
    ```bash
    ollama run llama3:8b-instruct "Briefly explain the concept of a large language model."
    ```
    *(Verify you get a sensible response)*
4.  **Test Ollama API:** Create a small Python script (`test_ollama_api.py`) in your project:
    ```python
    import openai

    client = openai.OpenAI(
        base_url='http://localhost:11434/v1',
        api_key='ollama', # required, but Ollama doesn't verify it
    )

    try:
        response = client.chat.completions.create(
            model="llama3:8b-instruct",
            messages=[{"role": "user", "content": "Why is the sky blue?"}],
            max_tokens=100
        )
        print(response.choices[0].message.content)
    except Exception as e:
        print(f"Error connecting to Ollama API: {e}")

    ```
    Run it: `python test_ollama_api.py`. Verify you get a response.

## Phase 3: MCP Server (Email Backend) - On Windows

* *This is the most complex part, involving OAuth and email protocols.*
1.  **Design API Structure:** Plan your FastAPI endpoints. A minimal structure could be:
    * `POST /authenticate` (To initiate OAuth flow)
    * `GET /oauth_callback` (Handles redirect from email provider)
    * `GET /tools` (Lists available email tools like "read_emails", "send_email")
    * `POST /use_tool` (Executes a specific tool with parameters)
2.  **OAuth Setup:**
    * Choose your provider (e.g., Gmail or Outlook/Microsoft 365).
    * Go to Google Cloud Console or Azure Active Directory portal.
    * Create a new project/application registration.
    * Enable the relevant API (Gmail API or Microsoft Graph API).
    * Create OAuth 2.0 Credentials (Client ID, Client Secret).
    * Configure Redirect URIs (e.g., `http://localhost:8000/oauth_callback` - port must match where your FastAPI server runs).
    * **Store Credentials Securely:** Use environment variables (`.env` file with `python-dotenv`) or a proper secrets management solution. **Do not commit secrets to Git.**
3.  **Install Email/OAuth Libraries:**
    * **Gmail:** `pip install google-api-python-client google-auth-oauthlib google-auth-httplib2`
    * **Outlook/M365:** `pip install msal requests`
    * **Generic IMAP/SMTP:** Python's built-in `imaplib`, `smtplib` (more complex auth handling needed).
4.  **Implement OAuth Flow:** Use the installed libraries to handle:
    * Generating the authorization URL.
    * Handling the callback request to exchange the authorization code for access and refresh tokens.
    * **Securely Storing Tokens:** Store the refresh token associated with the user (or your single account). Access tokens are short-lived and can be obtained using the refresh token.
5.  **Implement Email Tools:** Create functions for each tool you want:
    * `read_emails(credentials, ...)`: Uses the stored/refreshed credentials to connect via API/IMAP and fetch emails based on filters. Parse content (e.g., use `beautifulsoup4` to get text from HTML emails).
    * `send_email(credentials, to, subject, body)`: Uses credentials to send via API/SMTP.
    * `search_emails(credentials, query)`: Implement search functionality.
6.  **Build FastAPI Endpoints:** Wrap your tool functions and OAuth logic within FastAPI routes. Use dependency injection for handling credentials.
7.  **Run Server:** `uvicorn main:app --reload --port 8000` (assuming your FastAPI app is in `main.py`).

## Phase 4: MCP Client Logic - On Windows

1.  **Purpose:** This module will interact with *your* MCP Server, not directly with Ollama initially (though it orchestrates the call *to* Ollama *via* the MCP server concept, or by calling Ollama after getting context *from* the MCP server). The exact MCP flow can vary; a simple start is: UI -> Client -> MCP Server (gets email data) -> Client -> Ollama (processes data) -> Client -> UI.
2.  **Structure:** Create Python functions:
    * `get_email_context(filters)`: Calls your MCP Server's `/use_tool` endpoint for `read_emails` or `search_emails`.
    * `call_llm_with_context(prompt, context)`: Takes user prompt and context from the step above, formats it, and sends it to the Ollama API (like in Phase 2, Step 4).
    * `draft_email_reply(context)`: Calls LLM to generate a draft.
    * `send_draft(draft_details)`: Calls your MCP Server's `/use_tool` endpoint for `send_email`.
3.  **Interaction:** Use the `requests` library to make HTTP calls to your running FastAPI MCP Server (e.g., `http://localhost:8000/use_tool`).

## Phase 5: User Interface (Streamlit) - On Windows

1.  **Create UI File:** Create `app.py`.
2.  **Import Libraries:** `import streamlit as st` and functions from your MCP Client module.
3.  **Layout:**
    * `st.title("Email AI Assistant")`
    * Use `st.text_input` for user queries/prompts.
    * Use `st.button` for actions (e.g., "Fetch Recent Emails", "Search", "Draft Reply", "Send").
    * Use `st.text_area` or `st.markdown` to display email content and LLM responses.
    * Use `st.session_state` to maintain conversation history or fetched email data between interactions.
4.  **Connect Logic:**
    * Button clicks call functions in your MCP Client module.
    * Display results returned by the client functions.
    * Handle the initial OAuth authentication step if needed (e.g., a button that redirects to your MCP server's `/authenticate` endpoint).
5.  **Run UI:** `streamlit run app.py`. Open the displayed URL (usually `http://localhost:8501`) in your browser on the Windows machine (visible via your remote session).

## Phase 6: Integration, Testing & Refinement - On Windows

1.  **Integration:** Ensure the UI, MCP Client, MCP Server, Ollama, and Email backend work together seamlessly. Test the full request-response cycle.
2.  **Testing:**
    * Unit tests for MCP server tool logic.
    * Integration tests for the MCP client/server interaction.
    * End-to-end tests via the UI (common scenarios: reading new mail, searching, drafting simple replies).
    * Test OAuth token refresh logic.
    * Test error handling (e.g., email server down, invalid credentials, LLM errors).
3.  **Optimization:**
    * Profile LLM inference speed. Consider smaller models if too slow.
    * Optimize email fetching (e.g., fetch only necessary headers first).
    * Cache results where appropriate (e.g., list of folders).

## (Optional) Phase 7: Personalization/Fine-tuning

1.  **Data Collection:** Export your own emails (e.g., MBOX format).
2.  **Data Preprocessing:** Clean and format data into instruction/response pairs suitable for fine-tuning (e.g., "Draft a reply to this email: [Email Content] \n Reply: [Your Drafted Reply]"). This requires significant effort and careful privacy handling.
3.  **Fine-tuning:** Use frameworks like `axolotl`, `trl`, or Hugging Face's `Trainer` to fine-tune the local Llama 3 model on your prepared dataset. This requires significant VRAM and time.
4.  **Evaluation:** Assess if the fine-tuned model performs better on your specific tasks (e.g., matching your writing style).