import streamlit as st
import os
import asyncio
import pandas as pd
from dotenv import load_dotenv
from google.cloud import firestore

# --- IMPORTS ---
import utils
import monitor
from monitor import run_daily_brief

load_dotenv()
st.set_page_config(page_title="Marketing Analyst Agent", page_icon="🕵️‍♂️", layout="wide")

# --- DATABASE CONNECTION ---
# We initialize this once to use across the app
try:
    project_id = os.getenv("PROJECT_ID")
    db = firestore.Client(project=project_id) if project_id else firestore.Client()
except Exception as e:
    db = None
    st.error(f"⚠️ Database Connection Error: {e}")

# --- AUTHENTICATION LOGIC ---
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")


def check_password():
    """Returns `True` if the user had the correct password."""

    def password_entered():
        if st.session_state["password"] == ADMIN_PASSWORD:
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.text_input(
            "Admin Password",
            type="password",
            on_change=password_entered,
            key="password",
        )
        return False
    elif not st.session_state["password_correct"]:
        st.text_input(
            "Admin Password",
            type="password",
            on_change=password_entered,
            key="password",
        )
        st.error("😕 Password incorrect")
        return False
    else:
        return True


# --- ADMIN FEATURE: DELETE HELPER ---
def delete_doc(collection, doc_id):
    try:
        db.collection(collection).document(doc_id).delete()
        st.toast(f"✅ Deleted {doc_id} from {collection}")
        # We don't rerun immediately to avoid jarring refreshes,
        # but the user will see it vanish on next action.
    except Exception as e:
        st.error(f"Error deleting: {e}")


# --- PAGE: ADMIN DASHBOARD ---
def show_admin_dashboard():
    st.title("🕵️‍♂️ Analyst Command Center")

    # Create Tabs for cleaner organization
    tab1, tab2, tab3 = st.tabs(
        ["🔭 Discovery & Add", "⚙️ Manage Competitors", "👥 Subscribers"]
    )

    # --- TAB 1: DISCOVERY (The New Logic) ---
    with tab1:
        st.subheader("Find New Competitors")
        st.info(
            "Uses 'Profile-First' logic: Profiles the target > Identifies Business Model > Finds Matches."
        )

        col1, col2 = st.columns([3, 1])
        with col1:
            new_competitor_domain = st.text_input(
                "Enter Target Domain (e.g., viamedia.ai):"
            )
        with col2:
            st.write("")  # Spacer
            st.write("")
            run_discovery = st.button("Analyze & Find", type="primary")

        if run_discovery:
            if not new_competitor_domain:
                st.warning("Please enter a domain.")
            else:
                with st.spinner(f"Agent is profiling {new_competitor_domain}..."):
                    try:
                        results = asyncio.run(
                            monitor.discover_competitors(new_competitor_domain)
                        )
                        st.session_state["discovery_results"] = results
                        st.success("Analysis Complete!")
                    except Exception as e:
                        st.error(f"Discovery Error: {e}")

        # Display Discovery Results
        if (
            "discovery_results" in st.session_state
            and st.session_state["discovery_results"]
        ):
            st.write("### 🎯 Suggested Matches")
            results = st.session_state["discovery_results"]
            if not results:
                st.warning("No matches found.")
            else:
                for comp in results:
                    with st.expander(
                        f"Found: {comp.get('name', 'Unknown')}", expanded=True
                    ):
                        st.write(f"**Domain:** {comp.get('domain')}")
                        st.write(f"**Reason:** {comp.get('reason')}")
                        if st.button(
                            f"Track {comp.get('name')}", key=f"add_{comp.get('domain')}"
                        ):
                            utils.add_competitor_to_db(comp.get("domain"))
                            st.success(f"Added {comp.get('name')}!")

        st.divider()
        with st.expander("Manually Add Domain (Skip Discovery)"):
            manual_domain = st.text_input("Domain to track directly:")
            if st.button("Add Manually"):
                utils.add_competitor_to_db(manual_domain)
                st.success(f"Added {manual_domain}")

    # --- TAB 2: MANAGE COMPETITORS (Restore Delete Controls) ---
    with tab2:
        st.subheader("Active Tracking List")
        col_a, col_b = st.columns([4, 1])
        with col_b:
            if st.button("🔄 Run Daily Brief Now"):
                with st.spinner("Running analysis..."):
                    asyncio.run(run_daily_brief())
                    st.success("Brief Sent!")

        # List Competitors with Delete Buttons
        try:
            docs = db.collection("competitors").stream()
            competitors = [doc.id for doc in docs]

            if competitors:
                for domain in competitors:
                    c1, c2 = st.columns([4, 1])
                    with c1:
                        st.write(f"🌐 **{domain}**")
                    with c2:
                        if st.button("🗑️ Remove", key=f"del_{domain}"):
                            delete_doc("competitors", domain)
                            st.rerun()  # Refresh to show it's gone
                    st.divider()
            else:
                st.info("No competitors being tracked.")
        except Exception as e:
            st.error(f"Error loading list: {e}")

    # --- TAB 3: MANAGE SUBSCRIBERS (Restore User Management) ---
    with tab3:
        st.subheader("Email Subscribers")
        try:
            sub_docs = db.collection("subscribers").stream()
            subs = [{"id": d.id, **d.to_dict()} for d in sub_docs]

            if subs:
                for sub in subs:
                    c1, c2, c3 = st.columns([3, 2, 1])
                    with c1:
                        st.write(f"📧 {sub.get('email')}")
                    with c2:
                        st.caption(f"Status: {sub.get('status', 'active')}")
                    with c3:
                        if st.button("Remove", key=f"del_sub_{sub['id']}"):
                            delete_doc("subscribers", sub["id"])
                            st.rerun()
                    st.divider()
            else:
                st.info("No subscribers yet.")
        except Exception as e:
            st.error(f"Error loading subscribers: {e}")


# --- PAGE: PUBLIC SIGNUP ---
def show_public_page():
    st.title("📊 Market Intelligence Brief")
    st.write("Get daily updates on competitor strategy changes and market shifts.")

    with st.form("subscribe_form"):
        email = st.text_input("Enter your work email:")
        submit = st.form_submit_button("Subscribe to Daily Briefs")

        if submit and email:
            if "@" in email and "." in email:
                try:
                    # Save to Firestore
                    db.collection("subscribers").add(
                        {
                            "email": email,
                            "status": "active",
                            "joined_at": firestore.SERVER_TIMESTAMP,
                        }
                    )
                    st.success("✅ You are subscribed! Check your inbox tomorrow.")
                except Exception as e:
                    st.error("Something went wrong. Please try again.")
            else:
                st.warning("Please enter a valid email address.")


# --- MAIN CONTROLLER ---
def main():
    # If no password is set in environment, show error
    if not ADMIN_PASSWORD:
        st.error("Configuration Error: ADMIN_PASSWORD is missing.")
        return

    # Use Tabs to switch between Public Signup and Admin Login
    # We check session state to see if they are already logged in as admin
    if st.session_state.get("password_correct", False):
        show_admin_dashboard()
    else:
        # Public View
        tab_public, tab_login = st.tabs(["📢 Subscribe", "🔒 Admin Login"])

        with tab_public:
            show_public_page()

        with tab_login:
            if check_password():
                st.rerun()  # Force reload to show dashboard


if __name__ == "__main__":
    main()
