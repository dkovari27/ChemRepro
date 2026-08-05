from app.utils.design import register_globals
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.comment import Comment
from app.models.like import Like
from app.models.notification import Notification
from app.models.paper import Paper
from app.models.paper_subscription import PaperSubscription
from app.models.rating import Rating, OUTCOME_LABELS
from app.models.user import User, CAREER_STAGES
from app.models.user_follow import UserFollow
from app.routers.papers import OUTCOME_SCORES, ND_STAR_LABELS, ND_STAR_COLORS, ND_FAILURE_CONTEXT_LABELS

router = APIRouter(tags=["profile"])
templates = Jinja2Templates(directory="app/templates")
register_globals(templates)


# ── Nickname helpers ──────────────────────────────────────────────────────────

def _nickname_taken(nickname: str, current_user_id: str, db: Session) -> bool:
    """Case-insensitive check: is this nickname already used by someone else?"""
    return db.query(User).filter(
        User.nickname.isnot(None),
        User.orcid_id != current_user_id,
        func.lower(User.nickname) == nickname.strip().lower(),
    ).first() is not None


def _suggest_nicknames(base: str, orcid_id: str, current_user_id: str, db: Session) -> list:
    """Generate up to 4 free nickname alternatives (all verified case-insensitively)."""
    import datetime
    year = str(datetime.datetime.now().year)[-2:]
    if orcid_id.startswith("linkedin:"):
        id_suffix = orcid_id.replace("linkedin:", "")[-4:]
    else:
        id_suffix = orcid_id.replace("-", "")[-4:]

    candidates = [
        f"{base}2",
        f"{base}{year}",
        f"{base}_{id_suffix}",
        f"{base}3",
    ]
    # Remove duplicate lower-case entries while preserving order
    seen: set = set()
    unique = [c for c in candidates if not (c.lower() in seen or seen.add(c.lower()))]

    # Single query to find which are taken
    taken_rows = db.query(User.nickname).filter(
        User.nickname.isnot(None),
        User.orcid_id != current_user_id,
        func.lower(User.nickname).in_([c.lower() for c in unique]),
    ).all()
    taken_lower = {row[0].lower() for row in taken_rows}

    return [c for c in unique if c.lower() not in taken_lower][:4]


@router.get("/profile/nickname-check")
async def nickname_check(request: Request, q: str = "", db: Session = Depends(get_db)):
    """Live availability check used by the debounced input handler."""
    orcid_id = request.session.get("orcid_id") or ""
    q = q.strip()[:60]
    if not q:
        return JSONResponse({"taken": False, "suggestions": []})
    taken = _nickname_taken(q, orcid_id, db)
    suggestions = _suggest_nicknames(q, orcid_id, orcid_id, db) if taken else []
    return JSONResponse({"taken": taken, "suggestions": suggestions})


@router.get("/profile/my-reviews", response_class=HTMLResponse)
async def my_reviews(request: Request, db: Session = Depends(get_db)):
    orcid_id = request.session.get("orcid_id")
    if not orcid_id:
        return RedirectResponse("/auth/login", status_code=303)

    ratings = (
        db.query(Rating)
        .filter(Rating.orcid_id == orcid_id)
        .order_by(Rating.created_at.desc())
        .all()
    )

    # Collect DOIs and fetch papers in one query
    dois = list({r.doi for r in ratings})
    papers_map = {p.doi: p for p in db.query(Paper).filter(Paper.doi.in_(dois)).all()}

    # Counts
    rating_ids = [r.id for r in ratings]
    like_rows = (
        db.query(Like.rating_id, func.count(Like.id))
        .filter(Like.rating_id.in_(rating_ids))
        .group_by(Like.rating_id)
        .all()
    ) if rating_ids else []
    like_counts = {rid: cnt for rid, cnt in like_rows}

    comment_rows = (
        db.query(Comment.rating_id, func.count(Comment.id))
        .filter(Comment.rating_id.in_(rating_ids))
        .group_by(Comment.rating_id)
        .all()
    ) if rating_ids else []
    comment_counts = {rid: cnt for rid, cnt in comment_rows}

    return templates.TemplateResponse("my_reviews.html", {
        "request": request,
        "ratings": ratings,
        "papers_map": papers_map,
        "like_counts": like_counts,
        "comment_counts": comment_counts,
        "outcome_labels": OUTCOME_LABELS,
        "outcome_scores": OUTCOME_SCORES,
        "nd_star_labels": ND_STAR_LABELS,
        "nd_star_colors": ND_STAR_COLORS,
        "nd_failure_context_labels": ND_FAILURE_CONTEXT_LABELS,
        "user_name": request.session.get("user_name"),
        "orcid_id": orcid_id,
        "site_version": "standard",
        "switch_urls": {"standard": "/", "classic": "/classic/"},
    })


@router.get("/profile/notifications", response_class=HTMLResponse)
async def notifications_page(request: Request, db: Session = Depends(get_db)):
    orcid_id = request.session.get("orcid_id")
    if not orcid_id:
        return RedirectResponse("/auth/login", status_code=303)

    notifs = (
        db.query(Notification)
        .filter(Notification.recipient_orcid_id == orcid_id)
        .order_by(Notification.created_at.desc())
        .limit(100)
        .all()
    )

    # Mark all as read
    db.query(Notification).filter(
        Notification.recipient_orcid_id == orcid_id,
        Notification.is_read == False,  # noqa: E712
    ).update({"is_read": True})
    db.commit()

    return templates.TemplateResponse("notifications.html", {
        "request": request,
        "notifications": notifs,
        "user_name": request.session.get("user_name"),
        "orcid_id": orcid_id,
        "site_version": "standard",
        "switch_urls": {"standard": "/", "classic": "/classic/"},
    })


@router.get("/profile/notifications/count")
async def notification_count(request: Request, db: Session = Depends(get_db)):
    orcid_id = request.session.get("orcid_id")
    if not orcid_id:
        return JSONResponse({"unread": 0})
    count = (
        db.query(func.count(Notification.id))
        .filter(
            Notification.recipient_orcid_id == orcid_id,
            Notification.is_read == False,  # noqa: E712
        )
        .scalar()
    )
    return JSONResponse({"unread": count or 0})


@router.get("/profile/settings", response_class=HTMLResponse)
async def settings_page(request: Request, db: Session = Depends(get_db)):
    orcid_id = request.session.get("orcid_id")
    if not orcid_id:
        return RedirectResponse("/auth/login", status_code=303)
    user = db.query(User).filter(User.orcid_id == orcid_id).first()
    return templates.TemplateResponse("profile_settings.html", {
        "request": request,
        "user": user,
        "career_stages": CAREER_STAGES,
        "saved": request.query_params.get("saved") == "1",
        "linked": request.query_params.get("linked") == "1",
        "link_error": request.query_params.get("link_error", ""),
        "nickname_error": "",
        "nickname_suggestions": [],
        "nickname_input": "",
        "user_name": request.session.get("user_name"),
        "orcid_id": orcid_id,
        "site_version": "standard",
        "switch_urls": {"standard": "/", "classic": "/classic/"},
    })


@router.post("/profile/settings")
async def save_settings(
    request: Request,
    db: Session = Depends(get_db),
    nickname: str = Form(""),
    notification_email: str = Form(""),
    career_stage: str = Form(""),
):
    orcid_id = request.session.get("orcid_id")
    if not orcid_id:
        return RedirectResponse("/auth/login", status_code=303)
    user = db.query(User).filter(User.orcid_id == orcid_id).first()
    if not user:
        return RedirectResponse("/profile/settings", status_code=303)

    nickname_clean = nickname.strip()[:60]

    # Nickname conflict check (only when user doesn't have one yet)
    if nickname_clean and not user.nickname:
        if _nickname_taken(nickname_clean, orcid_id, db):
            suggestions = _suggest_nicknames(nickname_clean, orcid_id, orcid_id, db)
            return templates.TemplateResponse("profile_settings.html", {
                "request": request,
                "user": user,
                "career_stages": CAREER_STAGES,
                "saved": False,
                "linked": False,
                "link_error": "",
                "nickname_error": "taken",
                "nickname_suggestions": suggestions,
                "nickname_input": nickname_clean,
                "user_name": request.session.get("user_name"),
                "orcid_id": orcid_id,
                "site_version": "standard",
                "switch_urls": {"standard": "/", "classic": "/classic/"},
            })
        user.nickname = nickname_clean

    user.notification_email = notification_email.strip() or None
    if career_stage in CAREER_STAGES:
        user.career_stage = career_stage
        user.career_stage_set = True
    db.commit()
    request.session["user_name"] = user.nickname or user.name or orcid_id
    return RedirectResponse("/profile/settings?saved=1", status_code=303)


@router.get("/profile/subscriptions", response_class=HTMLResponse)
async def subscriptions_page(request: Request, db: Session = Depends(get_db)):
    orcid_id = request.session.get("orcid_id")
    if not orcid_id:
        return RedirectResponse("/auth/login", status_code=303)

    paper_subs = (
        db.query(PaperSubscription)
        .filter(PaperSubscription.orcid_id == orcid_id)
        .order_by(PaperSubscription.created_at.desc())
        .all()
    )
    dois = [s.doi for s in paper_subs]
    papers_map = {p.doi: p for p in db.query(Paper).filter(Paper.doi.in_(dois)).all()} if dois else {}

    user_follows = (
        db.query(UserFollow)
        .filter(UserFollow.follower_orcid_id == orcid_id)
        .order_by(UserFollow.created_at.desc())
        .all()
    )
    followed_ids = [f.followed_orcid_id for f in user_follows]
    users_map = {u.orcid_id: u for u in db.query(User).filter(User.orcid_id.in_(followed_ids)).all()} if followed_ids else {}

    return templates.TemplateResponse("profile_subscriptions.html", {
        "request": request,
        "paper_subs": paper_subs,
        "papers_map": papers_map,
        "user_follows": user_follows,
        "users_map": users_map,
        "user_name": request.session.get("user_name"),
        "orcid_id": orcid_id,
        "site_version": "standard",
        "switch_urls": {"standard": "/", "classic": "/classic/"},
    })
