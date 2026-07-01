from datetime import datetime, timezone

from app.utils.design import register_globals
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.comment import Comment, CommentLike
from app.models.like import Like
from app.models.message import Message
from app.models.notification import Notification
from app.models.paper import Paper
from app.models.paper_subscription import PaperSubscription
from app.models.rating import Rating
from app.models.report import Report
from app.models.user import User
from app.models.user_follow import UserFollow

ADMIN_ORCID = "admin:chemrepro"

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory="app/templates")
register_globals(templates)


def _require_admin(request: Request):
    if request.session.get("orcid_id") != ADMIN_ORCID:
        raise HTTPException(status_code=403, detail="Admin access required")


def _base(request: Request) -> dict:
    return {
        "request": request,
        "user_name": request.session.get("user_name"),
        "orcid_id": request.session.get("orcid_id"),
        "site_version": "standard",
        "switch_urls": {"standard": "/", "classic": "/classic/"},
    }


# ── Secret login URL ──────────────────────────────────────────────────────────

@router.get("/login/{token}")
async def admin_login(token: str, request: Request, db: Session = Depends(get_db)):
    if token != settings.ADMIN_SECRET_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid token")
    # Ensure admin user exists
    admin = db.get(User, ADMIN_ORCID)
    if not admin:
        admin = User(
            orcid_id=ADMIN_ORCID,
            name="ChemReproAdmin",
            verified_at=datetime.now(timezone.utc),
        )
        db.add(admin)
        db.commit()
    request.session["orcid_id"] = ADMIN_ORCID
    request.session["user_name"] = "ChemReproAdmin"
    request.session["is_admin"] = True
    return RedirectResponse("/admin/", status_code=303)


# ── Dashboard ─────────────────────────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
async def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    _require_admin(request)

    stats = {
        "users":    db.query(func.count(User.orcid_id)).scalar(),
        "papers":   db.query(func.count(Paper.doi)).scalar(),
        "reviews":  db.query(func.count(Rating.id)).scalar(),
        "comments": db.query(func.count(Comment.id)).scalar(),
        "reports":  db.query(func.count(Report.id)).filter(Report.resolved == False).scalar(),  # noqa: E712
        "messages": db.query(func.count(Message.id)).scalar(),
    }

    open_reports = (
        db.query(Report)
        .filter(Report.resolved == False)  # noqa: E712
        .order_by(Report.created_at.desc())
        .limit(50)
        .all()
    )

    recent_reviews = (
        db.query(Rating)
        .order_by(Rating.created_at.desc())
        .limit(30)
        .all()
    )

    recent_users = (
        db.query(User)
        .filter(User.orcid_id != ADMIN_ORCID)
        .order_by(User.verified_at.desc())
        .limit(30)
        .all()
    )

    all_users = (
        db.query(User)
        .filter(User.orcid_id != ADMIN_ORCID)
        .order_by(User.verified_at.desc())
        .all()
    )

    recent_comments = (
        db.query(Comment)
        .order_by(Comment.created_at.desc())
        .limit(30)
        .all()
    )

    papers_map = {p.doi: p for p in db.query(Paper).all()}
    users_map = {u.orcid_id: u for u in db.query(User).all()}

    return templates.TemplateResponse("admin_dashboard.html", {
        **_base(request),
        "stats": stats,
        "open_reports": open_reports,
        "recent_reviews": recent_reviews,
        "recent_comments": recent_comments,
        "recent_users": recent_users,
        "all_users": all_users,
        "papers_map": papers_map,
        "users_map": users_map,
    })


# ── Delete any review ─────────────────────────────────────────────────────────

@router.post("/reviews/{rating_id}/delete")
async def admin_delete_review(rating_id: int, request: Request, db: Session = Depends(get_db)):
    _require_admin(request)
    r = db.get(Rating, rating_id)
    if not r:
        return JSONResponse({"error": "not found"}, status_code=404)
    db.query(Like).filter(Like.rating_id == rating_id).delete()
    db.query(Comment).filter(Comment.rating_id == rating_id).delete()
    db.query(Notification).filter(Notification.rating_id == rating_id).delete()
    db.delete(r)
    db.commit()
    return JSONResponse({"ok": True})


# ── Delete any comment ────────────────────────────────────────────────────────

@router.post("/comments/{comment_id}/delete")
async def admin_delete_comment(comment_id: int, request: Request, db: Session = Depends(get_db)):
    _require_admin(request)
    c = db.get(Comment, comment_id)
    if not c:
        return JSONResponse({"error": "not found"}, status_code=404)
    db.query(CommentLike).filter(CommentLike.comment_id == comment_id).delete()
    # Delete replies
    replies = db.query(Comment).filter(Comment.parent_id == comment_id).all()
    for rep in replies:
        db.query(CommentLike).filter(CommentLike.comment_id == rep.id).delete()
        db.delete(rep)
    db.delete(c)
    db.commit()
    return JSONResponse({"ok": True})


