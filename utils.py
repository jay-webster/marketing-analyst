import os
import json
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.mime.application import MIMEApplication
from google.cloud import storage
from google.cloud import firestore
from fpdf import FPDF

# --- CONFIGURATION ---
BUCKET_NAME = "marketing-brain-v1"
MEMORY_FILE = "competitor_memory.json"
COMPETITOR_FILE = "competitors.json"


# --- SECRETS & CONFIG ---
def get_secrets():
    """Fetches secrets with safe defaults to avoid KeyErrors."""
    secrets = {
        "email": {
            "sender": os.getenv("EMAIL_SENDER"),
            "password": os.getenv("EMAIL_PASSWORD"),
            "recipient": os.getenv("EMAIL_RECIPIENT"),
        },
        "slack": {
            "bot_token": os.getenv("SLACK_BOT_TOKEN"),
            "channel_id": os.getenv("SLACK_CHANNEL_ID"),
        },
    }

    # Local Fallback (Only if sender is missing, e.g., on your laptop)
    if not secrets["email"]["sender"]:
        try:
            import streamlit as st

            st_secrets = dict(st.secrets)
            secrets["email"]["sender"] = secrets["email"]["sender"] or st_secrets.get(
                "email", {}
            ).get("sender")
            secrets["email"]["password"] = secrets["email"][
                "password"
            ] or st_secrets.get("email", {}).get("password")
        except:
            pass

    return secrets


# --- PERSISTENCE (GCS) ---
def load_memory():
    try:
        client = storage.Client()
        bucket = client.bucket(BUCKET_NAME)
        blob = bucket.blob(MEMORY_FILE)
        return json.loads(blob.download_as_text()) if blob.exists() else {}
    except Exception as e:
        print(f"⚠️ Warning: Could not load memory from GCS: {e}")
        return {}


def save_memory(memory_dict):
    try:
        client = storage.Client()
        bucket = client.bucket(BUCKET_NAME)
        bucket.blob(MEMORY_FILE).upload_from_string(json.dumps(memory_dict, indent=2))
    except Exception as e:
        print(f"❌ Error saving memory to GCS: {e}")


def get_competitors():
    """Fetches the list of competitors from Firestore."""
    try:
        db = firestore.Client()
        docs = db.collection("competitors").stream()
        competitors = [doc.id for doc in docs]

        # Fallback if empty (first run)
        if not competitors:
            return ["navistone.com", "pebblepost.com", "lob.com", "postie.com"]
        return competitors
    except Exception as e:
        print(f"⚠️ Warning: Could not load competitors from Firestore: {e}")
        return ["navistone.com", "pebblepost.com", "lob.com", "postie.com"]


def save_competitors(competitors_list):
    """Syncs the list of competitors to Firestore."""
    try:
        db = firestore.Client()
        collection_ref = db.collection("competitors")

        # 1. Get current list to find diffs
        existing_docs = [doc.id for doc in collection_ref.stream()]
        existing_set = set(existing_docs)
        new_set = set(competitors_list)

        batch = db.batch()

        # 2. Add New
        for domain in new_set - existing_set:
            doc_ref = collection_ref.document(domain)
            batch.set(
                doc_ref, {"domain": domain, "added_at": firestore.SERVER_TIMESTAMP}
            )

        # 3. Delete Removed
        for domain in existing_set - new_set:
            doc_ref = collection_ref.document(domain)
            batch.delete(doc_ref)

        batch.commit()
        return True
    except Exception as e:
        print(f"❌ Error saving competitors to Firestore: {e}")
        return False


# --- EMAIL ENGINE ---
def send_email(
    subject="Daily Brief",
    recipient_email=None,
    body_text="Report attached.",
    pdf_bytes=None,
    filename=None,
):
    """Universal email sender for plain text or PDF reports."""
    secrets = get_secrets()
    sender = secrets["email"]["sender"]
    password = secrets["email"]["password"]
    recipient = recipient_email or secrets["email"]["recipient"]

    if not sender or not password:
        print("❌ Email credentials missing.")
        return

    msg = MIMEMultipart()
    msg["From"] = sender
    msg["To"] = recipient
    msg["Subject"] = subject

    # Attach Body
    msg.attach(MIMEText(body_text, "plain", "utf-8"))

    # ATTACHMENT PROTECTION
    if filename and pdf_bytes:
        try:
            # Safe filename handling
            safe_filename = os.path.basename(filename)
            part = MIMEApplication(pdf_bytes, Name=safe_filename)
            part["Content-Disposition"] = f'attachment; filename="{safe_filename}"'
            msg.attach(part)
        except Exception as e:
            print(f"⚠️ Attachment failed: {e}")

    # Send
    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(sender, password)
            server.send_message(msg)
            print(f"📧 Email sent to {recipient}")
    except Exception as e:
        print(f"❌ SMTP Error: {e}")


