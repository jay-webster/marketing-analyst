import streamlit as st
import asyncio
import agent
import utils

st.set_page_config(page_title="Market Intelligence Agent", layout="wide")

# --- AUTHENTICATION ---
if not utils.check_password():
    st.stop()

# --- HEADER ---
st.title("🕵️‍♀️ Market Intelligence Agent")
st.markdown("---")

# --- TABS ---
tab1, tab2 = st.tabs(["🔎 Research Analyst", "⚙️ Manage Robot"])

# ==========================================
# TAB 1: MANUAL RESEARCH (Original App)
# ==========================================
with tab1:
    st.header("Ad-Hoc Competitor Analysis")

    col1, col2 = st.columns([3, 1])
    with col1:
        target_url = st.text_input("Enter Competitor URL", placeholder="example.com")
    with col2:
        analyze_btn = st.button("Analyze Site", type="primary")

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    if analyze_btn and target_url:
        with st.status("🤖 AI Agent Working...", expanded=True) as status:
            st.write("🌐 Accessing website...")
            initial_prompt = f"Analyze {target_url}. Provide a strategic summary of their homepage value proposition."

            try:
                response = asyncio.run(
                    agent.run_agent_turn(initial_prompt, st.session_state.chat_history)
                )
                st.session_state.chat_history.append(
                    {"role": "user", "content": initial_prompt}
                )
                st.session_state.chat_history.append(
                    {"role": "assistant", "content": response}
                )
                status.update(
                    label="✅ Analysis Complete!", state="complete", expanded=False
                )
            except Exception as e:
                st.error(f"Error: {e}")
                status.update(label="❌ Failed", state="error")

    # Display Chat
    for message in st.session_state.chat_history:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Follow-up Input
    if st.session_state.chat_history:
        user_input = st.chat_input("Ask a follow-up question...")
        if user_input:
            with st.chat_message("user"):
                st.markdown(user_input)
            st.session_state.chat_history.append(
                {"role": "user", "content": user_input}
            )

            with st.spinner("Thinking..."):
                response = asyncio.run(
                    agent.run_agent_turn(user_input, st.session_state.chat_history)
                )
                with st.chat_message("assistant"):
                    st.markdown(response)
                st.session_state.chat_history.append(
                    {"role": "assistant", "content": response}
                )

            # PDF Download Button
            full_text = "\n\n".join(
                [
                    f"**{m['role'].upper()}**: {m['content']}"
                    for m in st.session_state.chat_history
                ]
            )
            pdf_bytes = utils.create_pdf(full_text)
            st.download_button(
                "📄 Download Report as PDF",
                data=pdf_bytes,
                file_name="research_report.pdf",
                mime="application/pdf",
            )

# ==========================================
# TAB 2: ROBOT MANAGER (New Feature)
# ==========================================
with tab2:
    st.header("⚙️ Daily Monitor Settings")
    st.info("Manage the list of competitors the Cloud Robot watches every morning.")

    # Load current list from Cloud
    current_competitors = utils.get_competitors()

    # Layout: List on left, Add form on right
    col_list, col_add = st.columns([2, 1])

    with col_list:
        st.subheader(f"Current Watchlist ({len(current_competitors)})")

        # Display as a clean table with delete buttons
        for comp in current_competitors:
            c1, c2 = st.columns([4, 1])
            c1.markdown(f"**{comp}**")
            if c2.button("🗑️", key=f"del_{comp}", help=f"Remove {comp}"):
                new_list = [x for x in current_competitors if x != comp]
                if utils.save_competitors(new_list):
                    st.success(f"Removed {comp}")
                    st.rerun()
                else:
                    st.error("Failed to save changes.")

    with col_add:
        st.subheader("Add New Target")
        with st.form("add_comp_form"):
            new_comp = st.text_input("Domain (e.g. competitors.com)")
            submitted = st.form_submit_button("Add to Watchlist")

            if submitted and new_comp:
                clean_comp = (
                    new_comp.replace("https://", "")
                    .replace("http://", "")
                    .replace("www.", "")
                    .strip()
                )
                if clean_comp in current_competitors:
                    st.warning("Already in the list!")
                else:
                    current_competitors.append(clean_comp)
                    if utils.save_competitors(current_competitors):
                        st.success(f"Added {clean_comp}")
                        st.rerun()
                    else:
                        st.error("Failed to save to Cloud.")
