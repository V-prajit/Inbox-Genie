import streamlit as st
import requests
import email_summarizer

MCP_SERVER_URL = "http://localhost:8000"

def check_auth_status():
    try:
        response = requests.get(f"{MCP_SERVER_URL}/auth_status")
        if response.status_code == 200:
            data = response.json()
            return data.get("authenticated", False)
        return False
    except Exception as e:
        st.error(f"Error checking auth status: {str(e)}")
        return False

def get_auth_url():
    try:
        response = requests.get(f"{MCP_SERVER_URL}/authenticate", params={"provider": "gmail"})
        if response.status_code == 200:
            data = response.json()
            return data.get("auth_url")
        else:
            st.error(f"Error getting auth URL: {response.status_code}")
            st.text(response.text)
            return None
    except Exception as e:
        st.error(f"Error getting auth URL: {str(e)}")
        return None

def init_session_state():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if "email_summaries" not in st.session_state:
        st.session_state.email_summaries = []

def main():
    st.set_page_config(page_title="Inbox Genie", page_icon="📧")
    
    st.title("📧 Inbox Genie")
    st.subheader("Your AI Email Assistant")
    
    init_session_state()
    
    is_authenticated = check_auth_status()
    st.session_state.authenticated = is_authenticated
    
    if not st.session_state.authenticated:
        st.warning("You need to authenticate with Gmail to use Inbox Genie.")
        auth_url = get_auth_url()
        if auth_url:
            st.markdown(f"[Click here to authenticate with Gmail]({auth_url})")
            
        st.markdown("After authentication, come back and refresh this page.")
        st.button("Refresh after authentication", on_click=lambda: None)
    else:
        st.success("Connected to Gmail")
        
        st.markdown("---")
        col1, col2 = st.columns([3, 1])
        
        with col1:
            st.text_input("Ask Inbox Genie something:", 
                         value="summarize the last 5 emails", 
                         key="user_query",
                         label_visibility="collapsed")
        
        with col2:
            if st.button("Process"):
                query = st.session_state.user_query.lower()
                
                if "summarize" in query and ("email" in query or "mail" in query):
                    with st.spinner("Fetching and summarizing your emails..."):
                        limit = 5
                        for word in query.split():
                            if word.isdigit():
                                limit = int(word)
                                break
                                
                        summaries = email_summarizer.summarize_recent_emails(limit)
                        st.session_state.email_summaries = summaries
                else:
                    st.warning("I can only summarize emails at the moment. Try asking 'summarize the last 5 emails'")
        
        if st.session_state.email_summaries:
            st.markdown("## Email Summaries")
            
            if isinstance(st.session_state.email_summaries, str):
                st.info(st.session_state.email_summaries)
            else:
                for i, summary in enumerate(st.session_state.email_summaries, 1):
                    with st.expander(f"Email {i}: {summary['subject']}"):
                        st.write(f"**From:** {summary['from']}")
                        st.write(f"**Summary:** {summary['summary']}")

if __name__ == "__main__":
    main()