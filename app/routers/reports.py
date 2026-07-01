from app.utils.design import register_globals
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.report import Report

router = APIRouter(tags=["reports"])
from fastapi.templating import Jinja2Templates
templates = Jinja2Templates(directory="app/templates")
register_globals(templates)


@router.post("/report")
async def submit_report(
    request: Request,
    db: Session = Depends(get_db),
    target_type: str = Form(...),
    target_id: str = Form(...),
    reason: str = Form(default=""),
):
    orcid_id = request.session.get("orcid_id")
    if not orcid_id:
        return JSONResponse({"error": "not authenticated"}, status_code=401)
    if target_type not in ("review", "comment", "user"):
        return JSONResponse({"error": "invalid target type"}, status_code=422)

    db.add(Report(
        reporter_orcid_id=orcid_id,
        target_type=target_type,
        target_id=str(target_id),
        reason=reason.strip()[:500] or None,
    ))
    db.commit()
    return JSONResponse({"ok": True})
