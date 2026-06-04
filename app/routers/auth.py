import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.user import User
from app.services.orcid import exchange_code_for_token, fetch_orcid_name, get_auth_url

router = APIRouter(prefix="/auth", tags=["auth"])

DEV_FAKE_USERS = [
    ("0000-0000-0000-0001", "Alice Testuser"),
    ("0000-0000-0000-0002", "Bob Labrat"),
    ("0000-0000-0000-0003", "Carol Benchwork"),
]


@router.get("/login")
async def login(request: Request):
    """Redirect the user to ORCID for authentication."""
    state = secrets.token_urlsafe(16)
    request.session["oauth_state"] = state
    return RedirectResponse(get_auth_url(state))


@router.get("/callback")
async def callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
):
    if error:
        raise HTTPException(status_code=400, detail=f"ORCID auth error: {error}")
    if not code:
        raise HTTPException(status_code=400, detail="Missing code from ORCID")

    # CSRF check
    saved_state = request.session.pop("oauth_state", None)
    if not saved_state or saved_state != state:
        raise HTTPException(status_code=400, detail="Invalid OAuth state")

    token_data = await exchange_code_for_token(code)
    if not token_data:
        raise HTTPException(status_code=502, detail="Failed to exchange code with ORCID")

    orcid_id: str = token_data.get("orcid", "")
    if not orcid_id:
        raise HTTPException(status_code=502, detail="ORCID did not return an iD")

    # Upsert user
    user = db.get(User, orcid_id)
    if not user:
        display_name = await fetch_orcid_name(orcid_id, token_data.get("access_token", ""))
        user = User(
            orcid_id=orcid_id,
            name=display_name,
            verified_at=datetime.now(timezone.utc),
        )
        db.add(user)
        db.commit()

    request.session["orcid_id"] = orcid_id
    request.session["user_name"] = user.name or orcid_id

    return RedirectResponse("/", status_code=303)


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/", status_code=303)


@router.get("/dev-login/{user_index}")
async def dev_login(user_index: int, request: Request, db: Session = Depends(get_db)):
    """Dev-only fake login — disabled in production."""
    if settings.ORCID_ENV == "production":
        raise HTTPException(status_code=403, detail="Dev login is disabled in production")
    if user_index < 0 or user_index >= len(DEV_FAKE_USERS):
        raise HTTPException(status_code=404, detail="Invalid dev user index")

    orcid_id, name = DEV_FAKE_USERS[user_index]
    user = db.get(User, orcid_id)
    if not user:
        user = User(orcid_id=orcid_id, name=name, verified_at=datetime.now(timezone.utc))
        db.add(user)
        db.commit()

    request.session["orcid_id"] = orcid_id
    request.session["user_name"] = name
    return RedirectResponse("/", status_code=303)
