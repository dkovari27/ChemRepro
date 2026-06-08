from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.feedback import Feedback
from app.utils.email import send_feedback_notification

router = APIRouter(tags=["feedback"])
templates = Jinja2Templates(directory="app/templates")

VALID_PREFS = {"standard", "classic", "both", "unsure"}


@router.get("/feedback", response_class=HTMLResponse)
async def feedback_page(request: Request):
    return templates.TemplateResponse("feedback.html", {
        "request": request,
        "user_name": request.session.get("user_name"),
        "orcid_id": request.session.get("orcid_id"),
        "submitted": request.query_params.get("submitted") == "1",
        "site_version": "standard",
        "switch_urls": {"standard": "/", "classic": "/classic/"},
    })


@router.post("/feedback")
async def submit_feedback(
    request: Request,
    db: Session = Depends(get_db),
    preference: str = Form(""),
    comment: str = Form(""),
):
    if preference not in VALID_PREFS:
        return RedirectResponse("/feedback", status_code=303)

    orcid_id = request.session.get("orcid_id")
    trimmed_comment = comment.strip()[:2000] or None
    db.add(Feedback(
        preference=preference,
        comment=trimmed_comment,
        orcid_id=orcid_id,
    ))
    db.commit()
    await send_feedback_notification(preference, trimmed_comment, orcid_id)
    return RedirectResponse("/feedback?submitted=1", status_code=303)


@router.get("/admin/feedback", response_class=HTMLResponse)
async def admin_feedback(request: Request, db: Session = Depends(get_db)):
    if settings.ORCID_ENV == "production":
        from fastapi import HTTPException
        raise HTTPException(status_code=403)
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
