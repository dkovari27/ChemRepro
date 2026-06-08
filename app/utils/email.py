import asyncio
import smtplib
from email.mime.text import MIMEText

from app.config import settings


async def send_feedback_notification(
    preference: str,
    comment: str | None,
    orcid_id: str | None,
) -> None:
    if not all([settings.GMAIL_ADDRESS, settings.GMAIL_APP_PASSWORD, settings.FEEDBACK_NOTIFY_EMAIL]):
        return

    def _send() -> None:
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
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(settings.GMAIL_ADDRESS, settings.GMAIL_APP_PASSWORD)
            smtp.send_message(msg)

    try:
        await asyncio.to_thread(_send)
    except Exception:
        pass
