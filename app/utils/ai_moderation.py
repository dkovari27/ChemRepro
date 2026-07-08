import anthropic
from app.config import settings


def _check_content(text: str) -> bool:
    """Returns True if the content is safe, False if it should be hidden."""
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
        return msg.content[0].text.strip().upper() != "FLAG"
    except Exception:
        return True  # fail open -- never block on API errors


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
    except Exception:
        pass
    finally:
        db.close()


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
    except Exception:
        pass
    finally:
        db.close()
