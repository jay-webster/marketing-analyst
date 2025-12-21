import streamlit as st
import asyncio

# Import our modules
import utils
import agent

st.set_page_config(page_title="Marketing Analyst AI", page_icon="🕵️‍♀️", layout="wide")

# 1. Security Check
if not utils.check_password():
    st.stop()

# 2. Chat History Setup
if "messages" not in st.session_state:
    st.session_state.messages = []


# --- THE "GOOGLE" CENTER LAYOUT LOGIC ---
def handle_search():
    """Callback to move center-search text into chat history"""
    user_input = st.session_state.center_search
    if user_input:
        st.session_state.messages.append({"role": "user", "content": user_input})
        # Clear the input
        st.session_state.center_search = ""


# If history is empty, show the "Google Style" Landing Page
if not st.session_state.messages:

    # SPACER 1: Push the Title down from the top of the browser
    st.markdown("<br><br>", unsafe_allow_html=True)

    # Title & Subtitle
    st.markdown(
        "<h1 style='text-align: center;'>🕵️‍♀️ Marketing Analyst Agent</h1>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<h5 style='text-align: center;'><i>I read websites so you don't have to.</i></h5>",
        unsafe_allow_html=True,
    )

    # SPACER 2: Push the Search Box away from the Title
    st.markdown("<br><br><br>", unsafe_allow_html=True)

    # Centered Search Box using Columns
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.text_input(
            "Enter a URL to analyze:",
            key="center_search",
            on_change=handle_search,
            placeholder="e.g. pulsarplatform.com",
            label_visibility="collapsed",  # Hides the tiny label for a cleaner look
        )
        # Center the caption too
        st.markdown(
            "<p style='text-align: center; color: grey;'>Press Enter to start analysis</p>",
            unsafe_allow_html=True,
        )

# --- THE "CHAT" INTERFACE LOGIC ---
else:
    # 3. Header (Smaller now)
    st.title("🕵️‍♀️ Marketing Analyst Agent")

    # 4. Display History
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # 5. Run Logic (If the last message is from User, reply!)
    last_msg = st.session_state.messages[-1]
    if last_msg["role"] == "user":
        with st.chat_message("assistant"):
            try:
                # Run the agent using the last message content
                response_text = asyncio.run(
                    agent.run_agent_turn(last_msg["content"], st.session_state.messages)
                )

                st.markdown(response_text)
                st.session_state.messages.append(
                    {"role": "assistant", "content": response_text}
                )

                # PDF Export
                if response_text:
                    st.markdown("---")
                    pdf_bytes = utils.create_pdf(response_text)
                    st.download_button(
                        "📄 Download Strategy PDF",
                        pdf_bytes,
                        "marketing_strategy.pdf",
                        "application/pdf",
                    )

            except Exception as e:
                st.error(f"An error occurred: {e}")

    # 6. Bottom Chat Input (For follow-up questions)
    if prompt := st.chat_input("Ask a follow-up question..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        st.rerun()  # Force reload to trigger the logic above
