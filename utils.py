import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import os
import json
from google.cloud import firestore

# --- DATABASE SETUP ---
try:
    project_id = os.getenv("PROJECT_ID")
    db = firestore.Client(project=project_id) if project_id else firestore.Client()
except Exception:
    db = None


# --- DATABASE HELPERS ---
def add_competitor_to_db(domain):
    """
    Manually adds a competitor to the active tracking list.
    """
    if not db:
        return False
    try:
        clean_domain = (
            domain.lower().replace("https://", "").replace("www.", "").split("/")[0]
        )
        # Check if exists
        doc = db.collection("competitors").document(clean_domain).get()
        if not doc.exists:
            db.collection("competitors").document(clean_domain).set(
                {
                    "name": clean_domain.split(".")[0].capitalize(),
                    "added_at": firestore.SERVER_TIMESTAMP,
                    "content": {"value_proposition": "Manual Entry - Pending Analysis"},
                }
            )
            print(f"✅ Manually added {clean_domain}")
            return True
        return False
    except Exception as e:
        print(f"❌ Error adding competitor: {e}")
        return False


def load_memory():
    """
    Backwards compatibility helper.
    In the new cloud-native version, we read directly from Firestore,
    but some legacy code might still call this.
    """
    return {}


def save_memory(memory_dict):
    """
    No-op for cloud native version (we save directly to DB now).
    """
    pass


# --- EMAIL HELPER ---
def send_email(
    subject, recipient_email, body_text, pdf_bytes=None, filename=None, html_body=None
):
    email_user = os.getenv("GMAIL_USER")
    email_password = os.getenv("GMAIL_APP_PASSWORD")

    if not email_user or not email_password:
        print("❌ Email credentials missing.")
        return

    if pdf_bytes:
        msg = MIMEMultipart("mixed")
    else:
        msg = MIMEMultipart("alternative")

    msg["From"] = email_user
    msg["To"] = recipient_email
    msg["Subject"] = subject

    msg.attach(MIMEText(body_text, "plain"))

    if html_body:
        msg.attach(MIMEText(html_body, "html"))

    if pdf_bytes and filename:
        part = MIMEBase("application", "octet-stream")
        part.set_payload(pdf_bytes)
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f"attachment; filename= {filename}")
        msg.attach(part)

    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(email_user, email_password)
        server.sendmail(email_user, recipient_email, msg.as_string())
        server.quit()
    except Exception as e:
        print(f"❌ Failed to send email: {e}")
