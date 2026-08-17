import io

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from fastapi.responses import Response, JSONResponse
from PIL import Image, UnidentifiedImageError
from PIL.Image import DecompressionBombError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.image import UploadedImage

router = APIRouter(tags=["images"])

_ALLOWED_MIME = {"image/png", "image/jpeg", "image/gif", "image/webp"}
_MAX_BYTES = 5 * 1024 * 1024  # 5 MB

# Pillow's format names, keyed by the MIME types we accept.
_MIME_TO_PIL_FORMAT = {
    "image/png": "PNG",
    "image/jpeg": "JPEG",
    "image/gif": "GIF",
    "image/webp": "WEBP",
}


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

    # Verify the bytes are actually a valid image of the claimed type, not just
    # a file with a spoofed Content-Type header (client-supplied and untrusted).
    # DecompressionBombError is raised separately from the other cases: it's
    # Pillow's own guard against a small file declaring huge pixel dimensions
    # (a "decompression bomb" — well under the 5MB byte cap but expensive to
    # decode), and it is NOT a subclass of OSError/ValueError so it needs its
    # own except clause or it escapes as an unhandled 500.
    try:
        with Image.open(io.BytesIO(data)) as img:
            img.verify()
        # verify() leaves the file unusable for anything else, so re-open to
        # confirm Pillow's own format detection matches the declared MIME type.
        with Image.open(io.BytesIO(data)) as img:
            actual_format = img.format
    except DecompressionBombError:
        return JSONResponse({"error": "image dimensions too large"}, status_code=415)
    except (UnidentifiedImageError, OSError, ValueError):
        return JSONResponse({"error": "file is not a valid image"}, status_code=415)

    if actual_format != _MIME_TO_PIL_FORMAT.get(mime):
        return JSONResponse({"error": "file content does not match declared type"}, status_code=415)

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
        headers={
            "Cache-Control": "public, max-age=31536000, immutable",
            "X-Content-Type-Options": "nosniff",
        },
    )
