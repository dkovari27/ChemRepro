"""Disk storage and validation for private library uploads."""
import io
import re
import time
import uuid
from pathlib import Path

from PIL import Image, UnidentifiedImageError
from PIL.Image import DecompressionBombError

from app.config import settings

QUOTA_BYTES = 20 * 1024 * 1024        # per user, across all papers
MAX_FILE_BYTES = 20 * 1024 * 1024     # per upload
MAX_FILES_PER_ENTRY = 20
ORPHAN_GRACE_SECONDS = 3600           # leave files this young alone (upload may be in flight)

# detected MIME -> (kind, extension, Pillow format or None)
_TYPES = {
    "application/pdf": ("pdf", ".pdf", None),
    "image/png": ("image", ".png", "PNG"),
    "image/jpeg": ("image", ".jpg", "JPEG"),
}
_STORED_NAME = re.compile(r"[0-9a-f]{32}\.(pdf|png|jpg)")


class UploadRejected(Exception):
    def __init__(self, message: str, status: int = 415):
        super().__init__(message)
        self.message = message
        self.status = status


def storage_dir() -> Path:
    p = Path(settings.LIBRARY_DIR)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _sniff(data: bytes) -> str | None:
    """Detect the type from content; the client's Content-Type is ignored."""
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    return None


def validate_upload(data: bytes) -> tuple[str, str, str]:
    """Return (mime, kind, extension) or raise UploadRejected."""
    if not data:
        raise UploadRejected("The file is empty.")
    mime = _sniff(data)
    if mime is None:
        raise UploadRejected("Only PDF, PNG and JPG files can be uploaded.")
    kind, ext, pil_format = _TYPES[mime]
    if pil_format:
        try:
            with Image.open(io.BytesIO(data)) as img:
                img.verify()
            with Image.open(io.BytesIO(data)) as img:
                if img.format != pil_format:
                    raise UploadRejected("File content does not match its type.")
        except DecompressionBombError:
            raise UploadRejected("Image dimensions are too large.")
        except (UnidentifiedImageError, OSError, ValueError):
            raise UploadRejected("That file is not a valid image.")
    return mime, kind, ext


def clean_display_name(name: str | None, ext: str) -> str:
    base = (name or "").replace("\\", "/").split("/")[-1]
    base = re.sub(r"[\x00-\x1f\x7f\"<>|?*:]", "", base).strip(". ")
    stem = Path(base).stem[:120] if base else ""
    return (stem or "file") + ext


def save_bytes(data: bytes, ext: str) -> str:
    """Write to disk under a random name and return that stored name."""
    stored = f"{uuid.uuid4().hex}{ext}"
    (storage_dir() / stored).write_bytes(data)
    return stored


def path_for(stored_name: str) -> Path:
    # stored_name comes from our own DB, but never let it escape the folder.
    return storage_dir() / Path(stored_name).name


def delete_stored(stored_name: str) -> None:
    try:
        path_for(stored_name).unlink(missing_ok=True)
    except OSError:
        pass


def remove_orphans(known_names: set[str]) -> int:
    """Delete stored files that no LibraryFile row points to (e.g. left behind
    when the app stopped between a DB commit and the file delete).
    Only names that save_bytes() creates are touched, so a misconfigured
    LIBRARY_DIR can never lose unrelated files. Returns how many were removed."""
    cutoff = time.time() - ORPHAN_GRACE_SECONDS
    removed = 0
    for p in storage_dir().iterdir():
        try:
            if (_STORED_NAME.fullmatch(p.name) and p.is_file()
                    and p.name not in known_names and p.stat().st_mtime < cutoff):
                p.unlink()
                removed += 1
        except OSError:
            pass
    return removed