# --- EMAIL WRAPPERS ---
def send_verification_email(recipient_email, link):
    body = f"Click to verify your Marketing Intel subscription:\n\n{link}\n\nIf you didn't request this, ignore it."
    send_email(
        subject="Verify your Access", recipient_email=recipient_email, body_text=body
    )


def send_welcome_email(recipient_email):
    # Ensure this URL matches your actual Cloud Run Service URL
    unsub_link = f"https://marketing-intel-portal-1082338379066.us-central1.run.app?unsub={recipient_email}"
    body = (
        f"Welcome! You'll now receive daily reports.\n\nUnsubscribe here: {unsub_link}"
    )
    send_email(
        subject="Welcome to Marketing Intel",
        recipient_email=recipient_email,
        body_text=body,
    )


# --- PDF GENERATOR ---
class ReportPDF(FPDF):
    def sanitize(self, text):
        """Fixes encoding issues (smart quotes, emojis) that crash FPDF."""
        if not text:
            return ""
        # Encode to latin-1, replacing unsupported chars with '?'
        return text.encode("latin-1", "replace").decode("latin-1")

    def header(self):
        self.set_font("Arial", "B", 16)
        self.set_text_color(40, 40, 40)
        self.cell(0, 10, "Daily Competitive Intelligence Brief", 0, 1, "C")
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font("Arial", "I", 8)
        self.set_text_color(128, 128, 128)
        self.cell(
            0,
            10,
            f"Page {self.page_no()} | {datetime.now().strftime('%Y-%m-%d')}",
            0,
            0,
            "C",
        )

    def competitor_header(self, name):
        self.set_font("Arial", "B", 14)
        self.set_text_color(0, 51, 102)  # Dark Blue
        self.cell(0, 10, self.sanitize(name), "B", 1, "L")
        self.ln(2)

    def section_title(self, title):
        self.set_font("Arial", "B", 10)
        self.set_text_color(0, 0, 0)
        self.cell(0, 6, self.sanitize(title).upper(), 0, 1, "L")

    def body_text(self, text):
        self.set_font("Arial", "", 10)
        self.set_text_color(60, 60, 60)
        self.multi_cell(0, 5, self.sanitize(text))
        self.ln(3)


def create_pdf(report_data):
    """
    Generates a PDF from a list of structured competitor analysis dicts.
    """
    pdf = ReportPDF()
    pdf.set_auto_page_break(auto=True, margin=15)

    changed_list = [c for c in report_data if c.get("has_changes")]
    unchanged_list = [c for c in report_data if not c.get("has_changes")]

    # 1. Full Reports for Changed Competitors
    for comp in changed_list:
        pdf.add_page()
        pdf.competitor_header(comp["name"])

        data = comp["content"]

        pdf.section_title("Value Proposition")
        pdf.body_text(data.get("value_proposition", "No specific updates."))

        pdf.section_title("Key Solutions")
        pdf.body_text(data.get("solutions", "No specific updates."))

        pdf.section_title("Target Industries")
        pdf.body_text(data.get("industries", "No specific updates."))

    # 2. Final Page for Unchanged
    if unchanged_list:
        pdf.add_page()
        pdf.competitor_header("No Significant Changes")
        pdf.set_font("Arial", "", 11)
        # FIX: Sanitize the names before joining to prevent Unicode crashes
        names = ", ".join([pdf.sanitize(c["name"]) for c in unchanged_list])
        pdf.body_text(
            f"The following competitors showed no significant website updates since the last report: {names}"
        )

    # If the list was totally empty (no competitors), add a placeholder page to avoid crash
    if not changed_list and not unchanged_list:
        pdf.add_page()
        pdf.body_text("No competitors were processed for this run.")

    return pdf.output(dest="S").encode("latin-1", "replace")
