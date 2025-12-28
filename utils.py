import os
import json
import re
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

load_dotenv()


# --- 1. MEMORY MANAGEMENT ---
def load_memory():
    if os.path.exists("memory.json"):
        try:
            with open("memory.json", "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}
    return {}


def save_memory(memory):
    with open("memory.json", "w") as f:
        json.dump(memory, f)


# --- 2. PDF GENERATION ---
def clean_text(text):
    if text is None:
        return "N/A"
    if isinstance(text, list):
        return ", ".join([str(t) for t in text])
    return str(text)


def format_news_item(text):
    """
    Removes numbering and formats **Header** as bold.
    """
    # 1. Remove leading numbering (e.g., "1. ", "2. ")
    text = re.sub(r"^\d+\.\s*", "", text)

    # 2. Replace markdown bold (**Text**) with HTML bold (<b>Text</b>)
    text = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", text)

    return text


def create_pdf(report_data, analyst_summary, reference_company="NaviStone"):
    """
    Generates a PDF tailored for the Reference Company.
    """
    filename = "daily_brief.pdf"
    doc = SimpleDocTemplate(filename, pagesize=LETTER)
    story = []
    styles = getSampleStyleSheet()

    # Custom Styles
    title_style = styles["Title"]
    heading_style = styles["Heading2"]
    sub_heading_style = styles["Heading3"]
    normal_style = styles["Normal"]

    news_style = ParagraphStyle(
        "NewsStyle",
        parent=styles["Normal"],
        leftIndent=0,
        spaceAfter=10,
        textColor=colors.black,
    )

    # --- TITLE PAGE ---
    story.append(
        Paragraph(f"Daily Competitive Brief for {reference_company}", title_style)
    )
    story.append(
        Paragraph(f"Date: {datetime.now().strftime('%B %d, %Y')}", normal_style)
    )
    story.append(Spacer(1, 20))

    story.append(Paragraph("🧠 Executive Analyst Summary", heading_style))
    story.append(Paragraph(clean_text(analyst_summary), normal_style))
    story.append(Spacer(1, 20))
    story.append(PageBreak())

    # --- COMPANY UPDATES ---
    for company in report_data:
        c_name = clean_text(company.get("name", "Unknown"))

        story.append(Paragraph(f"🏢 {c_name}", heading_style))
        story.append(Spacer(1, 10))

        # A. Website Table
        data = [
            ["Metric", "Current Strategy"],
            [
                "Value Prop",
                Paragraph(
                    clean_text(company["content"].get("value_proposition")),
                    normal_style,
                ),
            ],
            [
                "Key Solutions",
                Paragraph(
                    clean_text(company["content"].get("solutions")), normal_style
                ),
            ],
            [
                "Target Ind.",
                Paragraph(
                    clean_text(company["content"].get("industries")), normal_style
                ),
            ],
        ]

        t = Table(data, colWidths=[100, 350])
        t.setStyle(
            TableStyle(
                [
                    # CHANGED: 'dimgrey' gives much better contrast for white text
                    ("BACKGROUND", (0, 0), (1, 0), colors.dimgrey),
                    ("TEXTCOLOR", (0, 0), (1, 0), colors.whitesmoke),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
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

        # B. News Section (Formatted)
        story.append(Paragraph("📰 Recent News & Activity", sub_heading_style))

        raw_news = company.get("linkedin_update", "No recent updates.")
        news_items = raw_news.split("\n")

        for item in news_items:
            if len(item.strip()) > 5:
                formatted_item = format_news_item(item)
                story.append(Paragraph(formatted_item, news_style))

        # CHANGED: Force a Page Break after every company
        story.append(PageBreak())

    doc.build(story)

    with open(filename, "rb") as f:
        return f.read()


# --- 3. EMAIL SENDING ---
def send_email(subject, recipient_email, body_text, pdf_bytes, filename):
    email_user = os.getenv("GMAIL_USER")
    email_password = os.getenv("GMAIL_APP_PASSWORD")

    if not email_user or not email_password:
        print("❌ Email credentials missing in .env.")
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
        text = msg.as_string()
        server.sendmail(email_user, recipient_email, text)
        server.quit()
        print(f"📧 Email sent to {recipient_email}")
    except Exception as e:
        print(f"❌ Email Failed: {e}")
