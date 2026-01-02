import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import os


def send_email(
    subject, recipient_email, body_text, pdf_bytes=None, filename=None, html_body=None
):
    email_user = os.getenv("GMAIL_USER")
    email_password = os.getenv("GMAIL_APP_PASSWORD")

    if not email_user or not email_password:
        print("❌ Email credentials missing.")
        return

    # 1. Determine Email Type
    if pdf_bytes:
        msg = MIMEMultipart("mixed")
    else:
        msg = MIMEMultipart("alternative")

    msg["From"] = email_user
    msg["To"] = recipient_email
    msg["Subject"] = subject

    # 2. Attach Plain Text (Fallback)
    msg.attach(MIMEText(body_text, "plain"))

    # 3. Attach HTML (Rich Content)
    if html_body:
        msg.attach(MIMEText(html_body, "html"))

    # 4. Attach PDF (Optional)
    if pdf_bytes and filename:
        part = MIMEBase("application", "octet-stream")
        part.set_payload(pdf_bytes)
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f"attachment; filename= {filename}")
        msg.attach(part)

    # 5. Send
    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(email_user, email_password)
        server.sendmail(email_user, recipient_email, msg.as_string())
        server.quit()
        # print(f"✅ Email sent to {recipient_email}")
    except Exception as e:
        print(f"❌ Failed to send email: {e}")
