import streamlit as st
import smtplib
import os
import tomllib
from datetime import datetime
from fpdf import FPDF
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication


# --- SECURITY ---
def check_password():
    """Returns True if the user is logged in."""
    if "password_correct" not in st.session_state:
        st.session_state.password_correct = False

    if st.session_state.password_correct:
        return True

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
    """Hybrid Secret Loader (Local + Cloud)."""
    secrets = {}
    try:
        with open(".streamlit/secrets.toml", "rb") as f:
            secrets = tomllib.load(f)
    except FileNotFoundError:
        pass

    if "email" not in secrets:
        secrets["email"] = {}

    if os.getenv("EMAIL_SENDER"):
        secrets["email"]["sender"] = os.getenv("EMAIL_SENDER")
    if os.getenv("EMAIL_PASSWORD"):
        secrets["email"]["password"] = os.getenv("EMAIL_PASSWORD")
    if os.getenv("EMAIL_RECIPIENT"):
        secrets["email"]["recipient"] = os.getenv("EMAIL_RECIPIENT")

    return secrets


# --- PDF GENERATION (PROFESSIONAL UPGRADE) ---
class ReportPDF(FPDF):
    def header(self):
        self.set_font("Arial", "I", 9)
        self.set_text_color(150, 150, 150)
        self.cell(0, 5, f'{datetime.now().strftime("%Y-%m-%d")}', 0, 1, "R")
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font("Arial", "I", 8)
        self.set_text_color(128)
        self.cell(0, 10, f"Page {self.page_no()}", 0, 0, "C")


def create_pdf(text):
    """Parses Markdown text and applies indented, clean styling."""
    pdf = ReportPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    lines = text.split("\n")

    for line in lines:
        clean_line = line.replace("\xa0", " ").strip()
        safe_line = clean_line.encode("latin-1", "replace").decode("latin-1")

        if not safe_line:
            pdf.ln(2)
            continue

        # --- STYLING RULES ---

        # TITLE (Single #)
        if safe_line.startswith("# "):
            text_content = safe_line.replace("#", "").strip()
            pdf.set_font("Arial", "B", 18)
            pdf.set_text_color(0, 51, 102)  # Navy Blue
            pdf.ln(8)
            pdf.cell(0, 10, text_content, 0, 1, "L")
            y = pdf.get_y()
            pdf.set_draw_color(0, 51, 102)
            pdf.line(10, y, 200, y)
            pdf.ln(5)

        # HEADER 2 (##)
        elif safe_line.startswith("## "):
            # Clean both '#' and potential '*' if the model mixed them
            text_content = safe_line.replace("#", "").replace("*", "").strip()
            pdf.set_font("Arial", "B", 14)
            pdf.set_text_color(0, 76, 153)
            pdf.ln(5)
            pdf.cell(0, 8, text_content, 0, 1, "L")
            pdf.ln(2)

        # HEADER 3 (###)
        elif safe_line.startswith("### "):
            text_content = safe_line.replace("#", "").replace("*", "").strip()
            pdf.set_font("Arial", "B", 12)
            pdf.set_text_color(50, 50, 50)
            pdf.ln(3)
            pdf.cell(0, 6, text_content, 0, 1, "L")

        # BULLETS (* or -) -> NOW INDENTED
        elif safe_line.startswith("* ") or safe_line.startswith("- "):
            bullet_text = safe_line[2:].strip()

            if bullet_text.startswith("**"):
                pdf.set_font("Arial", "B", 11)
            else:
                pdf.set_font("Arial", "", 11)

            pdf.set_text_color(0, 0, 0)

            # Indent Logic:
            # Bullet sits at 15mm (was 10)
            # Text sits at 20mm (was 15)
            current_y = pdf.get_y()
            pdf.set_xy(15, current_y)
            pdf.cell(5, 6, chr(149), 0, 0)

            pdf.set_xy(20, current_y)
            pdf.multi_cell(0, 6, bullet_text.replace("**", ""))
            pdf.ln(1)

        # STANDARD TEXT
        else:
            pdf.set_font("Arial", "", 11)
            pdf.set_text_color(0, 0, 0)
            pdf.multi_cell(0, 6, safe_line)

    return pdf.output(dest="S").encode("latin-1")


# --- EMAIL SENDER (GHOST PROOF) ---
def send_email(pdf_bytes, filename, subject="Daily Strategy Brief"):
    """Sends the PDF via Gmail (Ghost-Proof Version)."""
    secrets = get_secrets()

    if "email" not in secrets:
        print("❌ Error: No email credentials found.")
        return

    sender = secrets["email"]["sender"]
    password = secrets["email"]["password"]
    recipient = secrets["email"]["recipient"]

    msg = MIMEMultipart()
    msg["From"] = sender
    msg["To"] = recipient

    # CLEAN SUBJECT
    safe_subject = subject.encode("ascii", "ignore").decode("ascii")
    msg["Subject"] = safe_subject

    # BODY
    body = "Attached is the latest" + " " + "automated strategy report."
    msg.attach(MIMEText(body, "plain", "utf-8"))

    # CLEAN ATTACHMENT
    safe_filename = filename.encode("ascii", "ignore").decode("ascii")
    part = MIMEApplication(pdf_bytes, Name=safe_filename)
    part["Content-Disposition"] = f'attachment; filename="{safe_filename}"'
    msg.attach(part)

    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(sender, password)
        server.send_message(msg)
        server.quit()
        print(f"📧 Email sent to {recipient}")
    except Exception as e:
        print(f"❌ Email failed: {e}")
