import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from app.config import settings


def _smtp_send(msg: MIMEText | MIMEMultipart) -> None:
    """Send via Gmail SMTP on port 587 (STARTTLS). Railway blocks 465."""
    with smtplib.SMTP("smtp.gmail.com", 587, timeout=15) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.login(settings.GMAIL_ADDRESS, settings.GMAIL_APP_PASSWORD)
        smtp.send_message(msg)


def send_feedback_notification(
    preference: str,
    comment: str | None,
    orcid_id: str | None,
) -> None:
    if not all([settings.GMAIL_ADDRESS, settings.GMAIL_APP_PASSWORD, settings.FEEDBACK_NOTIFY_EMAIL]):
        return
    try:
        body_lines = [
            f"Preference: {preference}",
            f"User: {orcid_id or 'anonymous'}",
            "",
            comment or "(no comment)",
        ]
        msg = MIMEText("\n".join(body_lines), "plain")
        msg["Subject"] = f"[ChemRepro] New feedback – {preference}"
        msg["From"] = settings.GMAIL_ADDRESS
        msg["To"] = settings.FEEDBACK_NOTIFY_EMAIL
        _smtp_send(msg)
    except Exception:
        pass


def notify_admin(subject: str, body: str) -> None:
    """Email chemrepro@gmail.com when a significant site event occurs."""
    if not settings.ADMIN_NOTIFY_ENABLED:
        return
    if not all([settings.GMAIL_ADDRESS, settings.GMAIL_APP_PASSWORD]):
        return
    try:
        msg = MIMEText(body, "plain")
        msg["Subject"] = f"[ChemRepro] {subject}"
        msg["From"] = settings.GMAIL_ADDRESS
        msg["To"] = settings.GMAIL_ADDRESS
        _smtp_send(msg)
    except Exception:
        pass


def send_generic_email(to: str, subject: str, body_html: str, body_text: str) -> None:
    """Send a generic email (used for author notifications, subscriber alerts, etc.)."""
    if not all([settings.GMAIL_ADDRESS, settings.GMAIL_APP_PASSWORD]):
        return
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"ChemRepro <{settings.GMAIL_ADDRESS}>"
        msg["To"] = to
        msg.attach(MIMEText(body_text, "plain"))
        msg.attach(MIMEText(body_html, "html"))
        _smtp_send(msg)
    except Exception:
        pass
