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


def _post_login_redirect(user: User, next_url: str) -> RedirectResponse:
    """Central post-login redirect: intercepts for pledge if not yet accepted."""
    if not getattr(user, "pledge_accepted", False):
        return RedirectResponse(f"/pledge?next={next_url}", status_code=303)
    return RedirectResponse(next_url, status_code=303)

DEV_FAKE_USERS = [
    ("0000-0000-0000-0001", "Alice Testuser"),
    ("0000-0000-0000-0002", "Bob Labrat"),
    ("0000-0000-0000-0003", "Carol Benchwork"),
    ("0000-0000-0000-9999", "DanK-ORCID"),
    ("linkedin:dank-linkedin-test", "DanK-LinkedIn"),
]


def _safe_next(url: str) -> str:
    """Allow only relative paths to prevent open-redirect abuse."""
    if url and url.startswith("/") and not url.startswith("//"):
        return url
    return "/"


@router.get("/choose")
async def choose_login(request: Request, error: str | None = None):
    next_url = request.query_params.get("next", "")
    if next_url:
        request.session["login_next"] = _safe_next(next_url)
    return templates.TemplateResponse("login_choose.html", {
        "request": request,
        "error": error,
        "user_name": request.session.get("user_name"),
        "orcid_id": request.session.get("orcid_id"),
    })


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
    # Pop link key immediately so a denied/failed flow never leaves it in session
    link_for = request.session.pop("orcid_link_user", None)

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

    # Account-linking flow: LinkedIn user clicked "Link ORCID"
    if link_for:
        owner = db.get(User, link_for)
        if owner:
            conflict = db.query(User).filter(User.orcid_real == orcid_id).first()
            if conflict and conflict.orcid_id != owner.orcid_id:
                return RedirectResponse("/profile/settings?link_error=orcid_already_linked", status_code=303)
            # Also guard against the real ORCID being an existing primary account
            existing_primary = db.get(User, orcid_id)
            if existing_primary and existing_primary.orcid_id != owner.orcid_id:
                return RedirectResponse("/profile/settings?link_error=orcid_already_linked", status_code=303)
            owner.orcid_real = orcid_id
            db.commit()
        return RedirectResponse("/profile/settings?linked=1", status_code=303)

    # Normal login: check if this ORCID is linked to a LinkedIn-primary account
    linked_owner = db.query(User).filter(User.orcid_real == orcid_id).first()
    if linked_owner:
        request.session["orcid_id"] = linked_owner.orcid_id
        request.session["user_name"] = linked_owner.nickname or linked_owner.name or linked_owner.orcid_id
        if not linked_owner.career_stage_set:
            request.session["after_profile_setup"] = "/"
            return RedirectResponse("/auth/profile-setup", status_code=303)
        return _post_login_redirect(linked_owner, "/")

    # Standard ORCID upsert
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

    login_next = request.session.pop("login_next", "/")
    if not user.career_stage_set:
        request.session["after_profile_setup"] = login_next
        return RedirectResponse("/auth/profile-setup", status_code=303)
    return _post_login_redirect(user, login_next)


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
        return _post_login_redirect(user, next_url or "/")
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

    from app.routers.profile import _nickname_taken, _suggest_nicknames

    user = db.get(User, orcid_id)
    if user:
        nickname_clean = nickname.strip()[:60]
        if nickname_clean and _nickname_taken(nickname_clean, orcid_id, db):
            suggestions = _suggest_nicknames(nickname_clean, orcid_id, orcid_id, db)
            return templates.TemplateResponse("profile_setup.html", {
                "request": request,
                "career_stages": CAREER_STAGES,
                "user_name": request.session.get("user_name"),
                "orcid_id": orcid_id,
                "site_version": "standard",
                "switch_urls": {"standard": "/", "classic": "/classic/"},
                "nickname_error": "taken",
                "nickname_suggestions": suggestions,
                "nickname_input": nickname_clean,
                "selected_career_stage": career_stage,
            })

        if career_stage in CAREER_STAGES:
            user.career_stage = career_stage
        user.career_stage_set = True
        if nickname_clean:
            user.nickname = nickname_clean
        db.commit()
        request.session["user_name"] = user.nickname or user.name or orcid_id

    next_url = request.session.pop("after_profile_setup", "/")
    request.session["tour_pending"] = 1
    return _post_login_redirect(user, next_url) if user else RedirectResponse(next_url, status_code=303)


@router.get("/profile-setup-skip")
async def skip_profile_setup(request: Request, db: Session = Depends(get_db)):
    orcid_id = request.session.get("orcid_id")
    next_url = request.session.pop("after_profile_setup", "/")
    if orcid_id:
        user = db.get(User, orcid_id)
        if user:
            user.career_stage_set = True
            db.commit()
            request.session["tour_pending"] = 1
            return _post_login_redirect(user, next_url)
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
        return RedirectResponse("/auth/choose?error=linkedin_not_configured", status_code=303)
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


