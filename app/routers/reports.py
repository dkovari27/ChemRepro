from app.utils.design import register_globals
from fastapi import APIRouter, BackgroundTasks, Depends, Form, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.report import Report
from app.models.rating import Rating
from app.models.comment import Comment
from app.models.message import Message
from app.models.user import User

router = APIRouter(tags=["reports"])
from fastapi.templating import Jinja2Templates
templates = Jinja2Templates(directory="app/templates")
register_globals(templates)


def _send_defamatory_notice(db: Session, orcid_id: str, target_type: str, target_id: str) -> None:
    """Send inbox message to content author when their content is reported as defamatory."""
    from app.models.notification import Notification
    user = db.get(User, orcid_id)
    if not user:
        return
    content = (
        f"A report has been filed indicating that your {target_type} (ID: {target_id}) "
        "may contain defamatory content. It has been temporarily hidden while the admin "
        "reviews the report within 48-72 hours.\n\n"
        "If the content is found to be within our community guidelines, it will be "
        "restored. If you believe this report was filed in bad faith, please reply to "
        "this message with your explanation."
    )
    db.add(Message(
        thread_id=Message.new_thread_id(),
        sender_orcid_id="admin:chemrepro",
        recipient_orcid_id=orcid_id,
        content=content,
    ))
    db.commit()


@router.post("/report")
async def submit_report(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    target_type: str = Form(...),
    target_id: str = Form(...),
    reason: str = Form(default=""),
    is_defamatory: str = Form(default=""),
):
    orcid_id = request.session.get("orcid_id")
    if not orcid_id:
        return JSONResponse({"error": "not authenticated"}, status_code=401)
    if target_type not in ("review", "comment", "user"):
        return JSONResponse({"error": "invalid target type"}, status_code=422)

    flagged_as_defamatory = is_defamatory == "true"

    report = Report(
        reporter_orcid_id=orcid_id,
        target_type=target_type,
        target_id=str(target_id),
        reason=reason.strip()[:500] or None,
        is_defamatory=flagged_as_defamatory,
    )
    db.add(report)

    content_author_orcid = None
    if flagged_as_defamatory:
        if target_type == "review":
            r = db.get(Rating, int(target_id))
            if r:
                content_author_orcid = r.orcid_id
                r.ai_flagged = True
        elif target_type == "comment":
            c = db.get(Comment, int(target_id))
            if c:
                content_author_orcid = c.orcid_id
                c.ai_flagged = True

    db.commit()

    if flagged_as_defamatory and content_author_orcid:
        background_tasks.add_task(
            _send_defamatory_notice, db, content_author_orcid, target_type, target_id
        )
        from app.utils.email import notify_admin
        background_tasks.add_task(
            notify_admin,
            f"URGENT: Defamatory report filed — {target_type} {target_id}",
            f"Reporter: {orcid_id}\nTarget: {target_type} ID {target_id}\nReason: {reason[:300]}\n\nContent has been IMMEDIATELY HIDDEN. Review at /admin/",
        )
    else:
        from app.utils.email import notify_admin
        background_tasks.add_task(
            notify_admin,
            f"New report: {target_type} {target_id}",
            f"Reporter: {orcid_id}\nTarget: {target_type} ID {target_id}\nReason: {reason[:300]}\n\nReview at /admin/",
        )

    return JSONResponse({"ok": True})
