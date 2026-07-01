import secrets
import uuid
from datetime import datetime, timezone
from urllib.parse import urlencode

import httpx
from app.utils.design import register_globals
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.user import CAREER_STAGES, User
from app.services.orcid import exchange_code_for_token, fetch_orcid_name, get_auth_url

_LINKEDIN_AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
_LINKEDIN_TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
_LINKEDIN_USERINFO_URL = "https://api.linkedin.com/v2/userinfo"

templates = Jinja2Templates(directory="app/templates")
register_globals(templates)

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
    request.session["user_name"] = user.nickname or user.name or orcid_id

    if not user.career_stage_set:
        request.session["after_profile_setup"] = "/"
        return RedirectResponse("/auth/profile-setup", status_code=303)
    return RedirectResponse("/", status_code=303)


@router.get("/guest-setup")
async def guest_setup_page(request: Request):
    next_url = request.query_params.get("next", "/")
    return templates.TemplateResponse("guest_setup.html", {
        "request": request,
        "next_url": next_url,
    })


@router.post("/guest-setup")
async def guest_setup(
    request: Request,
    db: Session = Depends(get_db),
    display_name: str = Form(...),
    next_url: str = Form(default="/"),
    reconnect_id: str = Form(default=""),
):
    display_name = display_name.strip()[:80]
    if not display_name:
        return RedirectResponse(f"/auth/guest-setup?next={next_url}", status_code=303)

    user = None

    # ── Layer 1: explicit reconnect from localStorage ──────────────────────
    if reconnect_id.startswith("local:"):
        user = db.get(User, reconnect_id)

    # ── Layer 2: name-based reconnect (fallback, unique-name only) ────────
    if user is None:
        matches = (
            db.query(User)
            .filter(User.orcid_id.like("local:%"), User.name == display_name)
            .all()
        )
        if len(matches) == 1:
            user = matches[0]

    # ── Layer 3: create new guest ─────────────────────────────────────────
    if user is None:
        local_id = f"local:{uuid.uuid4()}"
        user = User(orcid_id=local_id, name=display_name, verified_at=datetime.now(timezone.utc))
        db.add(user)
        db.commit()

    request.session["orcid_id"] = user.orcid_id
    request.session["user_name"] = user.nickname or user.name or user.orcid_id
    request.session["after_profile_setup"] = next_url or "/"

    # Skip profile setup if the user already configured their career stage
    if user.career_stage_set:
        return RedirectResponse(next_url or "/", status_code=303)
    return RedirectResponse("/auth/profile-setup", status_code=303)


@router.get("/profile-setup")
async def profile_setup_page(request: Request):
    if not request.session.get("orcid_id"):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse("profile_setup.html", {
        "request": request,
        "career_stages": CAREER_STAGES,
        "user_name": request.session.get("user_name"),
        "orcid_id": request.session.get("orcid_id"),
        "site_version": "standard",
        "switch_urls": {"standard": "/", "classic": "/classic/"},
    })


@router.post("/profile-setup")
async def submit_profile_setup(
    request: Request,
    db: Session = Depends(get_db),
    career_stage: str = Form(default=""),
    nickname: str = Form(default=""),
):
    orcid_id = request.session.get("orcid_id")
    if not orcid_id:
        return RedirectResponse("/", status_code=303)

    user = db.get(User, orcid_id)
    if user:
        if career_stage in CAREER_STAGES:
            user.career_stage = career_stage
        user.career_stage_set = True
        if nickname.strip():
            user.nickname = nickname.strip()[:60]
        db.commit()
        request.session["user_name"] = user.nickname or user.name or orcid_id

    next_url = request.session.pop("after_profile_setup", "/")
    return RedirectResponse(next_url, status_code=303)


@router.get("/profile-setup-skip")
async def skip_profile_setup(request: Request, db: Session = Depends(get_db)):
    orcid_id = request.session.get("orcid_id")
    if orcid_id:
        user = db.get(User, orcid_id)
        if user:
            user.career_stage_set = True
            db.commit()
    next_url = request.session.pop("after_profile_setup", "/")
    return RedirectResponse(next_url, status_code=303)


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    # Redirect through a tiny page that clears guest localStorage before going home
    return RedirectResponse("/auth/signed-out", status_code=303)


@router.get("/signed-out")
async def signed_out(request: Request):
    return templates.TemplateResponse("signed_out.html", {"request": request})


@router.get("/linkedin")
async def linkedin_login(request: Request):
    if not settings.LINKEDIN_CLIENT_ID:
        raise HTTPException(status_code=503, detail="LinkedIn login is not configured yet.")
    state = secrets.token_urlsafe(16)
    request.session["linkedin_state"] = state
    params = urlencode({
        "response_type": "code",
        "client_id": settings.LINKEDIN_CLIENT_ID,
        "redirect_uri": settings.LINKEDIN_REDIRECT_URI,
        "state": state,
        "scope": "openid profile email",
    })
    return RedirectResponse(f"{_LINKEDIN_AUTH_URL}?{params}")


@router.get("/linkedin/callback")
async def linkedin_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
):
    if error:
        raise HTTPException(status_code=400, detail=f"LinkedIn auth error: {error}")
    if not code:
        raise HTTPException(status_code=400, detail="Missing code from LinkedIn")

    saved_state = request.session.pop("linkedin_state", None)
    if not saved_state or saved_state != state:
        raise HTTPException(status_code=400, detail="Invalid OAuth state")

    async with httpx.AsyncClient(timeout=10) as client:
        token_resp = await client.post(_LINKEDIN_TOKEN_URL, data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": settings.LINKEDIN_REDIRECT_URI,
            "client_id": settings.LINKEDIN_CLIENT_ID,
            "client_secret": settings.LINKEDIN_CLIENT_SECRET,
        })
        if token_resp.status_code != 200:
            raise HTTPException(status_code=502, detail="Failed to exchange code with LinkedIn")
        access_token = token_resp.json().get("access_token", "")

        info_resp = await client.get(
            _LINKEDIN_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if info_resp.status_code != 200:
            raise HTTPException(status_code=502, detail="Failed to fetch LinkedIn user info")
        info = info_resp.json()

    sub = info.get("sub", "")
    if not sub:
        raise HTTPException(status_code=502, detail="LinkedIn did not return a user ID")

    linkedin_id = f"linkedin:{sub}"
    display_name = info.get("name") or info.get("given_name") or "LinkedIn User"
    notification_email = info.get("email") or ""

    user = db.get(User, linkedin_id)
    if not user:
        user = User(
            orcid_id=linkedin_id,
            name=display_name,
            notification_email=notification_email or None,
            verified_at=datetime.now(timezone.utc),
        )
        db.add(user)
        db.commit()
    else:
        if notification_email and not user.notification_email:
            user.notification_email = notification_email
            db.commit()

    request.session["orcid_id"] = linkedin_id
    request.session["user_name"] = user.nickname or user.name or linkedin_id

    if not user.career_stage_set:
        request.session["after_profile_setup"] = "/"
        return RedirectResponse("/auth/profile-setup", status_code=303)
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
