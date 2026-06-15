from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user_follow import UserFollow

router = APIRouter(prefix="/follow", tags=["follows"])


@router.post("/toggle/{target_orcid_id}")
async def toggle_follow(
    target_orcid_id: str, request: Request, db: Session = Depends(get_db)
):
    orcid_id = request.session.get("orcid_id")
    if not orcid_id or orcid_id == target_orcid_id:
        return JSONResponse({"following": False})

    existing = (
        db.query(UserFollow)
        .filter(
            UserFollow.follower_orcid_id == orcid_id,
            UserFollow.followed_orcid_id == target_orcid_id,
        )
        .first()
    )

    if existing:
        db.delete(existing)
        db.commit()
        return JSONResponse({"following": False})

    try:
        db.add(
            UserFollow(
                follower_orcid_id=orcid_id, followed_orcid_id=target_orcid_id
            )
        )
        db.commit()
        return JSONResponse({"following": True})
    except IntegrityError:
        db.rollback()
        return JSONResponse({"following": True})


@router.get("/status/{target_orcid_id}")
async def follow_status(
    target_orcid_id: str, request: Request, db: Session = Depends(get_db)
):
    orcid_id = request.session.get("orcid_id")
    if not orcid_id:
        return JSONResponse({"following": False})
    existing = (
        db.query(UserFollow)
        .filter(
            UserFollow.follower_orcid_id == orcid_id,
            UserFollow.followed_orcid_id == target_orcid_id,
        )
        .first()
    )
    return JSONResponse({"following": bool(existing)})
