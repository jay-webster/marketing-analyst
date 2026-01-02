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

# --- CSS HACK: HIDE ANCHOR ICONS ---
# This hides the little chain links that appear next to headers
st.markdown(
    """
    <style>
    [data-testid="stHeaderActionElements"] {
        display: none;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# --- DATABASE CONNECTION ---
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


def delete_doc(collection, doc_id):
    try:
        db.collection(collection).document(doc_id).delete()
        st.toast(f"✅ Deleted {doc_id} from {collection}")
    except Exception as e:
        st.error(f"Error deleting: {e}")


# --- CALLBACK: RESET SEARCH ---
def reset_search():
    if "discovery_results" in st.session_state:
        del st.session_state["discovery_results"]
    st.session_state["search_input"] = ""


# --- PAGE: ADMIN DASHBOARD ---
def show_admin_dashboard():
    st.title("🕵️‍♂️ Analyst Command Center")

    tab1, tab2, tab3 = st.tabs(
        ["🔭 Discovery & Add", "⚙️ Manage Competitors", "👥 Subscribers"]
    )

    # --- TAB 1: DISCOVERY ---
    with tab1:
        st.subheader("Find New Competitors")
        st.info(
            "Uses 'Profile-First' logic: Profiles the target > Identifies Business Model > Finds Matches."
        )

        # 1. SEARCH FORM
        with st.form("discovery_form"):
            col1, col2 = st.columns([3, 1])
            with col1:
                st.text_input(
                    "Enter Target Domain (e.g., viamedia.ai):", key="search_input"
                )
            with col2:
                st.write("")
                st.write("")
                run_discovery = st.form_submit_button(
                    "Analyze & Find", type="primary", use_container_width=True
                )

        # 2. ACTION BUTTONS
        c_refresh, c_reset = st.columns(2)
        with c_refresh:
            if st.button("🔄 Refresh / Fill List", use_container_width=True):
                target = st.session_state.get("search_input")
                if target:
                    with st.spinner(
                        f"Finding more competitors for {target} (ignoring dismissed)..."
                    ):
                        new_results = asyncio.run(monitor.refresh_competitors(target))
                        st.session_state["discovery_results"] = new_results
                        st.rerun()
                else:
                    st.warning("Enter a domain first.")

        with c_reset:
            st.button(
                "🗑️ Reset / Clear",
                type="secondary",
                use_container_width=True,
                on_click=reset_search,
            )

        # 3. RUN LOGIC
        if run_discovery:
            target_domain = st.session_state.get("search_input", "")
            if not target_domain:
                st.warning("Please enter a domain.")
            else:
                with st.spinner(f"Agent is profiling {target_domain}..."):
                    try:
                        results = asyncio.run(
                            monitor.discover_competitors(target_domain)
                        )
                        st.session_state["discovery_results"] = results
                        st.success("Analysis Complete!")
                    except Exception as e:
                        st.error(f"Discovery Error: {e}")

        # 4. DISPLAY RESULTS (Clean UI)
        if "discovery_results" in st.session_state:
            results = st.session_state["discovery_results"]

            if not results:
                st.warning("Analysis finished, but 0 competitors were found.")
            else:
                st.write(f"### 🎯 Found {len(results)} Matches")

                for i, comp in enumerate(results):
                    with st.container(border=True):
                        c1, c2 = st.columns([3, 1])
                        with c1:
                            domain = comp.get("domain", "")
                            name = comp.get("name", "Unknown")
                            link = (
                                domain
                                if domain.startswith("http")
                                else f"https://{domain}"
                            )

                            # CLEAN LINKED TITLE (No redundancy, no hover icons)
                            st.markdown(f"### [{name}]({link})")
                            st.markdown(f"_{comp.get('reason')}_")

                        with c2:
                            if st.button(
                                "✅ Track",
                                key=f"track_{i}_{domain}",
                                use_container_width=True,
                            ):
                                utils.add_competitor_to_db(domain)
                                st.toast(f"Tracking {name}!")
                                monitor.remove_competitor_from_cache(
                                    st.session_state["search_input"], domain
                                )
                                st.session_state["discovery_results"].pop(i)
                                st.rerun()

                            if st.button(
                                "❌ Dismiss",
                                key=f"dismiss_{i}_{domain}",
                                use_container_width=True,
                            ):
                                monitor.remove_competitor_from_cache(
                                    st.session_state["search_input"], domain
                                )
                                st.session_state["discovery_results"].pop(i)
                                st.rerun()

        st.divider()
        st.markdown("### ➕ Manually Add Competitor")

        # clear_on_submit=True is crucial: it clears the text box when you hit Enter,
        # providing immediate visual feedback that the submission worked.
        with st.form("manual_add_form", clear_on_submit=True):
            col_input, col_btn = st.columns([3, 1])
            with col_input:
                manual_domain = st.text_input(
                    "Enter domain (e.g. new-rival.com)", label_visibility="collapsed"
                )
            with col_btn:
                submitted = st.form_submit_button(
                    "Add Domain", use_container_width=True
                )

            if submitted and manual_domain:
                if "." not in manual_domain:
                    st.error("Please enter a valid domain (e.g., example.com)")
                else:
                    success = utils.add_competitor_to_db(manual_domain)
                    if success:
                        st.success(f"✅ Added {manual_domain}")
                        st.rerun()
                    else:
                        st.warning("Could not add domain (already exists?).")

    # --- TAB 2: MANAGE COMPETITORS ---
    with tab2:
        st.subheader("Active Tracking List")

        # HEADER with Run Button
        col_header, col_btn = st.columns([3, 1])
        with col_header:
            st.info("These companies are monitored daily for strategy changes.")
        with col_btn:
            # THIS IS THE MISSING BUTTON
            if st.button("🔄 Run Daily Brief Now", use_container_width=True):
                with st.spinner("Analyzing all competitors (this takes time)..."):
                    asyncio.run(monitor.run_daily_brief())
                    st.success("✅ Analysis Complete! Check Slack/Email for alerts.")

        # LIST COMPETITORS
        try:
            docs = db.collection("competitors").stream()
            competitors = [doc.id for doc in docs]

            if competitors:
                for domain in competitors:
                    c1, c2 = st.columns([4, 1])
                    with c1:
                        # Clickable Link
                        link = (
                            domain if domain.startswith("http") else f"https://{domain}"
                        )
                        st.markdown(f"🌐 **[{domain}]({link})**")
                    with c2:
                        if st.button("🗑️ Remove", key=f"del_{domain}"):
                            delete_doc("competitors", domain)
                            st.rerun()
                    st.divider()
            else:
                st.warning("No competitors being tracked yet.")
        except Exception as e:
            st.error(f"Error loading list: {e}")

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


def show_public_page():
    st.title("📊 Market Intelligence Brief")
    st.write("Get daily updates on competitor strategy changes and market shifts.")
    st.info("Subscribe to receive a Baseline Report immediately.")

    with st.form("subscribe_form"):
        email = st.text_input("Enter your work email:")
        submit = st.form_submit_button("Subscribe to Daily Briefs")

        if submit and email:
            # 1. Domain Validation (Security Gate)
            if not email.lower().endswith("@navistone.com"):
                st.error(
                    "🚫 Access Restricted: You must use a @navistone.com email address."
                )
                return

            if "@" in email and "." in email:
                try:
                    # 2. Add to Database
                    db.collection("subscribers").add(
                        {
                            "email": email,
                            "status": "active",
                            "joined_at": firestore.SERVER_TIMESTAMP,
                        }
                    )

                    # 3. Send Baseline Report (Welcome Email)
                    with st.spinner("Processing subscription & generating baseline..."):
                        monitor.send_baseline_report(email)

                    st.success(
                        f"✅ Subscribed! A baseline report has been sent to {email}."
                    )

                except Exception as e:
                    st.error(f"Something went wrong: {e}")
            else:
                st.warning("Please enter a valid email address.")


def main():
    if not ADMIN_PASSWORD:
        st.error("Configuration Error: ADMIN_PASSWORD is missing.")
        return
    if st.session_state.get("password_correct", False):
        show_admin_dashboard()
    else:
        tab_public, tab_login = st.tabs(["📢 Subscribe", "🔒 Admin Login"])
        with tab_public:
            show_public_page()
        with tab_login:
            if check_password():
                st.rerun()


if __name__ == "__main__":
    main()
