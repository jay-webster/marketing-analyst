import streamlit as st
import utils
import os
import asyncio
import re
import monitor  # Needed for the discovery function
from dotenv import load_dotenv
load_dotenv()

st.set_page_config(page_title="Marketing Analyst Agent", page_icon="🕵️‍♂️")

# Security: No default password - must be set via environment variable
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")


def is_valid_email(email: str) -> bool:
    """
    Validates email format to prevent injection and ensure RFC compliance.
    Returns True if email is valid, False otherwise.
    """
    if not email or len(email) > 254:
        return False
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


def is_valid_domain(domain: str) -> bool:
    """
    Validates domain format to prevent injection attacks.
    Returns True if domain is valid, False otherwise.
    """
    if not domain or len(domain) > 253:
        return False
    # Remove protocol if present
    domain = domain.replace('http://', '').replace('https://', '').strip()
    # Basic domain validation: alphanumeric, hyphens, dots allowed
    pattern = r'^[a-z0-9]+([\-\.]{1}[a-z0-9]+)*\.[a-z]{2,}$'
    return bool(re.match(pattern, domain.lower()))


def check_password():
    """Check if user has entered correct admin password."""
    # Security check: ensure ADMIN_PASSWORD is configured
    if not ADMIN_PASSWORD:
        st.error("⚠️ ADMIN_PASSWORD environment variable is not set. Admin access is disabled for security.")
        st.info("💡 Please set the ADMIN_PASSWORD environment variable to enable admin access.")
        return False
    
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


def show_subscribe_page():
    st.title("📬 Subscribe to Daily Intel")
    st.markdown(
        "Get automated competitive updates delivered to your inbox every morning."
    )
    email = st.text_input("Enter your work email")

    if st.button("Subscribe"):
        if not email:
            st.error("Please enter an email address.")
        elif not is_valid_email(email):
            st.error("⚠️ Please enter a valid email address (e.g., user@company.com).")
        else:
            if utils.add_subscriber(email):
                st.success(f"✅ Subscribed! You will receive daily updates at {email}.")
                with st.spinner("Generating your Baseline Report..."):
                    utils.send_welcome_email(email)
                st.info(
                    "📨 A complete Competitive Baseline Report has been sent to your inbox."
                )
            else:
                st.warning("⚠️ This email is already subscribed.")


def _render_competitor_discovery_ui():
    """Renders the AI-powered competitor discovery section."""
    if "discovery_results" not in st.session_state:
        st.session_state.discovery_results = []

    with st.expander("✨ Competitor Discovery (AI Powered)", expanded=False):
        st.markdown("Enter a target company URL to find relevant competitors.")

        c1, c2, c3 = st.columns([3, 1, 1])
        with c1:
            target_domain = st.text_input(
                "Target Domain",
                placeholder="e.g., yourclient.com",
                label_visibility="collapsed",
            )
        with c2:
            scan_clicked = st.button("🔍 Scan Market")
        with c3:
            if st.button("🗑️ Clear Results"):
                st.session_state.discovery_results = []
                st.rerun()

        # Execute Scan
        if scan_clicked and target_domain:
            with st.spinner(f"Agent is researching competitors for {target_domain}..."):
                results = asyncio.run(monitor.discover_competitors(target_domain))
                if results:
                    st.session_state.discovery_results = results
                else:
                    st.warning(
                        "No competitors found. Try a broader domain or industry name."
                    )

        # Render Results from State
        if st.session_state.discovery_results:
            st.success(
                f"Found {len(st.session_state.discovery_results)} potential competitors."
            )

            for i, comp in enumerate(st.session_state.discovery_results):
                with st.container(border=True):
                    col_a, col_b = st.columns([4, 1])
                    with col_a:
                        st.subheader(comp.get("name", "Unknown"))
                        st.caption(f"Domain: {comp.get('domain')}")
                        st.write(f"**Why:** {comp.get('reason')}")
                    with col_b:
                        dom = comp.get("domain", "").lower()

                        if st.button("Add", key=f"add_{dom}_{i}"):
                            utils.add_competitor(dom)
                            st.toast(f"✅ Added {dom}!")

                        if st.button("Ignore", key=f"ignore_{dom}_{i}"):
                            st.session_state.discovery_results.pop(i)
                            st.rerun()


def _render_competitor_list_ui():
    """Renders the tracked competitors list and management section."""
    st.header("🏢 Tracked Competitors")

    col1, col2 = st.columns([3, 1])
    with col1:
        new_comp = st.text_input(
            "Manually Add Domain",
            placeholder="e.g. lob.com",
            label_visibility="collapsed",
        )
    with col2:
        if st.button("Add New"):
            if not new_comp:
                st.error("Please enter a domain.")
            elif not is_valid_domain(new_comp):
                st.error("⚠️ Please enter a valid domain (e.g., competitor.com).")
            else:
                utils.add_competitor(new_comp.lower().strip())
                st.success(f"Added {new_comp}")
                st.rerun()

    current_competitors = utils.get_competitors()
    if not current_competitors:
        st.info("No competitors tracked yet.")
    else:
        for comp in current_competitors:
            c1, c2 = st.columns([4, 1])
            with c1:
                st.markdown(f"**{comp}**")
            with c2:
                if st.button("Delete", key=f"del_{comp}"):
                    utils.remove_competitor(comp)
                    st.success(f"Removed {comp}")
                    asyncio.run(asyncio.sleep(0.5))
                    st.rerun()


def _render_subscriber_management_ui():
    """Renders the subscriber list and management section."""
    st.header("👥 Subscribers")
    subs = utils.get_subscribers()
    if subs:
        st.table(subs)
    else:
        st.info("No active subscribers.")

    rem_sub = st.text_input("Remove Subscriber Email")
    if st.button("Unsubscribe User"):
        utils.remove_subscriber(rem_sub)
        st.success("User removed.")
        st.rerun()


def show_admin_dashboard():
    """Main admin dashboard with competitor and subscriber management."""
    st.title("🕵️‍♂️ Analyst Admin Dashboard")
    st.markdown("Manage competitors and subscribers.")

    _render_competitor_discovery_ui()
    st.divider()
    _render_competitor_list_ui()
    st.divider()
    _render_subscriber_management_ui()


def main():
    sidebar_selection = st.sidebar.radio("Navigation", ["Subscribe", "Admin Login"])
    if sidebar_selection == "Subscribe":
        show_subscribe_page()
    elif sidebar_selection == "Admin Login" and check_password():
        show_admin_dashboard()


if __name__ == "__main__":
    main()
