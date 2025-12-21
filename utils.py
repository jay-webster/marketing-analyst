# utils.py
import streamlit as st
import os
from fpdf import FPDF


def check_password():
    """Handles password protection."""
    stored_password = os.environ.get("APP_PASSWORD")
    if not stored_password:
        if "password" in st.secrets:
            stored_password = st.secrets["password"]
        else:
            st.error("❌ Config Error: No password found!")
            return False

    def password_entered():
        if st.session_state["password"] == stored_password:
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if st.session_state.get("password_correct", False):
        return True

    st.text_input(
        "Enter Password", type="password", on_change=password_entered, key="password"
    )
    return False


def create_pdf(text):
    """Generates a PDF from text."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    # Header
    pdf.set_font("Arial", style="B", size=16)
    pdf.cell(200, 10, txt="Marketing Strategy Report", ln=True, align="C")
    pdf.ln(10)
    # Body
    pdf.set_font("Arial", size=12)
    pdf.multi_cell(0, 10, text.encode("latin-1", "replace").decode("latin-1"))
    return pdf.output(dest="S").encode("latin-1")
