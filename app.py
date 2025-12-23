import streamlit as st
from google.cloud import firestore
import uuid
import re
import utils
from datetime import datetime

db = firestore.Client()


# Helper: Verification Link
def get_app_url():
    # In production, replace this with your Cloud Run URL
    return "https://marketing-intel-portal-1082338379066.us-central1.run.app"


# --- STATE MANAGEMENT ---
if "page" not in st.session_state:
    st.session_state["page"] = "login"


def switch_page(page_name):
    st.session_state["page"] = page_name
    st.rerun()


# --- VIEWS ---
def show_login():
    """Renders the Admin Login Page."""
    st.header("🔑 Admin Login")

    # If already logged in, show the Dashboard
    if st.session_state.get("password_correct", False):
        show_admin_dashboard()
        return

    # Check Password Logic
    if "password" not in st.secrets:
        st.warning("⚠️ No password set. Access is open.")
        show_admin_dashboard()
        return

    password = st.text_input("Enter Password", type="password")
    if st.button("Login"):
        if password == st.secrets["password"]:
            st.session_state["password_correct"] = True
            st.rerun()
        else:
            st.error("❌ Incorrect Password")

    st.divider()
    st.caption("Don't have an account?")
    st.button("Request Access", on_click=lambda: switch_page("signup"))


def show_signup():
    """Renders the Signup/Request Access Page."""
    st.header("📝 Request Access")
    st.markdown(
        "Enter your company email to receive daily competitive intelligence reports."
    )

    with st.form("signup_form", clear_on_submit=True):
        email_input = st.text_input("Email Address (e.g. name@navistone.com)")
        submitted = st.form_submit_button("Send Verification Link")

    if submitted:
        email = email_input.strip().lower()
        if not re.match(r"^[a-zA-Z0-9_.+-]+@navistone\.com$", email):
            st.error("🚨 Access Restricted: Please use a valid @navistone.com email.")
        else:
            verification_token = str(uuid.uuid4())
            db.collection("pending_verifications").document(email).set(
                {
                    "email": email,
                    "token": verification_token,
                    "created_at": firestore.SERVER_TIMESTAMP,
                }
            )
            verify_link = f"{get_app_url()}?token={verification_token}"
            utils.send_verification_email(email, verify_link)
            st.success(f"✅ Verification sent to {email}. Check your inbox.")

    st.divider()
    st.button("Back to Login", on_click=lambda: switch_page("login"))


def show_admin_dashboard():
    """Renders the Robot Manager (Admin UI)."""
    st.success("🔓 Access Granted")
    st.subheader("⚙️ Robot Manager")
    st.info("Manage the list of competitors the Cloud Robot watches every morning.")

    current_competitors = utils.get_competitors()
    col_list, col_add = st.columns([2, 1])

    with col_list:
        st.write(f"**Current Watchlist ({len(current_competitors)})**")
        for comp in current_competitors:
            c1, c2 = st.columns([4, 1])
            c1.text(comp)
            if c2.button("🗑️", key=f"del_{comp}"):
                new_list = [x for x in current_competitors if x != comp]
                utils.save_competitors(new_list)
                st.rerun()

    with col_add:
        st.write("**Add Target**")
        with st.form("add_comp_form"):
            new_comp = st.text_input("Domain")
            if st.form_submit_button("Add"):
                clean_comp = (
                    new_comp.replace("https://", "")
                    .replace("http://", "")
                    .replace("www.", "")
                    .strip()
                )
                if clean_comp and clean_comp not in current_competitors:
                    current_competitors.append(clean_comp)
                    utils.save_competitors(current_competitors)
                    st.rerun()


# --- GLOBAL HANDLERS (Execute on every run) ---
query_params = st.query_params

# 1. Handle Verification
if "token" in query_params:
    token = query_params["token"]
    pending_ref = (
        db.collection("pending_verifications")
        .where("token", "==", token)
        .limit(1)
        .get()
    )
    if pending_ref:
        user_data = pending_ref[0].to_dict()
        email = user_data["email"]
        db.collection("subscribers").document(email).set(
            {
                "email": email,
                "status": "active",
                "signup_date": firestore.SERVER_TIMESTAMP,
            }
        )
        db.collection("pending_verifications").document(pending_ref[0].id).delete()
        st.balloons()
        st.success(f"🎉 Account Verified! {email} is now active.")
        utils.send_welcome_email(email)
    else:
        st.error("❌ Invalid or expired verification link.")

# 2. Handle Unsubscribe
if "unsub" in query_params:
    email = query_params["unsub"]
    db.collection("subscribers").document(email).delete()
    st.success(f"🗑️ Unsubscribed {email}.")


# --- MAIN APP ROUTER ---
st.title("🚀 Marketing Intelligence Portal")

if st.session_state["page"] == "login":
    show_login()
elif st.session_state["page"] == "signup":
    show_signup()
