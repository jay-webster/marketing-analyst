from email.header import Header
import streamlit as st
import smtplib
from fpdf import FPDF
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
import tomllib  # Built-in for Python 3.11+


# --- SECURITY ---
def check_password():
    """Returns True if the user is logged in."""
    if "password_correct" not in st.session_state:
        st.session_state.password_correct = False

    if st.session_state.password_correct:
        return True

    # Show login form
    with st.form("login_form"):
        password = st.text_input("Enter Password", type="password")
        if st.form_submit_button("Login"):
            if password == st.secrets["password"]:
                st.session_state.password_correct = True
                st.rerun()
            else:
                st.error("❌ Incorrect password")
    return False


def get_secrets():
    """Helper to load secrets locally without Streamlit running."""
    try:
        with open(".streamlit/secrets.toml", "rb") as f:
            return tomllib.load(f)
    except FileNotFoundError:
        return {}


# --- PDF GENERATION ---
def create_pdf(text):
    """Generates a PDF from the provided text."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)

    # Simple line-by-line write (handling unicode roughly)
    # FPDF doesn't love emojis, so we encode/decode to strip them or use a compatible font
    # For this prototype, we'll keep it simple:
    safe_text = text.encode("latin-1", "replace").decode("latin-1")
    pdf.multi_cell(0, 10, safe_text)

    return pdf.output(dest="S").encode("latin-1")


# --- EMAIL SENDER ---


def send_email(pdf_bytes, filename, subject="Daily Strategy Brief"):
    """Sends the PDF via Gmail (Ghost-Proof Version)."""
    secrets = get_secrets()

    if "email" not in secrets:
        print("❌ Error: No email credentials found in secrets.toml")
        return

    sender = secrets["email"]["sender"]
    password = secrets["email"]["password"]
    recipient = secrets["email"]["recipient"]

    msg = MIMEMultipart()
    msg["From"] = sender
    msg["To"] = recipient

    # 1. CLEAN SUBJECT
    # Force subject to strict ASCII to be safe, ignore weird chars
    safe_subject = subject.encode("ascii", "ignore").decode("ascii")
    msg["Subject"] = safe_subject

    # 2. GHOST-PROOF BODY CONSTRUCTION
    # Build the string piece by piece to guarantee standard spaces (ASCII 32).

    body = "Attached is the latest" + " " + "automated strategy report."

    msg.attach(MIMEText(body, "plain", "utf-8"))

    # 3. CLEAN ATTACHMENT NAME
    safe_filename = filename.encode("ascii", "ignore").decode("ascii")
    part = MIMEApplication(pdf_bytes, Name=safe_filename)
    part["Content-Disposition"] = f'attachment; filename="{safe_filename}"'
    msg.attach(part)

    # Send
    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(sender, password)
        server.send_message(msg)
        server.quit()
        print(f"📧 Email sent to {recipient}")
    except Exception as e:
        print(f"❌ Email failed: {e}")
