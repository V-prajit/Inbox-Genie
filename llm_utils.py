import json
import openai

def get_llm_client(api_url):
    if not api_url:
        print("Warning: LLM API URL not configured in environment.")
        return None
        
    try:
        # Initialize OpenAI client with Ollama API URL
        client = openai.OpenAI(
            base_url=api_url,
            api_key="ollama",  # Ollama doesn't check API key but requires one
        )
        
        # Test connection by listing models
        client.models.list()
        print(f"LLM Client configured successfully at {api_url}")
        return client
        
    except Exception as e:
        print(f"Error configuring LLM client: {e}")
        return None

def get_llm_tool_request(user_input, tool_definitions, llm_client, model_name):
    if not llm_client:
        print("LLM client is not configured. Cannot process request.")
        return None
        
    if not tool_definitions:
        print("Tool definitions are not available. Cannot process request.")
        return None

    # Construct the system prompt for the LLM
    prompt_system = f"""You are an expert AI assistant named Inbox Genie. Your task is to understand a user's request related to managing their Gmail emails and convert it into a specific JSON format to call an API tool.

You have the following tools available:
{json.dumps(tool_definitions, indent=2)}

COMMON USER REQUESTS AND HOW TO HANDLE THEM:
1. "Show my emails" → read_emails with default parameters
2. "Show my last 5 emails" → read_emails with limit=5
3. "Show my unread emails" → read_emails with unread_only=true
4. "Search for emails about meetings" → search_emails with query="meetings"
5. "Send an email to john@example.com" → send_email with appropriate parameters

Based on the user's request, identify the single most appropriate tool to use and construct a JSON object with the required 'tool_name' and 'parameters'.

Rules:
- Only output the JSON object. Do not include any other text, explanation, or formatting like ```json ... ```.
- Ensure all required parameters for the chosen tool are included in the JSON.
- For 'read_emails': 
  * Extract numbers mentioned (e.g., "show last 3 emails" → limit=3)
  * If "unread" is mentioned, set unread_only=true
  * Default limit is 5 if not specified

- For 'search_emails':
  * Extract search terms (e.g., "find emails about projects" → query="projects")
  * For queries like "from John", convert to proper search syntax (query="from:John")
  * Default limit is 5 if not specified

- For 'send_email':
  * Ensure 'to', 'subject', and 'body' are filled correctly
  * If user request is unclear, set "error" field instead

- If the user's request is unclear or doesn't match a tool, output: {{"error": "Request unclear or does not match available tools."}}
"""

    prompt_user = f"User request: \"{user_input}\"\n\nGenerate the JSON ToolRequest:"

    try:
        # Call the LLM with the prompts
        llm_response = llm_client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": prompt_system},
                {"role": "user", "content": prompt_user}
            ],
            max_tokens=500,
            temperature=0.1  # Low temperature for more deterministic output
        )
        
        # Extract the response text
        llm_output = llm_response.choices[0].message.content.strip()

        try:
            if llm_output.startswith("```json"):
                llm_output = llm_output.split("```json")[1].split("```")[0].strip()
            elif llm_output.startswith("```"):
                llm_output = llm_output.split("```")[1].strip()

            tool_request_json = json.loads(llm_output)

            if "error" in tool_request_json:
                print(f"I don't understand that email command: {tool_request_json['error']}")
                print("Try something like 'show my emails', 'search for emails about meetings', etc.")
                return None
                 
            if "tool_name" not in tool_request_json or "parameters" not in tool_request_json:
                print("Sorry, I couldn't interpret your request. Please try a different phrasing.")
                return None

            print(f"Processing: {tool_request_json.get('tool_name')}...")
            return tool_request_json

        except json.JSONDecodeError:
            print("Sorry, I couldn't process that request. Please try again with different wording.")
            return None

    except Exception as e:
        print(f"Error calling LLM: {e}")
        return None

def summarize_email(email_data, llm_client, model_name, max_words=50):
    try:
        from_email = email_data.get('from_email', 'Unknown')
        subject = email_data.get('subject', '(No subject)')
        text_content = email_data.get('body_text', '')
        
        if len(text_content) > 2000:
            text_content = text_content[:2000] + "..."
        
        prompt = f"""
        Summarize the following email in under {max_words} words:
        
        From: {from_email}
        Subject: {subject}
        
        {text_content}
        """
        
        response = llm_client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=100 
        )
        
        summary = response.choices[0].message.content.strip()
        return {
            "from": from_email,
            "subject": subject,
            "summary": summary
        }
    except Exception as e:
        print(f"Error summarizing email: {str(e)}")
        return {
            "from": email_data.get('from_email', 'Unknown'),
            "subject": email_data.get('subject', '(No subject)'),
            "summary": f"Failed to summarize: {str(e)}"
        }

def draft_reply(email_data, llm_client, model_name):
    try:
        from_email = email_data.get('from_email', 'Unknown')
        subject = email_data.get('subject', '(No subject)')
        text_content = email_data.get('body_text', '')
        
        if len(text_content) > 2000:
            text_content = text_content[:2000] + "..."
        
        prompt = f"""
        Draft a professional reply to the following email:
        
        From: {from_email}
        Subject: {subject}
        
        {text_content}
        
        Your reply:
        """
        
        response = llm_client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500
        )
        
        reply = response.choices[0].message.content.strip()
        return reply
    except Exception as e:
        print(f"Error drafting reply: {str(e)}")
        return f"Failed to draft reply: {str(e)}"