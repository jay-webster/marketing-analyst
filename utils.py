import streamlit as st
import smtplib
import os
import tomllib
import json
import requests
from datetime import datetime
from fpdf import FPDF
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from google.cloud import storage

# --- CONFIGURATION ---
BUCKET_NAME = "marketing-brain-v1"
MEMORY_FILE = "competitor_memory.json"
COMPETITOR_FILE = "competitors.json"


# --- SECURITY ---
def check_password():
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

    # Slack Secrets (Updated for Bot Token)
    if "slack" not in secrets:
        secrets["slack"] = {}
    if os.getenv("SLACK_BOT_TOKEN"):
        secrets["slack"]["bot_token"] = os.getenv("SLACK_BOT_TOKEN")
    if os.getenv("SLACK_CHANNEL_ID"):
        secrets["slack"]["channel_id"] = os.getenv("SLACK_CHANNEL_ID")

    return secrets


# --- PERSISTENCE ---
def load_memory():
    try:
        client = storage.Client()
        bucket = client.bucket(BUCKET_NAME)
        blob = bucket.blob(MEMORY_FILE)
        if blob.exists():
            return json.loads(blob.download_as_text())
        else:
            return {}
    except Exception as e:
        print(f"⚠️ Memory Load Failed: {e}")
        return {}


def save_memory(memory_dict):
    try:
        client = storage.Client()
        bucket = client.bucket(BUCKET_NAME)
        blob = bucket.blob(MEMORY_FILE)
        blob.upload_from_string(json.dumps(memory_dict, indent=2))
        print("💾 Memory saved.")
    except Exception as e:
        print(f"❌ Memory Save Failed: {e}")


def get_competitors():
    default_list = ["navistone.com", "pebblepost.com", "lob.com", "postie.com"]
    try:
        client = storage.Client()
        bucket = client.bucket(BUCKET_NAME)
        blob = bucket.blob(COMPETITOR_FILE)
        if blob.exists():
            data = json.loads(blob.download_as_text())
            return data.get("competitors", default_list)
        else:
            save_competitors(default_list)
            return default_list
    except Exception as e:
        print(f"⚠️ Competitor Load Failed: {e}")
        return default_list


def save_competitors(competitor_list):
    try:
        client = storage.Client()
        bucket = client.bucket(BUCKET_NAME)
        blob = bucket.blob(COMPETITOR_FILE)
        data = {"competitors": competitor_list, "updated_at": str(datetime.now())}
        blob.upload_from_string(json.dumps(data, indent=2))
        return True
    except Exception as e:
        print(f"❌ Failed to save competitors: {e}")
        return False


# --- SLACK FILE UPLOAD (NEW) ---
def send_slack_file(pdf_bytes, filename, summary_text):
    """Uploads the PDF to Slack with a summary message."""
    secrets = get_secrets()
    slack_conf = secrets.get("slack", {})

    if "bot_token" not in slack_conf or "channel_id" not in slack_conf:
        print("⚠️ Missing Slack Bot Token or Channel ID. Skipping.")
        return

    token = slack_conf["bot_token"]
    channel_id = slack_conf["channel_id"]

    print(f"📤 Uploading {filename} to Slack Channel {channel_id}...")

    try:
        # We use the files.upload API to send the PDF + The Comment in one go
        response = requests.post(
            "https://slack.com/api/files.upload",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": pdf_bytes},
            data={
                "channels": channel_id,
                "initial_comment": summary_text,
                "title": filename,
                "filetype": "pdf",
            },
        )

        if response.status_code == 200 and response.json().get("ok"):
            print("✅ Slack file upload successful.")
        else:
            print(f"❌ Slack Upload Failed: {response.text}")

    except Exception as e:
        print(f"❌ Slack Error: {e}")


# --- PDF GENERATION ---
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
    pdf = ReportPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=20)

    lines = text.split("\n")

    for line in lines:
        clean_line = line.replace("\xa0", " ").strip()
        safe_line = clean_line.encode("latin-1", "replace").decode("latin-1")

        if not safe_line:
            pdf.ln(2)
            continue

        if safe_line.startswith("# "):
            text_content = safe_line.replace("#", "").strip()
            if pdf.page_no() > 1 or pdf.get_y() > 50:
                pdf.add_page()
            pdf.set_font("Arial", "B", 18)
            pdf.set_text_color(0, 51, 102)
            pdf.ln(8)
            pdf.cell(0, 10, text_content, 0, 1, "L")
            y = pdf.get_y()
            pdf.set_draw_color(0, 51, 102)
            pdf.line(10, y, 200, y)
            pdf.ln(5)

        elif safe_line.startswith("## "):
            text_content = safe_line.replace("#", "").replace("*", "").strip()
            pdf.set_font("Arial", "B", 14)
            pdf.set_text_color(0, 76, 153)
            pdf.ln(5)
            pdf.cell(0, 8, text_content, 0, 1, "L")
            pdf.ln(2)

        elif safe_line.startswith("### "):
            text_content = safe_line.replace("#", "").replace("*", "").strip()
            pdf.set_font("Arial", "B", 12)
            pdf.set_text_color(50, 50, 50)
            pdf.ln(3)
            pdf.cell(0, 6, text_content, 0, 1, "L")

        elif safe_line.startswith("* ") or safe_line.startswith("- "):
            bullet_text = safe_line[2:].strip()
            if bullet_text.startswith("**"):
                pdf.set_font("Arial", "B", 11)
            else:
                pdf.set_font("Arial", "", 11)
            pdf.set_text_color(0, 0, 0)
            current_y = pdf.get_y()
            pdf.set_xy(15, current_y)
            pdf.cell(5, 6, chr(149), 0, 0)
            pdf.set_xy(20, current_y)
            pdf.multi_cell(0, 6, bullet_text.replace("**", ""))
            pdf.ln(1)

        else:
            pdf.set_font("Arial", "", 11)
            pdf.set_text_color(0, 0, 0)
            pdf.multi_cell(0, 6, safe_line)

    return pdf.output(dest="S").encode("latin-1")


# --- EMAIL SENDER ---
def send_email(pdf_bytes, filename, subject="Daily Strategy Brief"):
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

    safe_subject = subject.encode("ascii", "ignore").decode("ascii")
    msg["Subject"] = safe_subject

    body = "Attached is the latest" + " " + "automated strategy report."
    msg.attach(MIMEText(body, "plain", "utf-8"))

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
