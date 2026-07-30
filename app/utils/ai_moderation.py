import re
import anthropic
from app.config import settings

_MISCONDUCT_WORDS = re.compile(
    r'\b(fraud|fraudulent|fabrication|fabricated|falsification|falsified|falsify'
    r'|plagiarism|plagiarized|plagiarize|misconduct)\b'
    r'|data\s+manipulation|image\s+manipulation',
    re.IGNORECASE,
)


def contains_misconduct_allegation(text: str) -> bool:
    """Return True if text contains language suggesting a research misconduct allegation."""
    return bool(_MISCONDUCT_WORDS.search(text))


# Suppress repeated credit/API alarm emails within one server lifetime
_api_alarm_sent = False


def _check_content(text: str) -> bool:
    """Returns True if the content is safe, False if it should be hidden."""
    global _api_alarm_sent
    if not settings.ANTHROPIC_API_KEY or not text.strip():
        return True
    try:
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=5,
            messages=[{
                "role": "user",
                "content": (
                    "You are a content moderator for a scientific chemistry paper review platform.\n"
                    "Assess whether the following text is abusive, harassing, defamatory, "
                    "or likely to create legal liability for the platform.\n"
                    "Scientific criticism, negative assessments, and factual claims about "
                    "research quality are ALWAYS allowed and must never be flagged.\n"
                    "Reply with exactly one word: SAFE or FLAG\n\n"
                    f"Text:\n{text[:1500]}"
                ),
            }],
        )
        return "FLAG" not in msg.content[0].text.strip().upper()
    except anthropic.APIError as exc:
        # API reachable but request rejected: likely billing or credit issue
        if not _api_alarm_sent:
            _api_alarm_sent = True
            try:
                from app.utils.email import send_generic_email
                body = (
                    f"The Anthropic API returned an error. "
                    f"AI content moderation is DISABLED until the issue is resolved.\n\n"
                    f"Error: {type(exc).__name__}: {exc}\n\n"
                    "Check credits/billing at console.anthropic.com and verify "
                    "ANTHROPIC_API_KEY is set correctly in Railway."
                )
                send_generic_email(
                    to="dani.kovari@gmail.com",
                    subject="[ChemRepro] CRITICAL: AI moderation offline",
                    body_html=f"<pre style='font-family:sans-serif'>{body}</pre>",
                    body_text=body,
                )
            except Exception:
                pass
        return True  # fail open: never block content on API errors
    except Exception:
        return True  # network/timeout errors: fail open silently


def moderate_comment_bg(comment_id: int) -> None:
    """Background task: AI-check a comment and hide it if flagged."""
    from app.database import SessionLocal
    from app.models.comment import Comment

    db = SessionLocal()
    try:
        comment = db.get(Comment, comment_id)
        if comment and not _check_content(comment.content):
            comment.ai_flagged = True
            db.commit()
            from app.utils.email import notify_admin
            notify_admin(
                f"Comment hidden by AI moderation: {comment.doi}",
                f"Comment ID: {comment.id}\nDOI: {comment.doi}\nUser: {comment.orcid_id}\n\nText:\n{comment.content[:500]}",
            )
    except Exception:
        pass
    finally:
        db.close()


def _send_flag_message(db, rating) -> None:
    """Send an inbox message and notification to the reviewer when their review is flagged."""
    from app.config import settings
    from app.models.message import Message
    from app.models.notification import Notification
    from app.models.paper import Paper
    from app.models.user import User

    orcid = rating.orcid_id
    if not orcid or orcid.startswith("AI-"):
        return
    user = db.get(User, orcid)
    if not user:
        return

    paper = db.get(Paper, rating.doi)
    paper_title = (paper.title[:200] if paper and paper.title else rating.doi)
    base = settings.SITE_URL.rstrip("/")
    edit_link = f"{base}/paper/{rating.doi}/ratings/{rating.id}/edit"

    content = (
        "Your recent review has been automatically hidden from public view because it "
        "was found to contain content not aligned with the ChemRepro community pledge.\n\n"
        f"Edit your review here: {edit_link}\n\n"
        "Please revise the text to bring it in line with our community guidelines. "
        "The review will be re-checked automatically after you save your edits. "
        "If no changes are made, the review may be permanently deleted by a moderator.\n\n"
        "If you believe this was a mistake, please reply to this message."
    )
    db.add(Message(
        thread_id=Message.new_thread_id(),
        sender_orcid_id="admin:chemrepro",
        recipient_orcid_id=orcid,
        content=content,
    ))
    db.add(Notification(
        recipient_orcid_id=orcid,
        type="flagged",
        actor_name="ChemRepro",
        rating_id=rating.id,
        doi=rating.doi,
        paper_title=paper_title,
    ))
    db.commit()


def moderate_rating_bg(rating_id: int) -> None:
    """Background task: AI-check a review's free-text fields and hide it if flagged."""
    from app.database import SessionLocal
    from app.models.rating import Rating

    db = SessionLocal()
    try:
        rating = db.get(Rating, rating_id)
        if rating:
            combined = " ".join(filter(None, [
                rating.reproducibility_observation,
                rating.scope_observation,
                rating.modification_details,
            ]))
            if combined and not _check_content(combined):
                rating.ai_flagged = True
                db.commit()
                _send_flag_message(db, rating)
                from app.utils.email import notify_admin
                notify_admin(
                    f"Review hidden by AI moderation: {rating.doi}",
                    f"Rating ID: {rating.id}\nDOI: {rating.doi}\nUser: {rating.orcid_id}\n\nText:\n{combined[:500]}",
                )
    except Exception:
        pass
    finally:
        db.close()


