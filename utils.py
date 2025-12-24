import os
import json
import smtplib
from datetime import datetime, date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from google.cloud import storage
from google.cloud import firestore
from fpdf import FPDF

# --- CONFIGURATION ---
BUCKET_NAME = "marketing-brain-v1"
MEMORY_FILE = "competitor_memory.json"


# --- SECRETS & CONFIG ---
def get_secrets():
    """Fetches secrets with safe defaults."""
    return {
        "email": {
            "sender": os.getenv("EMAIL_SENDER"),
            "password": os.getenv("EMAIL_PASSWORD"),
            "recipient": os.getenv("EMAIL_RECIPIENT"),
        }
    }


# --- PERSISTENCE (GCS) ---
def load_memory():
    """Fetches the previous analysis state from Google Cloud Storage."""
    try:
        client = storage.Client()
        bucket = client.bucket(BUCKET_NAME)
        blob = bucket.blob(MEMORY_FILE)
        if blob.exists():
            return json.loads(blob.download_as_text())
        return {}
    except Exception as e:
        print(f"⚠️ Warning: Could not load memory from GCS: {e}")
        return {}


def save_memory(memory_dict):
    """Uploads the current analysis state to Google Cloud Storage."""
    try:
        client = storage.Client()
        bucket = client.bucket(BUCKET_NAME)
        bucket.blob(MEMORY_FILE).upload_from_string(json.dumps(memory_dict, indent=2))
        print("✅ Memory saved to GCS.")
    except Exception as e:
        print(f"❌ Error saving memory to GCS: {e}")


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
    msg.attach(MIMEText(body_text, "plain", "utf-8"))

    if filename and pdf_bytes:
        try:
            part = MIMEApplication(pdf_bytes, Name=filename)
            part["Content-Disposition"] = f'attachment; filename="{filename}"'
            msg.attach(part)
        except Exception as e:
            print(f"⚠️ Attachment failed: {e}")

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(sender, password)
            server.send_message(msg)
            print(f"📧 Email sent to {recipient}")
    except Exception as e:
        print(f"❌ SMTP Error: {e}")


# --- PDF GENERATOR (EXECUTIVE VERSION) ---
class ExecutivePDF(FPDF):
    def header(self):
        """Adds a professional branded header to every page."""
        self.set_font("Arial", "B", 12)
        self.set_text_color(44, 62, 80)
        self.cell(0, 10, "DAILY COMPETITIVE STRATEGY BRIEF", 0, 1, "L")
        self.set_font("Arial", "", 10)
        self.set_text_color(100, 100, 100)
        self.cell(
            0, 5, f"Analysis Date: {date.today().strftime('%B %d, %Y')}", 0, 1, "L"
        )
        self.ln(5)
        self.line(10, 27, 200, 27)

    def footer(self):
        """Adds centered page numbers at the bottom."""
        self.set_y(-15)
        self.set_font("Arial", "I", 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f"Page {self.page_no()}", 0, 0, "C")


def create_pdf(report_data, analyst_summary="No high-level summary available."):
    """Generates a structured, multi-page executive brief."""
    pdf = ExecutivePDF()
    pdf.set_auto_page_break(auto=True, margin=15)

    def safe_text(text):
        if not text:
            return "N/A"
        return text.encode("latin-1", "replace").decode("latin-1")

    # --- PAGE 1: EXECUTIVE COVER PAGE ---
    pdf.add_page()
    pdf.ln(10)
    pdf.set_font("Arial", "B", 18)
    pdf.set_text_color(44, 62, 80)
    pdf.cell(0, 10, "Executive Summary", 0, 1, "L")
    pdf.ln(2)

    pdf.set_font("Arial", "", 11)
    pdf.set_text_color(0, 0, 0)
    pdf.multi_cell(0, 6, safe_text(analyst_summary))
    pdf.ln(10)

    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 10, "Landscape Activity Status", 0, 1, "L")
    pdf.set_fill_color(245, 245, 247)
    pdf.set_font("Arial", "B", 10)
    pdf.cell(100, 10, " Competitor Domain", 1, 0, "L", 1)
    pdf.cell(40, 10, " Market Status", 1, 1, "L", 1)

    pdf.set_font("Arial", "", 10)
    for comp in report_data:
        pdf.cell(100, 10, f" {comp['name']}", 1, 0, "L")
        status = "CHANGES DETECTED" if comp["has_changes"] else "NO RECENT CHANGES"
        color = (180, 0, 0) if comp["has_changes"] else (100, 100, 100)
        pdf.set_text_color(*color)
        pdf.set_font("Arial", "B" if comp["has_changes"] else "", 10)
        pdf.cell(40, 10, f" {status}", 1, 1, "L")
        pdf.set_text_color(0, 0, 0)

    # --- PAGE 2+: DEEP DIVE ANALYSIS ---
    for comp in report_data:
        pdf.add_page()
        pdf.set_font("Arial", "B", 16)
        pdf.set_text_color(44, 62, 80)
        pdf.cell(0, 12, f"Deep Dive: {comp['name']}", 0, 1, "L")
        pdf.ln(2)

        pdf.set_font("Arial", "B", 11)
        pdf.set_fill_color(235, 245, 255)
        pdf.cell(0, 8, "  Current Value Proposition", 0, 1, "L", 1)
        pdf.set_font("Arial", "", 10)
        pdf.ln(2)
        pdf.multi_cell(0, 6, safe_text(comp["content"]["value_proposition"]))
        pdf.ln(6)

        if comp.get("old_content") and comp["has_changes"]:
            pdf.set_font("Arial", "B", 10)
            pdf.set_text_color(180, 0, 0)
            pdf.cell(0, 6, "PREVIOUS STRATEGIC POSITIONING:", 0, 1, "L")
            pdf.set_font("Arial", "I", 9)
            pdf.set_text_color(80, 80, 80)
            pdf.multi_cell(0, 5, safe_text(comp["old_content"]))
            pdf.set_text_color(0, 0, 0)
            pdf.ln(6)

        pdf.set_font("Arial", "B", 11)
        pdf.set_fill_color(245, 245, 245)
        pdf.cell(90, 8, "  Targeted Solutions", 0, 0, "L", 1)
        pdf.cell(5, 8, "", 0, 0)
        pdf.cell(90, 8, "  Industries Served", 0, 1, "L", 1)

        pdf.ln(2)
        pdf.set_font("Arial", "", 10)
        start_y = pdf.get_y()
        pdf.multi_cell(90, 5, safe_text(comp["content"]["solutions"]))
        sol_end_y = pdf.get_y()
        pdf.set_xy(105, start_y)
        pdf.multi_cell(90, 5, safe_text(comp["content"]["industries"]))
        ind_end_y = pdf.get_y()

        pdf.set_y(max(sol_end_y, ind_end_y) + 10)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())

    return pdf.output(dest="S").encode("latin-1", "replace")
