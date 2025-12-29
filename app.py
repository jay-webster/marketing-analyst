import streamlit as st
import utils
import os
import asyncio

st.set_page_config(page_title="Marketing Analyst Agent", page_icon="🕵️‍♂️")

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")


def check_password():
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
        if "@" in email and "." in email:
            if utils.add_subscriber(email):
                st.success(f"✅ Subscribed! You will receive daily updates at {email}.")
                with st.spinner("Generating your Baseline Report..."):
                    utils.send_welcome_email(email)
                st.info(
                    "📨 A complete Competitive Baseline Report has been sent to your inbox."
                )
            else:
                st.warning("⚠️ This email is already subscribed.")
        else:
            st.error("Please enter a valid email address.")


def show_admin_dashboard():
    st.title("🕵️‍♂️ Analyst Admin Dashboard")
    st.markdown("Manage competitors and subscribers.")

    # 1. Competitor Management
    st.header("🏢 Competitors")

    col1, col2 = st.columns([3, 1])
    with col1:
        new_comp = st.text_input(
            "Add Competitor Domain",
            placeholder="e.g. lob.com",
            label_visibility="collapsed",
        )
    with col2:
        if st.button("Add New"):
            if new_comp and "." in new_comp:
                utils.add_competitor(new_comp.lower().strip())
                st.success(f"Added {new_comp}")
                st.rerun()

    st.divider()

    # List with Delete Buttons
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
                    # Small delay to allow UI update
                    asyncio.run(asyncio.sleep(0.5))
                    st.rerun()

    st.divider()

    # 2. Subscriber Management
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


def main():
    sidebar_selection = st.sidebar.radio("Navigation", ["Subscribe", "Admin Login"])

    if sidebar_selection == "Subscribe":
        show_subscribe_page()
    elif sidebar_selection == "Admin Login":
        if check_password():
            show_admin_dashboard()


if __name__ == "__main__":
    main()
