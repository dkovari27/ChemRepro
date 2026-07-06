from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.utils.design import register_globals

templates = Jinja2Templates(directory="app/templates")
register_globals(templates)

router = APIRouter(tags=["pledge"])

PLEDGE_STATEMENTS = [
    {
        "id": 1,
        "text": "I will submit only first-hand reproducibility experiences I personally witnessed or directly supervised in the laboratory.",
        "icon": "flask",
    },
    {
        "id": 2,
        "text": "I will not submit fake, commercially motivated, or malicious reviews intended to unfairly discredit authors.",
        "icon": "shield",
    },
    {
        "id": 3,
        "text": "I will act respectfully and in good faith toward authors and other members of the ChemRepro community.",
        "icon": "handshake",
    },
    {
        "id": 4,
        "text": "I will comply with all applicable laws and regulations, including data protection rules (GDPR / Swiss DSG).",
        "icon": "law",
    },
    {
        "id": 5,
        "text": "I have read and agree to ChemRepro's Privacy Policy and Terms of Service.",
        "icon": "doc",
    },
]


@router.get("/pledge")
async def pledge_page(request: Request, next: str = "/"):
    orcid_id = request.session.get("orcid_id")
    if not orcid_id:
        return RedirectResponse(f"/auth/login?next=/pledge", status_code=303)
    return templates.TemplateResponse("pledge.html", {
        "request": request,
        "orcid_id": orcid_id,
        "user_name": request.session.get("user_name"),
        "next_url": next,
        "statements": PLEDGE_STATEMENTS,
        "total": len(PLEDGE_STATEMENTS),
    })


@router.post("/pledge/accept")
async def accept_pledge(
    request: Request,
    next_url: str = Form(default="/"),
    db: Session = Depends(get_db),
):
    orcid_id = request.session.get("orcid_id")
    if not orcid_id:
        return RedirectResponse("/auth/login", status_code=303)

    user = db.get(User, orcid_id)
    if user:
        user.pledge_accepted = True
        db.commit()

    return RedirectResponse(next_url or "/", status_code=303)