# ── Delete any user ───────────────────────────────────────────────────────────

@router.post("/users/{orcid_id:path}/delete")
async def admin_delete_user(orcid_id: str, request: Request, db: Session = Depends(get_db)):
    _require_admin(request)
    if orcid_id == ADMIN_ORCID:
        return JSONResponse({"error": "cannot delete admin"}, status_code=400)
    user = db.get(User, orcid_id)
    if not user:
        return JSONResponse({"error": "not found"}, status_code=404)
    # Cascade: delete all content by this user
    rating_ids = [r.id for r in db.query(Rating.id).filter(Rating.orcid_id == orcid_id).all()]
    for rid in rating_ids:
        db.query(Like).filter(Like.rating_id == rid).delete()
        db.query(Comment).filter(Comment.rating_id == rid).delete()
        db.query(Notification).filter(Notification.rating_id == rid).delete()
    db.query(Rating).filter(Rating.orcid_id == orcid_id).delete()
    db.query(Comment).filter(Comment.orcid_id == orcid_id).delete()
    db.query(Like).filter(Like.orcid_id == orcid_id).delete()
    db.query(CommentLike).filter(CommentLike.orcid_id == orcid_id).delete()
    db.query(Notification).filter(Notification.recipient_orcid_id == orcid_id).delete()
    db.query(Message).filter(
        (Message.sender_orcid_id == orcid_id) | (Message.recipient_orcid_id == orcid_id)
    ).delete()
    db.query(UserFollow).filter(
        (UserFollow.follower_orcid_id == orcid_id) | (UserFollow.followed_orcid_id == orcid_id)
    ).delete()
    db.query(PaperSubscription).filter(PaperSubscription.orcid_id == orcid_id).delete()
    db.query(Report).filter(Report.reporter_orcid_id == orcid_id).delete()
    db.delete(user)
    db.commit()
    return JSONResponse({"ok": True})


# ── Delete any message ────────────────────────────────────────────────────────

@router.post("/messages/{message_id}/delete")
async def admin_delete_message(message_id: int, request: Request, db: Session = Depends(get_db)):
    _require_admin(request)
    m = db.get(Message, message_id)
    if not m:
        return JSONResponse({"error": "not found"}, status_code=404)
    db.delete(m)
    db.commit()
    return JSONResponse({"ok": True})


# ── Resolve / dismiss a report ────────────────────────────────────────────────

@router.post("/reports/{report_id}/resolve")
async def admin_resolve_report(report_id: int, request: Request, db: Session = Depends(get_db)):
    _require_admin(request)
    r = db.get(Report, report_id)
    if not r:
        return JSONResponse({"error": "not found"}, status_code=404)
    r.resolved = True
    db.commit()
    return JSONResponse({"ok": True})


# ── Ban / unban a user (sets name to [banned]) ────────────────────────────────

@router.post("/users/{orcid_id:path}/ban")
async def admin_ban_user(orcid_id: str, request: Request, db: Session = Depends(get_db)):
    _require_admin(request)
    if orcid_id == ADMIN_ORCID:
        return JSONResponse({"error": "cannot ban admin"}, status_code=400)
    user = db.get(User, orcid_id)
    if not user:
        return JSONResponse({"error": "not found"}, status_code=404)
    user.nickname = "[banned]"
    user.name = "[banned]"
    db.commit()
    return JSONResponse({"ok": True})


# ── Delete an entire paper and all its data ───────────────────────────────────

@router.post("/papers/{doi:path}/delete")
async def admin_delete_paper(doi: str, request: Request, db: Session = Depends(get_db)):
    _require_admin(request)
    paper = db.get(Paper, doi)
    if not paper:
        return JSONResponse({"error": "not found"}, status_code=404)
    rating_ids = [r.id for r in db.query(Rating.id).filter(Rating.doi == doi).all()]
    for rid in rating_ids:
        db.query(Like).filter(Like.rating_id == rid).delete()
        db.query(Notification).filter(Notification.rating_id == rid).delete()
    db.query(Comment).filter(Comment.doi == doi).delete()
    db.query(Rating).filter(Rating.doi == doi).delete()
    db.query(PaperSubscription).filter(PaperSubscription.doi == doi).delete()
    db.delete(paper)
    db.commit()
    return JSONResponse({"ok": True})
