from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from fastapi.responses import Response, JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.image import UploadedImage

router = APIRouter(tags=["images"])

_ALLOWED_MIME = {"image/png", "image/jpeg", "image/gif", "image/webp"}
_MAX_BYTES = 5 * 1024 * 1024  # 5 MB


@router.post("/upload/image")
async def upload_image(
    request: Request,
    db: Session = Depends(get_db),
    file: UploadFile = File(...),
):
    orcid_id = request.session.get("orcid_id")
    if not orcid_id:
        return JSONResponse({"error": "not authenticated"}, status_code=401)

    mime = file.content_type or ""
    if mime not in _ALLOWED_MIME:
        return JSONResponse({"error": "unsupported file type"}, status_code=415)

    data = await file.read()
    if len(data) > _MAX_BYTES:
        return JSONResponse({"error": "file too large (max 5 MB)"}, status_code=413)

    img = UploadedImage(
        uploader_orcid_id=orcid_id,
        mime_type=mime,
        data=data,
    )
    db.add(img)
    db.commit()
    db.refresh(img)
    return JSONResponse({"url": f"/images/{img.uuid}"})


@router.get("/images/{image_uuid}")
async def serve_image(image_uuid: str, db: Session = Depends(get_db)):
    img = db.query(UploadedImage).filter(UploadedImage.uuid == image_uuid).first()
    if not img:
        raise HTTPException(status_code=404)
    return Response(
        content=img.data,
        media_type=img.mime_type,
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )
