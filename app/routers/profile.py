from app.utils.design import register_globals
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.comment import Comment
from app.models.like import Like
from app.models.notification import Notification
from app.models.paper import Paper
from app.models.rating import Rating, OUTCOME_LABELS
from app.routers.papers import OUTCOME_SCORES

router = APIRouter(tags=["profile"])
templates = Jinja2Templates(directory="app/templates")
register_globals(templates)


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
