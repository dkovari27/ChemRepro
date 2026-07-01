from app.utils.design import register_globals
from app.utils.moderation import is_clean as _is_clean
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.message import Message
from app.models.user import User


router = APIRouter(prefix="/profile", tags=["messages"])
templates = Jinja2Templates(directory="app/templates")
register_globals(templates)


def _base_ctx(request: Request) -> dict:
    return {
        "request": request,
        "user_name": request.session.get("user_name"),
        "orcid_id": request.session.get("orcid_id"),
        "site_version": "standard",
        "switch_urls": {"standard": "/", "classic": "/classic/"},
    }


@router.get("/inbox/count")
async def inbox_unread_count(request: Request, db: Session = Depends(get_db)):
    orcid_id = request.session.get("orcid_id")
    if not orcid_id:
        return JSONResponse({"unread": 0})
    count = db.query(Message).filter(
        Message.recipient_orcid_id == orcid_id,
        Message.is_read == False,  # noqa: E712
    ).count()
    return JSONResponse({"unread": count})


@router.get("/inbox", response_class=HTMLResponse)
async def inbox(request: Request, db: Session = Depends(get_db)):
    orcid_id = request.session.get("orcid_id")
    if not orcid_id:
        return RedirectResponse("/auth/login", status_code=303)

    # Get the most recent message per thread where user is sender or recipient
    all_msgs = (
        db.query(Message)
        .filter(
            or_(Message.sender_orcid_id == orcid_id, Message.recipient_orcid_id == orcid_id)
        )
        .order_by(Message.created_at.desc())
        .all()
    )

    # Group by thread_id, keep only the latest per thread
    seen: set[str] = set()
    threads: list[dict] = []
    for msg in all_msgs:
        if msg.thread_id in seen:
            continue
        seen.add(msg.thread_id)
        other_id = msg.recipient_orcid_id if msg.sender_orcid_id == orcid_id else msg.sender_orcid_id
        other_user = db.get(User, other_id)
        unread = db.query(Message).filter(
            Message.thread_id == msg.thread_id,
            Message.recipient_orcid_id == orcid_id,
            Message.is_read == False,  # noqa: E712
        ).count()
        threads.append({
            "thread_id": msg.thread_id,
            "other_user": other_user,
            "last_message": msg,
            "unread": unread,
        })

    return templates.TemplateResponse("inbox.html", {**_base_ctx(request), "threads": threads})


@router.get("/inbox/{thread_id}", response_class=HTMLResponse)
async def view_thread(thread_id: str, request: Request, db: Session = Depends(get_db)):
    orcid_id = request.session.get("orcid_id")
    if not orcid_id:
        return RedirectResponse("/auth/login", status_code=303)

    messages = (
        db.query(Message)
        .filter(Message.thread_id == thread_id)
        .filter(or_(Message.sender_orcid_id == orcid_id, Message.recipient_orcid_id == orcid_id))
        .order_by(Message.created_at.asc())
        .all()
    )
    if not messages:
        raise HTTPException(status_code=404, detail="Thread not found")

    # Mark unread messages as read
    for msg in messages:
        if msg.recipient_orcid_id == orcid_id and not msg.is_read:
            msg.is_read = True
    db.commit()

    other_id = (
        messages[0].recipient_orcid_id
        if messages[0].sender_orcid_id == orcid_id
        else messages[0].sender_orcid_id
    )
    other_user = db.get(User, other_id)

    return templates.TemplateResponse("thread.html", {
        **_base_ctx(request),
        "messages": messages,
        "thread_id": thread_id,
        "other_user": other_user,
    })


@router.post("/inbox/{thread_id}/reply")
async def reply_thread(
    thread_id: str,
    request: Request,
    db: Session = Depends(get_db),
    content: str = Form(""),
):
    orcid_id = request.session.get("orcid_id")
    if not orcid_id:
        return RedirectResponse("/auth/login", status_code=303)
    content = content.strip()[:5000]
    if not content:
        return RedirectResponse(f"/profile/inbox/{thread_id}", status_code=303)
    if not _is_clean(content):
        raise HTTPException(status_code=422, detail="Message contains prohibited language.")

    # Verify user is part of this thread
    existing = (
        db.query(Message)
        .filter(
            Message.thread_id == thread_id,
            or_(Message.sender_orcid_id == orcid_id, Message.recipient_orcid_id == orcid_id),
        )
        .first()
    )
    if not existing:
        raise HTTPException(status_code=403, detail="Not your thread")

    recipient_id = (
        existing.recipient_orcid_id
        if existing.sender_orcid_id == orcid_id
        else existing.sender_orcid_id
    )
    db.add(Message(
        thread_id=thread_id,
        sender_orcid_id=orcid_id,
        recipient_orcid_id=recipient_id,
        content=content,
    ))
    db.commit()
    return RedirectResponse(f"/profile/inbox/{thread_id}", status_code=303)


@router.post("/messages/new")
async def new_message(
    request: Request,
    db: Session = Depends(get_db),
    recipient_orcid_id: str = Form(...),
    content: str = Form(""),
    source_doi: str = Form(default=""),
):
    orcid_id = request.session.get("orcid_id")
    if not orcid_id:
        return RedirectResponse("/auth/login", status_code=303)
    content = content.strip()[:5000]
    if not content or orcid_id == recipient_orcid_id:
        return RedirectResponse(request.headers.get("referer", "/"), status_code=303)
    if not _is_clean(content):
        raise HTTPException(status_code=422, detail="Message contains prohibited language.")

    thread_id = Message.new_thread_id()
    db.add(Message(
        thread_id=thread_id,
        sender_orcid_id=orcid_id,
        recipient_orcid_id=recipient_orcid_id,
        content=content,
    ))
    db.commit()
    return RedirectResponse(f"/profile/inbox/{thread_id}", status_code=303)
