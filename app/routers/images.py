import io

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from fastapi.responses import Response, JSONResponse
from PIL import Image, ImageOps, UnidentifiedImageError
from PIL.Image import DecompressionBombError
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.image import UploadedImage
from app.models.user import User

router = APIRouter(tags=["images"])

_ALLOWED_MIME = {"image/png", "image/jpeg", "image/gif", "image/webp"}
_MAX_BYTES = 5 * 1024 * 1024  # 5 MB
_USER_QUOTA_BYTES = 20 * 1024 * 1024  # all review/comment images of one user (stored in Postgres)
_MAX_SIDE = 1600  # px; larger images are scaled down on upload

# Pillow's format names, keyed by the MIME types we accept.
_MIME_TO_PIL_FORMAT = {
    "image/png": "PNG",
    "image/jpeg": "JPEG",
    "image/gif": "GIF",
    "image/webp": "WEBP",
}


def _shrink(data: bytes, mime: str) -> tuple[bytes, str]:
    """Scale the image down to _MAX_SIDE px and re-encode it as WebP, so a 5 MB
    screenshot is stored as a few hundred KB (images live in Postgres and count
    against the per-user total). Animated GIFs keep only their first frame.
    Keeps the original when re-encoding would not make it smaller."""
    with Image.open(io.BytesIO(data)) as img:
        img = ImageOps.exif_transpose(img)
        img.thumbnail((_MAX_SIDE, _MAX_SIDE))
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGBA" if "transparency" in img.info or img.mode in ("LA", "PA") else "RGB")
        out = io.BytesIO()
        img.save(out, "WEBP", quality=85, method=4)
    smaller = out.getvalue()
    return (smaller, "image/webp") if len(smaller) < len(data) else (data, mime)


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

    data = await file.read(_MAX_BYTES + 1)
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

    data, mime = _shrink(data, mime)

    # Per-user total, checked under a lock on the user's row so parallel
    # uploads can't both slip under it (PostgreSQL; SQLite serialises writes).
    db.query(User).filter(User.orcid_id == orcid_id).with_for_update().first()
    used = db.query(func.coalesce(func.sum(func.length(UploadedImage.data)), 0)).filter(
        UploadedImage.uploader_orcid_id == orcid_id
    ).scalar() or 0
    if used + len(data) > _USER_QUOTA_BYTES:
        db.rollback()
        return JSONResponse({"error": "image upload limit reached for this account"}, status_code=413)

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