@router.get("/link/linkedin")
async def link_linkedin(request: Request):
    """Initiate LinkedIn OAuth for linking to an existing ORCID account."""
    orcid_id = request.session.get("orcid_id")
    if not orcid_id:
        return RedirectResponse("/auth/login", status_code=303)
    if not settings.LINKEDIN_CLIENT_ID:
        return RedirectResponse("/profile/settings?link_error=not_configured", status_code=303)
    request.session["linkedin_link_user"] = orcid_id
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


@router.get("/link/orcid")
async def link_orcid(request: Request):
    """Initiate ORCID OAuth for linking to an existing LinkedIn account."""
    orcid_id = request.session.get("orcid_id")
    if not orcid_id or not orcid_id.startswith("linkedin:"):
        return RedirectResponse("/profile/settings", status_code=303)
    request.session["orcid_link_user"] = orcid_id
    state = secrets.token_urlsafe(16)
    request.session["oauth_state"] = state
    return RedirectResponse(get_auth_url(state))


@router.get("/linkedin/callback")
async def linkedin_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
):
    # Pop link key immediately so a denied/failed flow never leaves it in session
    link_for = request.session.pop("linkedin_link_user", None)

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

    linkedin_key = f"linkedin:{sub}"
    display_name = info.get("name") or info.get("given_name") or "LinkedIn User"
    notification_email = info.get("email") or ""

    # Account-linking flow: user was already logged in and clicked "Link LinkedIn"
    if link_for:
        owner = db.get(User, link_for)
        if owner:
            # Guard: linkedin_key already linked to a different account via linkedin_id column
            conflict = db.query(User).filter(User.linkedin_id == linkedin_key).first()
            if conflict and conflict.orcid_id != owner.orcid_id:
                return RedirectResponse("/profile/settings?link_error=already_linked", status_code=303)
            # Guard: linkedin_key already exists as a primary account (PK)
            existing_primary = db.get(User, linkedin_key)
            if existing_primary and existing_primary.orcid_id != owner.orcid_id:
                return RedirectResponse("/profile/settings?link_error=already_linked", status_code=303)
            owner.linkedin_id = linkedin_key
            db.commit()
        return RedirectResponse("/profile/settings?linked=1", status_code=303)

    # Normal login: look up by linkedin_id column first (linked ORCID account), then by PK
    user = db.query(User).filter(User.linkedin_id == linkedin_key).first()
    if not user:
        user = db.get(User, linkedin_key)
    if not user:
        user = User(
            orcid_id=linkedin_key,
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

    session_key = user.orcid_id
    request.session["orcid_id"] = session_key
    request.session["user_name"] = user.nickname or user.name or session_key

    login_next = request.session.pop("login_next", "/")
    if not user.career_stage_set:
        request.session["after_profile_setup"] = login_next
        return RedirectResponse("/auth/profile-setup", status_code=303)
    return _post_login_redirect(user, login_next)


@router.get("/dev-login/{user_index}")
async def dev_login(user_index: int, request: Request, db: Session = Depends(get_db)):
    """Dev-only fake login — enabled only when ORCID_ENV is explicitly "sandbox"."""
    if settings.ORCID_ENV != "sandbox":
        raise HTTPException(status_code=403, detail="Dev login is disabled outside sandbox")
    if user_index < 0 or user_index >= len(DEV_FAKE_USERS):
        raise HTTPException(status_code=404, detail="Invalid dev user index")

    orcid_id, name = DEV_FAKE_USERS[user_index]
    user = db.get(User, orcid_id)
    if not user:
        user = User(
            orcid_id=orcid_id,
            name=name,
            career_stage="PhD student",
            career_stage_set=True,
            pledge_accepted=True,
            verified_at=datetime.now(timezone.utc),
        )
        db.add(user)
        db.commit()
    else:
        changed = False
        if not user.career_stage_set:
            user.career_stage = "PhD student"
            user.career_stage_set = True
            changed = True
        if not user.pledge_accepted:
            user.pledge_accepted = True
            changed = True
        if changed:
            db.commit()

    request.session["orcid_id"] = orcid_id
    request.session["user_name"] = user.nickname or name
    return RedirectResponse("/", status_code=303)


@router.get("/dev-link/{orcid_idx}/{linkedin_idx}")
async def dev_link_accounts(
    orcid_idx: int,
    linkedin_idx: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """Dev-only: directly link two fake accounts without going through OAuth."""
    if settings.ORCID_ENV != "sandbox":
        raise HTTPException(status_code=403, detail="Dev link is disabled outside sandbox")

    orcid_pk, _ = DEV_FAKE_USERS[orcid_idx]
    linkedin_pk, _ = DEV_FAKE_USERS[linkedin_idx]

    orcid_user = db.get(User, orcid_pk)
    linkedin_user = db.get(User, linkedin_pk)

    if not orcid_user or not linkedin_user:
        raise HTTPException(
            status_code=400,
            detail="Both users must exist first. Visit /auth/dev-login/{idx} for each.",
        )

    orcid_user.linkedin_id = linkedin_pk
    linkedin_user.orcid_real = orcid_pk
    db.commit()
    return RedirectResponse("/profile/settings?linked=1", status_code=303)
