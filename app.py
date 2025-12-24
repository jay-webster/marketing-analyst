import streamlit as st
import os
from google.cloud import firestore
import uuid
import re
import utils
from datetime import datetime

db = firestore.Client()


def get_app_url():
    # Cloud Run URL
    return "https://marketing-intel-portal-1082338379066.us-central1.run.app"


# --- STATE MANAGEMENT ---
if "page" not in st.session_state:
    st.session_state["page"] = "login"


def switch_page(page_name):
    st.session_state["page"] = page_name
    st.rerun()


# --- VIEWS ---
def show_login():
    st.header("🔑 Admin Login")

    if st.session_state.get("password_correct", False):
        show_admin_dashboard()
        return

    # Unified password check across agent/monitor/app
    try:
        # Check Streamlit secrets first, then Environment variables
        stored_password = st.secrets.get("ADMIN_PASSWORD") or os.environ.get(
            "ADMIN_PASSWORD"
        )
    except:
        stored_password = os.environ.get("ADMIN_PASSWORD")

    if not stored_password:
        st.warning(
            "⚠️ ADMIN_PASSWORD not set in Cloud Run. Access is currently open for testing."
        )
        if st.button("Enter Dashboard"):
            st.session_state["password_correct"] = True
            st.rerun()
        return

    password = st.text_input("Enter Admin Password", type="password")
    if st.button("Login"):
        if password == stored_password:
            st.session_state["password_correct"] = True
            st.rerun()
        else:
            st.error("❌ Incorrect Password")

    st.divider()
    st.caption("Not an Admin? Request daily reports below.")
    st.button("Request Access", on_click=lambda: switch_page("signup"))


def show_signup():
    st.header("📝 Request Access")
    st.markdown("Enter your email to receive daily competitive intelligence reports.")

    with st.form("signup_form", clear_on_submit=True):
        email_input = st.text_input("Email Address")
        submitted = st.form_submit_button("Send Verification Link")

    if submitted:
        email = email_input.strip().lower()
        # Regex update to allow standard emails or keep your navistone restriction
        if not re.match(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$", email):
            st.error("🚨 Please use a valid email address.")
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
            st.success(f"✅ Verification link sent to {email}.")

    st.divider()
    st.button("Back to Login", on_click=lambda: switch_page("login"))


def show_admin_dashboard():
    st.success("🔓 Admin Access Active")
    st.subheader("⚙️ Competitor Watchlist")

    # Get competitors from Firestore via utils
    current_competitors = utils.get_competitors()

    # Ensure defaults exist without infinite rerun
    if not current_competitors:
        current_competitors = ["navistone.com"]
        utils.save_competitors(current_competitors)

    col_list, col_add = st.columns([2, 1])

    with col_list:
        st.write(f"**Watching {len(current_competitors)} Targets**")
        for comp in current_competitors:
            c1, c2 = st.columns([4, 1])
            c1.text(f"🌐 {comp}")
            if c2.button("🗑️", key=f"del_{comp}"):
                new_list = [x for x in current_competitors if x != comp]
                utils.save_competitors(new_list)
                st.rerun()

    with col_add:
        st.write("**Add New Target**")
        with st.form("add_comp_form", clear_on_submit=True):
            new_comp = st.text_input("Domain (e.g. lob.com)")
            if st.form_submit_button("Add"):
                clean_comp = (
                    new_comp.lower()
                    .replace("https://", "")
                    .replace("http://", "")
                    .replace("www.", "")
                    .strip()
                )
                if clean_comp and clean_comp not in current_competitors:
                    current_competitors.append(clean_comp)
                    utils.save_competitors(current_competitors)
                    st.rerun()


# --- GLOBAL HANDLERS ---
params = st.query_params

if "token" in params:
    token = params["token"]
    pending = (
        db.collection("pending_verifications")
        .where("token", "==", token)
        .limit(1)
        .get()
    )
    if pending:
        email = pending[0].to_dict()["email"]
        db.collection("subscribers").document(email).set(
            {
                "email": email,
                "status": "active",
                "signup_date": firestore.SERVER_TIMESTAMP,
            }
        )
        db.collection("pending_verifications").document(pending[0].id).delete()
        st.balloons()
        st.success(f"🎉 Subscribed! {email} will now receive reports.")
        utils.send_welcome_email(email)

if "unsub" in params:
    email = params["unsub"]
    db.collection("subscribers").document(email).delete()
    st.warning(f"Unsubscribed {email}.")

# --- APP ROUTER ---
st.title("🚀 Marketing Intelligence Portal")
if st.session_state["page"] == "login":
    show_login()
else:
    show_signup()
