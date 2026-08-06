import logging

import resend

from app.config import settings

logger = logging.getLogger(__name__)


def _resend_send(to: str, subject: str, body_text: str, body_html: str | None = None) -> None:
    """Send a single email via Resend HTTP API. Raises on failure."""
    resend.api_key = settings.RESEND_API_KEY
    params: resend.Emails.SendParams = {
        "from": settings.MAIL_FROM,
        "to": [to],
        "subject": subject,
        "text": body_text,
    }
    if body_html:
        params["html"] = body_html
    resend.Emails.send(params)


def send_feedback_notification(
    preference: str,
    comment: str | None,
    orcid_id: str | None,
) -> None:
    if not all([settings.RESEND_API_KEY, settings.FEEDBACK_NOTIFY_EMAIL]):
        return
    try:
        body = "\n".join([
            f"Preference: {preference}",
            f"User: {orcid_id or 'anonymous'}",
            "",
            comment or "(no comment)",
        ])
        _resend_send(
            to=settings.FEEDBACK_NOTIFY_EMAIL,
            subject=f"[ChemRepro] New feedback: {preference}",
            body_text=body,
        )
    except Exception as exc:
        logger.error("send_feedback_notification failed: %s: %s", type(exc).__name__, exc)


def notify_admin(subject: str, body: str) -> None:
    """Email the admin account when a significant site event occurs."""
    if not settings.ADMIN_NOTIFY_ENABLED:
        return
    if not settings.RESEND_API_KEY:
        return
    try:
        _resend_send(
            to=settings.GMAIL_ADDRESS,
            subject=f"[ChemRepro] {subject}",
            body_text=body,
        )
    except Exception as exc:
        logger.error("notify_admin failed — subject=%r error=%s: %s", subject, type(exc).__name__, exc)


def send_generic_email(to: str, subject: str, body_html: str, body_text: str) -> None:
    """Send a generic email (used for author notifications, subscriber alerts, etc.)."""
    if not settings.RESEND_API_KEY:
        return
    try:
        _resend_send(to=to, subject=subject, body_text=body_text, body_html=body_html)
    except Exception as exc:
        logger.error("send_generic_email failed — to=%r subject=%r error=%s: %s", to, subject, type(exc).__name__, exc)
