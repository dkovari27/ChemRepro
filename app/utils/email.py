import html
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


def sender_footer(base_url: str) -> tuple[str, str]:
    """Sender identification for the end of a notification email: (text, html).

    Names the sender and a contact route; adds the postal address when
    MAIL_POSTAL_ADDRESS is set.
    """
    base = base_url.rstrip("/")
    address = settings.MAIL_POSTAL_ADDRESS.strip()
    text = f"Sent by ChemRepro, {base}. Contact: {base}/feedback"
    html_line = f'Sent by <a href="{html.escape(base)}">ChemRepro</a>. Contact: <a href="{html.escape(base)}/feedback">feedback form</a>'
    if address:
        text += f"\n{address}"
        html_line += f"<br/>{html.escape(address)}"
    return text, f'<p style="margin-top:24px;font-size:12px;color:#64748b">{html_line}</p>'


def send_feedback_notification(
    preference: str,
    comment: str | None,
    orcid_id: str | None,
    submitter_name: str | None = None,
    submitter_email: str | None = None,
) -> None:
    if not all([settings.RESEND_API_KEY, settings.FEEDBACK_NOTIFY_EMAIL]):
        return
    try:
        # For non-logged-in users, show the contact info they provided; otherwise show orcid_id
        if orcid_id:
            user_line = f"User: {orcid_id}"
        elif submitter_name or submitter_email:
            user_line = f"User: {submitter_name or '(no name)'} <{submitter_email or 'no email'}>"
        else:
            user_line = "User: anonymous"
        body = "\n".join([
            f"Preference: {preference}",
            user_line,
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
