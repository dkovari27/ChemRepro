from app.utils.design import register_globals
from fastapi import APIRouter, BackgroundTasks, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.feedback import Feedback
from app.models.name_suggestion import NameSuggestion, NameVote
from app.routers.admin import _require_admin
from app.utils.email import send_feedback_notification

router = APIRouter(tags=["feedback"])
templates = Jinja2Templates(directory="app/templates")
register_globals(templates)

VALID_PREFS = {"standard", "classic", "both", "unsure"}


def _voter_id(request: Request) -> str | None:
    """Returns the stable voter ID for a properly authenticated user (ORCID or LinkedIn).
    Returns None for anonymous visitors and guest (local:) accounts."""
    orcid = request.session.get("orcid_id")
    if not orcid or orcid.startswith("local:"):
        return None
    return orcid


def _get_suggestions(db: Session, voter_id: str) -> list[dict]:
    suggestions = (
        db.query(NameSuggestion).order_by(NameSuggestion.id.asc()).all()
    )
    voted_ids = {
        v.suggestion_id
        for v in db.query(NameVote).filter(NameVote.voter_id == voter_id).all()
    }
    return [
        {
            "id": s.id,
            "name": s.name,
            "votes": len(s.votes),
            "voted": s.id in voted_ids,
        }
        for s in sorted(suggestions, key=lambda s: len(s.votes), reverse=True)
    ]


def _upsert_names(raw: str, voter_id: str, db: Session) -> None:
    for raw_name in raw.split(","):
        name = raw_name.strip()[:100]
        if not name:
            continue
        existing = db.query(NameSuggestion).filter(
            NameSuggestion.name.ilike(name)
        ).first()
        if existing:
            suggestion = existing
        else:
            suggestion = NameSuggestion(name=name)
            db.add(suggestion)
            try:
                db.flush()
            except IntegrityError:
                db.rollback()
                suggestion = db.query(NameSuggestion).filter(
                    NameSuggestion.name.ilike(name)
                ).first()
                if not suggestion:
                    continue
        if suggestion and not db.query(NameVote).filter(
            NameVote.suggestion_id == suggestion.id,
            NameVote.voter_id == voter_id,
        ).first():
            db.add(NameVote(suggestion_id=suggestion.id, voter_id=voter_id))
    db.commit()


@router.get("/feedback", response_class=HTMLResponse)
async def feedback_page(request: Request, db: Session = Depends(get_db)):
    voter_id = _voter_id(request)
    return templates.TemplateResponse("feedback.html", {
        "request": request,
        "user_name": request.session.get("user_name"),
        "orcid_id": request.session.get("orcid_id"),
        "submitted": request.query_params.get("submitted") == "1",
        "bug_doi": request.query_params.get("doi", ""),
        "suggestions": _get_suggestions(db, voter_id) if voter_id else _get_suggestions(db, ""),
        "can_vote": voter_id is not None,
        "site_version": "new_design",
        "switch_urls": {"standard": "/design-archive/standard/", "classic": "/classic/", "new_design": "/nd/"},
    })


@router.post("/feedback")
async def submit_feedback(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    preference: str = Form(""),
    comment: str = Form(""),
    submitter_name: str = Form(""),
    submitter_email: str = Form(""),
):
    orcid_id = request.session.get("orcid_id")

    # Non-logged-in users must supply name + email
    if not orcid_id:
        if not submitter_name.strip() or not submitter_email.strip():
            return RedirectResponse("/feedback?error=contact_required", status_code=303)

    ua = request.headers.get("user-agent", "")
    client_device = "mobile" if any(k in ua for k in ("Mobile", "Android", "iPhone")) else "desktop"

    trimmed_comment = comment.strip()[:2000] or None
    db.add(Feedback(
        preference="",
        comment=trimmed_comment,
        orcid_id=orcid_id,
        submitter_name=submitter_name.strip()[:255] or None,
        submitter_email=submitter_email.strip()[:255] or None,
        client_device=client_device,
    ))
    db.commit()
    background_tasks.add_task(
        send_feedback_notification, "", trimmed_comment, orcid_id,
        submitter_name.strip() or None,
        submitter_email.strip() or None,
    )
    return RedirectResponse("/feedback?submitted=1", status_code=303)


@router.post("/feedback/suggest")
async def add_suggestion(
    request: Request,
    db: Session = Depends(get_db),
    suggested_names: str = Form(""),
):
    voter_id = _voter_id(request)
    if not voter_id:
        return RedirectResponse("/auth/choose?next=/feedback", status_code=303)
    if suggested_names.strip():
        _upsert_names(suggested_names, voter_id, db)
    return RedirectResponse("/feedback", status_code=303)


@router.post("/feedback/vote/{suggestion_id}")
async def toggle_vote(
    suggestion_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    voter_id = _voter_id(request)
    if not voter_id:
        return JSONResponse({"error": "login_required"}, status_code=401)

    suggestion = db.get(NameSuggestion, suggestion_id)
    if not suggestion:
        return JSONResponse({"error": "not found"}, status_code=404)

    existing = db.query(NameVote).filter(
        NameVote.suggestion_id == suggestion_id,
        NameVote.voter_id == voter_id,
    ).first()

    if existing:
        db.delete(existing)
        db.commit()
        voted = False
    else:
        db.add(NameVote(suggestion_id=suggestion_id, voter_id=voter_id))
        db.commit()
        voted = True

    db.refresh(suggestion)
    return JSONResponse({"voted": voted, "votes": len(suggestion.votes)})


@router.get("/admin/feedback", response_class=HTMLResponse)
async def admin_feedback(request: Request, db: Session = Depends(get_db)):
    _require_admin(request)
    responses = db.query(Feedback).order_by(Feedback.created_at.desc()).all()
    counts = {p: sum(1 for r in responses if r.preference == p) for p in VALID_PREFS}
    return templates.TemplateResponse("admin_feedback.html", {
        "request": request,
        "responses": responses,
        "counts": counts,
        "total": len(responses),
        "user_name": request.session.get("user_name"),
        "orcid_id": request.session.get("orcid_id"),
        "site_version": "standard",
        "switch_urls": {"standard": "/", "classic": "/classic/"},
    })
