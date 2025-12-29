import os
import re
import json
from datetime import datetime
from dotenv import load_dotenv

# Email Imports
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

# PDF Imports
from reportlab.lib.pagesizes import LETTER
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
)

# Cloud Imports
from google.cloud import firestore

load_dotenv()


# --- 1. FIRESTORE HELPERS ---
def get_db():
    return firestore.Client(project=os.getenv("PROJECT_ID", "marketing-analyst-prod"))


def get_competitors():
    db = get_db()
    docs = db.collection("competitors").stream()
    return [doc.id for doc in docs]


def add_competitor(domain):
    db = get_db()
    db.collection("competitors").document(domain).set({"added_at": datetime.now()})


def remove_competitor(domain):
    db = get_db()
    db.collection("competitors").document(domain).delete()


def get_subscribers():
    db = get_db()
    docs = (
        db.collection("subscribers")
        .where(filter=firestore.FieldFilter("status", "==", "active"))
        .stream()
    )
    return [doc.to_dict()["email"] for doc in docs]


def add_subscriber(email):
    db = get_db()
    existing = (
        db.collection("subscribers")
        .where(filter=firestore.FieldFilter("email", "==", email))
        .stream()
    )
    if not list(existing):
        db.collection("subscribers").add(
            {"email": email, "status": "active", "joined_at": datetime.now()}
        )
        return True
    return False


def remove_subscriber(email):
    db = get_db()
    docs = (
        db.collection("subscribers")
        .where(filter=firestore.FieldFilter("email", "==", email))
        .stream()
    )
    for doc in docs:
        doc.reference.update({"status": "inactive"})


# --- 2. MEMORY MANAGEMENT (Rich Persistence) ---
def load_memory():
    """Returns dict: {domain: {full_data_object}}"""
    db = get_db()
    docs = db.collection("memory").stream()
    memory = {}
    for doc in docs:
        memory[doc.id] = doc.to_dict()
    return memory


def save_memory(memory_data):
    """Saves the full competitor state to Firestore."""
    db = get_db()
    batch = db.batch()
    for domain, data in memory_data.items():
        doc_ref = db.collection("memory").document(domain)
        batch.set(doc_ref, data)
    batch.commit()


# --- 3. PDF GENERATION ---
def clean_text(text):
    if text is None:
        return "N/A"
    if isinstance(text, list):
        return ", ".join([str(t) for t in text])
    return str(text)


def format_news_item(text):
    text = re.sub(r"^\d+\.\s*", "", text)
    text = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", text)
    return text


def create_pdf(
    report_data, analyst_summary, title_override=None, reference_company="NaviStone"
):
    filename = "daily_brief.pdf"
    doc = SimpleDocTemplate(filename, pagesize=LETTER)
    story = []
    styles = getSampleStyleSheet()

    title_style = styles["Title"]
    heading_style = styles["Heading2"]
    sub_heading_style = styles["Heading3"]
    normal_style = styles["Normal"]
    news_style = ParagraphStyle("NewsStyle", parent=styles["Normal"], spaceAfter=10)

    # Title Logic
    main_title = (
        title_override
        if title_override
        else f"Daily Competitive Brief for {reference_company}"
    )
    story.append(Paragraph(main_title, title_style))
    story.append(
        Paragraph(f"Date: {datetime.now().strftime('%B %d, %Y')}", normal_style)
    )
    story.append(Spacer(1, 20))

    story.append(Paragraph("🧠 Analyst Overview", heading_style))
    story.append(Paragraph(clean_text(analyst_summary), normal_style))
    story.append(Spacer(1, 20))
    story.append(PageBreak())

    for company in report_data:
        c_name = clean_text(company.get("name", "Unknown"))
        story.append(Paragraph(f"🏢 {c_name}", heading_style))
        story.append(Spacer(1, 10))

        # Handle structure differences
        props = company.get("content", company)

        data = [
            ["Metric", "Current Strategy"],
            [
                "Value Prop",
                Paragraph(clean_text(props.get("value_proposition")), normal_style),
            ],
            [
                "Key Solutions",
                Paragraph(clean_text(props.get("solutions")), normal_style),
            ],
            [
                "Target Ind.",
                Paragraph(clean_text(props.get("industries")), normal_style),
            ],
        ]

        t = Table(data, colWidths=[100, 350])
        t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (1, 0), colors.dimgrey),
                    ("TEXTCOLOR", (0, 0), (1, 0), colors.whitesmoke),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
                    ("BACKGROUND", (0, 1), (-1, -1), colors.beige),
                    ("GRID", (0, 0), (-1, -1), 1, colors.black),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        story.append(t)
        story.append(Spacer(1, 15))

        story.append(Paragraph("📰 Recent News & Activity", sub_heading_style))
        raw_news = company.get("linkedin_update", "No recent updates.")
        for item in raw_news.split("\n"):
            if len(item.strip()) > 5:
                story.append(Paragraph(format_news_item(item), news_style))

        story.append(PageBreak())

    doc.build(story)
    with open(filename, "rb") as f:
        return f.read()


# --- 4. EMAIL SENDING ---
def send_email(subject, recipient_email, body_text, pdf_bytes, filename):
    email_user = os.getenv("GMAIL_USER")
    email_password = os.getenv("GMAIL_APP_PASSWORD")

    if not email_user or not email_password:
        print("❌ Email credentials missing.")
        return

    msg = MIMEMultipart()
    msg["From"] = email_user
    msg["To"] = recipient_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body_text, "plain"))

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
        print(f"📧 Email sent to {recipient_email}")
    except Exception as e:
        print(f"❌ Email Failed: {e}")


# --- 5. NEW: WELCOME EMAIL ---
def send_welcome_email(recipient_email):
    """Generates and sends the Baseline Report to a new user."""
    print(f"👋 Preparing welcome email for {recipient_email}...")
    memory = load_memory()

    if not memory:
        print("⚠️ No memory found. Sending simple welcome.")
        # Fallback text if no data exists yet
        send_email(
            "Welcome to Daily Intel",
            recipient_email,
            "Welcome! Your first report will arrive tomorrow morning.",
            b"",
            "empty.txt",
        )
        return

    report_data = list(memory.values())

    baseline_summary = (
        "Welcome to your Competitive Baseline Report. "
        "This document represents the complete current state of your tracked competitors. "
        "Moving forward, you will receive daily alerts only when significant changes occur."
    )

    pdf_bytes = create_pdf(
        report_data,
        analyst_summary=baseline_summary,
        title_override="Competitive Baseline Report",
        reference_company="NaviStone",
    )

    body = (
        "Welcome to the Daily Competitive Intelligence Service.\n\n"
        "Attached is your Baseline Report. This document covers the current "
        "market position of all your competitors.\n\n"
        "Tomorrow, you will start receiving 'Exception Reports'—brief updates "
        "that only highlight what has changed.\n\n"
        "Best,\nAutomated Analyst"
    )

    send_email(
        subject="Welcome - Your Competitive Baseline",
        recipient_email=recipient_email,
        body_text=body,
        pdf_bytes=pdf_bytes,
        filename="Baseline_Report.pdf",
    )
