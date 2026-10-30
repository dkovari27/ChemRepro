"""
My Library: save papers to named collections, add private notes, export BibTeX/RIS.
Saving a paper also creates/removes the PaperSubscription (alerts).
"""
import json
import re
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Path, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.collection import Collection
from app.models.library_item import LibraryFile, LibraryNote
from app.models.paper import Paper
from app.models.paper_subscription import PaperSubscription
from app.models.saved_paper import SavedPaper
from app.models.user import User
from app.services import library_storage as storage
from app.utils.design import register_globals, render_md

templates = Jinja2Templates(directory="app/templates")
register_globals(templates)

router = APIRouter()

MAX_DEPTH = 5  # max nesting levels (0 = root, 4 = deepest allowed child)

_DB_INT_MAX = 2_147_483_647  # PostgreSQL INTEGER; larger ids make the query fail
DbId = Annotated[int, Path(ge=1, le=_DB_INT_MAX)]


# ── Helpers ──────────────────────────────────────────────────────────────────

def _require_login(request: Request):
    return request.session.get("orcid_id")


def _parse_id(value: str | None) -> int | None:
    """Positive database id from form or URL text; None if blank, not a number or out of range."""
    try:
        n = int((value or "").strip())
    except ValueError:
        return None
    return n if 0 < n <= _DB_INT_MAX else None


def _mb(n_bytes: int) -> int:
    return n_bytes // (1024 * 1024)


NOTE_MAX_CHARS = 20000


def _own_entry(entry_id: int, orcid_id: str, db: Session) -> SavedPaper | None:
    return db.query(SavedPaper).filter(
        SavedPaper.id == entry_id, SavedPaper.orcid_id == orcid_id
    ).first()


def _used_bytes(orcid_id: str, db: Session) -> int:
    return db.query(func.coalesce(func.sum(LibraryFile.size_bytes), 0)).filter(
        LibraryFile.orcid_id == orcid_id
    ).scalar() or 0


def _file_json(f: LibraryFile) -> dict:
    return {
        "uuid": f.uuid, "kind": f.kind, "name": f.original_name,
        "size": f.size_bytes, "url": f"/library/file/{f.uuid}",
    }


def _collection_depth(col: Collection) -> int:
    """Count ancestors (root = 0)."""
    depth = 0
    c = col
    while c.parent_id is not None:
        c = c.parent
        depth += 1
        if depth >= MAX_DEPTH:
            break
    return depth


def _collections_flat(orcid_id: str, db: Session) -> list[tuple[Collection, int]]:
    """All user collections as (collection, depth) in tree order, alphabetical within level."""
    all_cols = db.query(Collection).filter(Collection.orcid_id == orcid_id).all()
    by_parent: dict[int | None, list[Collection]] = {}
    for c in all_cols:
        by_parent.setdefault(c.parent_id, []).append(c)

    result: list[tuple[Collection, int]] = []

    def walk(parent_id: int | None, depth: int):
        for c in sorted(by_parent.get(parent_id, []), key=lambda x: x.name.lower()):
            result.append((c, depth))
            walk(c.id, depth + 1)

    walk(None, 0)
    return result


def delete_entries(db: Session, *conditions) -> list[str]:
    """Delete the SavedPaper rows matching `conditions` through the ORM, so their
    notes and file rows go with them. Returns the stored file names; the caller
    removes them with storage.delete_stored() after committing."""
    stored_names = []
    for sp in db.query(SavedPaper).filter(*conditions).all():
        stored_names += [f.stored_name for f in sp.library_files]
        db.delete(sp)
    db.flush()
    return stored_names


def _sync_subscription(orcid_id: str, doi: str, saved: bool, db: Session):
    """Keep PaperSubscription in sync with saved state."""
    existing = db.query(PaperSubscription).filter(
        PaperSubscription.orcid_id == orcid_id,
        PaperSubscription.doi == doi,
    ).first()
    if saved and not existing:
        db.add(PaperSubscription(orcid_id=orcid_id, doi=doi))
    elif not saved and existing:
        db.delete(existing)


def _authors_list(authors_json: str) -> list[str]:
    try:
        return json.loads(authors_json)
    except Exception:
        return [authors_json]


def _bibtex_key(authors: list[str], year: int | None, doi: str) -> str:
    first = re.sub(r"[^a-zA-Z]", "", (authors[0].split()[-1] if authors else "Unknown"))
    y = str(year) if year else "XXXX"
    suffix = re.sub(r"[^a-zA-Z0-9]", "", doi)[-6:]
    return f"{first}{y}{suffix}"


def _one_line(s) -> str:
    return " ".join(str(s or "").split())


def _bib(s) -> str:
    """One line, with backslashes and braces escaped so a field can't close early."""
    return _one_line(s).replace("\\", "\\textbackslash ").replace("{", "\\{").replace("}", "\\}")


def _to_bibtex(sp: SavedPaper) -> str:
    p = sp.paper
    authors = _authors_list(p.authors)
    key = _bibtex_key(authors, p.year, p.doi)
    author_str = " and ".join(_bib(a) for a in authors)
    lines = [
        f"@article{{{key},",
        f"  author  = {{{author_str}}},",
        f"  title   = {{{_bib(p.title)}}},",
    ]
    if p.journal:
        lines.append(f"  journal = {{{_bib(p.journal)}}},")
    if p.year:
        lines.append(f"  year    = {{{p.year}}},")
    lines.append(f"  doi     = {{{_bib(p.doi)}}},")
    lines.append("}")
    return "\n".join(lines)


def _to_ris(sp: SavedPaper) -> str:
    p = sp.paper
    authors = _authors_list(p.authors)
    lines = ["TY  - JOUR"]
    for a in authors:
        lines.append(f"AU  - {_one_line(a)}")
    lines.append(f"TI  - {_one_line(p.title)}")
    if p.journal:
        lines.append(f"JO  - {_one_line(p.journal)}")
    if p.year:
        lines.append(f"PY  - {p.year}")
    lines.append(f"DO  - {_one_line(p.doi)}")
    for n in sp.library_notes:
        lines.append(f"N1  - {_one_line(n.body)}")
    lines.append("ER  - ")
    return "\n".join(lines)


# ── Library page ──────────────────────────────────────────────────────────────

@router.get("/library")
async def library_page(
    request: Request,
    collection: str | None = None,
    db: Session = Depends(get_db),
):
    orcid_id = _require_login(request)
    if not orcid_id:
        return RedirectResponse(f"/auth/login?next=/library", status_code=303)

    raw_collection = collection
    collection = 0 if (raw_collection or "").strip() == "0" else _parse_id(raw_collection)
    if raw_collection and collection is None:
        return RedirectResponse("/library", status_code=303)

    cols_flat = _collections_flat(orcid_id, db)

    # Papers query
    q = db.query(SavedPaper).filter(SavedPaper.orcid_id == orcid_id)
    active_col = None
    if collection == 0:
        q = q.filter(SavedPaper.collection_id.is_(None))
        active_col = "unsorted"
    elif collection:
        active_col = db.query(Collection).filter(
            Collection.id == collection,
            Collection.orcid_id == orcid_id,
        ).first()
        if not active_col:
            return RedirectResponse("/library", status_code=303)
        q = q.filter(SavedPaper.collection_id == collection)

    saved_papers = q.order_by(SavedPaper.created_at.desc()).all()

    extras = {
        sp.id: {
            "notes": [{"id": n.id, "body": n.body, "html": render_md(n.body)} for n in sp.library_notes],
            "files": [_file_json(f) for f in sp.library_files],
        }
        for sp in saved_papers
    }

    return templates.TemplateResponse("library.html", {
        "extras": extras,
        "request": request,
        "orcid_id": orcid_id,
        "user_name": request.session.get("user_name"),
        "cols_flat": cols_flat,
        "saved_papers": saved_papers,
        "active_col": active_col,
        "active_col_id": collection,
        "total_saved": db.query(SavedPaper).filter(SavedPaper.orcid_id == orcid_id).count(),
        "used_bytes": _used_bytes(orcid_id, db),
        "quota_bytes": storage.QUOTA_BYTES,
        "max_file_bytes": storage.MAX_FILE_BYTES,
    })


# ── Save / unsave ─────────────────────────────────────────────────────────────

@router.post("/library/save")
async def save_paper(
    request: Request,
    doi: str = Form(...),
    collection_id: str = Form(""),
    notes: str = Form(""),
    db: Session = Depends(get_db),
):
    orcid_id = _require_login(request)
    if not orcid_id:
        return JSONResponse({"error": "not authenticated"}, status_code=401)

    doi = doi.strip()
    if not db.get(Paper, doi):
        return JSONResponse({"error": "paper not found"}, status_code=404)

    col_id = _parse_id(collection_id)

    # Validate collection belongs to this user
    if col_id:
        col = db.query(Collection).filter(
            Collection.id == col_id, Collection.orcid_id == orcid_id
        ).first()
        if not col:
            col_id = None

    existing = db.query(SavedPaper).filter(
        SavedPaper.orcid_id == orcid_id,
        SavedPaper.doi == doi,
    ).first()

    note_text = notes.strip()[:NOTE_MAX_CHARS]
    if existing:
        existing.collection_id = col_id
        entry = existing
    else:
        entry = SavedPaper(orcid_id=orcid_id, doi=doi, collection_id=col_id)
        db.add(entry)
        db.flush()
    # The paper-page Save box shows and edits the first note; more notes live in
    # the library. Clearing the box deletes that first note.
    first = entry.library_notes[0] if entry.library_notes else None
    if note_text:
        if first:
            if first.body != note_text:
                first.body = note_text
                first.updated_at = datetime.now(timezone.utc)
        else:
            db.add(LibraryNote(saved_paper_id=entry.id, orcid_id=orcid_id, body=note_text))
    elif first:
        db.delete(first)

    _sync_subscription(orcid_id, doi, saved=True, db=db)
    db.commit()

    col_name = None
    if col_id:
        c = db.query(Collection).filter(Collection.id == col_id).first()
        col_name = c.name if c else None

    return JSONResponse({"saved": True, "collection_name": col_name})


@router.post("/library/unsave")
async def unsave_paper(
    request: Request,
    doi: str = Form(...),
    db: Session = Depends(get_db),
):
    orcid_id = _require_login(request)
    if not orcid_id:
        return JSONResponse({"error": "not authenticated"}, status_code=401)

    existing = db.query(SavedPaper).filter(
        SavedPaper.orcid_id == orcid_id,
        SavedPaper.doi == doi,
    ).first()
    if existing:
        stored_names = [f.stored_name for f in existing.library_files]
        db.delete(existing)
        _sync_subscription(orcid_id, doi, saved=False, db=db)
        db.commit()
        for name in stored_names:
            storage.delete_stored(name)

    return JSONResponse({"saved": False, "used_bytes": _used_bytes(orcid_id, db)})


# ── Notes (many per paper) ────────────────────────────────────────────────────

def _note_json(n: LibraryNote) -> dict:
    return {"id": n.id, "body": n.body, "html": render_md(n.body)}


@router.post("/library/entry/{entry_id}/note")
async def add_note(
    entry_id: DbId,
    request: Request,
    body: str = Form(""),
    db: Session = Depends(get_db),
):
    orcid_id = _require_login(request)
    if not orcid_id:
        return JSONResponse({"error": "not authenticated"}, status_code=401)
    if not _own_entry(entry_id, orcid_id, db):
        return JSONResponse({"error": "not found"}, status_code=404)
    body = body.strip()
    if not body:
        return JSONResponse({"error": "note is empty"}, status_code=422)
    if len(body) > NOTE_MAX_CHARS:
        return JSONResponse({"error": f"note too long (max {NOTE_MAX_CHARS} characters)"}, status_code=413)
    note = LibraryNote(saved_paper_id=entry_id, orcid_id=orcid_id, body=body)
    db.add(note)
    db.commit()
    db.refresh(note)
    return JSONResponse(_note_json(note))


@router.post("/library/note/{note_id}/edit")
async def edit_note(
    note_id: DbId,
    request: Request,
    body: str = Form(""),
    db: Session = Depends(get_db),
):
    orcid_id = _require_login(request)
    if not orcid_id:
        return JSONResponse({"error": "not authenticated"}, status_code=401)
    note = db.query(LibraryNote).filter(
        LibraryNote.id == note_id, LibraryNote.orcid_id == orcid_id
    ).first()
    if not note:
        return JSONResponse({"error": "not found"}, status_code=404)
    body = body.strip()
    if not body:
        return JSONResponse({"error": "note is empty"}, status_code=422)
    if len(body) > NOTE_MAX_CHARS:
        return JSONResponse({"error": f"note too long (max {NOTE_MAX_CHARS} characters)"}, status_code=413)
    note.body = body
    note.updated_at = datetime.now(timezone.utc)
    db.commit()
    return JSONResponse(_note_json(note))


@router.post("/library/note/{note_id}/delete")
async def delete_note(
    note_id: DbId,
    request: Request,
    db: Session = Depends(get_db),
):
    orcid_id = _require_login(request)
    if not orcid_id:
        return JSONResponse({"error": "not authenticated"}, status_code=401)
    note = db.query(LibraryNote).filter(
        LibraryNote.id == note_id, LibraryNote.orcid_id == orcid_id
    ).first()
    if not note:
        return JSONResponse({"error": "not found"}, status_code=404)
    db.delete(note)
    db.commit()
    return JSONResponse({"ok": True})


# ── Files: PDFs and screenshots (private, owner-only) ─────────────────────────

@router.post("/library/entry/{entry_id}/files")
async def upload_file(
    entry_id: DbId,
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    orcid_id = _require_login(request)
    if not orcid_id:
        return JSONResponse({"error": "not authenticated"}, status_code=401)
    entry = _own_entry(entry_id, orcid_id, db)
    if not entry:
        return JSONResponse({"error": "not found"}, status_code=404)
    if len(entry.library_files) >= storage.MAX_FILES_PER_ENTRY:
        return JSONResponse(
            {"error": f"Up to {storage.MAX_FILES_PER_ENTRY} files per paper."}, status_code=413
        )

    too_big = {"error": f"Files can be at most {_mb(storage.MAX_FILE_BYTES)} MB."}
    no_space = {"error": f"Not enough library space left ({_mb(storage.QUOTA_BYTES)} MB per account). Delete a file first."}
    remaining = storage.QUOTA_BYTES - _used_bytes(orcid_id, db)
    buf = bytearray()
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        buf += chunk
        if len(buf) > storage.MAX_FILE_BYTES:
            return JSONResponse(too_big, status_code=413)
        if len(buf) > remaining:
            return JSONResponse(no_space, status_code=413)
    data = bytes(buf)

    try:
        mime, kind, ext = storage.validate_upload(data)
    except storage.UploadRejected as exc:
        return JSONResponse({"error": exc.message}, status_code=exc.status)

    # Lock the user's row so two parallel uploads can't both pass the quota
    # check (PostgreSQL; SQLite ignores FOR UPDATE but serialises writes).
    db.query(User).filter(User.orcid_id == orcid_id).with_for_update().first()
    if _used_bytes(orcid_id, db) + len(data) > storage.QUOTA_BYTES:
        db.rollback()
        return JSONResponse(no_space, status_code=413)
    if db.query(LibraryFile).filter(LibraryFile.saved_paper_id == entry_id).count() >= storage.MAX_FILES_PER_ENTRY:
        db.rollback()
        return JSONResponse(
            {"error": f"Up to {storage.MAX_FILES_PER_ENTRY} files per paper."}, status_code=413
        )

    stored = storage.save_bytes(data, ext)
    rec = LibraryFile(
        saved_paper_id=entry_id, orcid_id=orcid_id, kind=kind, mime_type=mime,
        original_name=storage.clean_display_name(file.filename, ext),
        stored_name=stored, size_bytes=len(data),
    )
    try:
        db.add(rec)
        db.commit()
    except Exception:
        db.rollback()
        storage.delete_stored(stored)
        raise
    db.refresh(rec)
    return JSONResponse({"file": _file_json(rec), "used_bytes": _used_bytes(orcid_id, db)})


@router.get("/library/file/{file_uuid}")
async def get_file(file_uuid: str, request: Request, db: Session = Depends(get_db)):
    orcid_id = _require_login(request)
    if not orcid_id:
        return JSONResponse({"error": "not authenticated"}, status_code=401)
    rec = db.query(LibraryFile).filter(
        LibraryFile.uuid == file_uuid, LibraryFile.orcid_id == orcid_id
    ).first()
    path = storage.path_for(rec.stored_name) if rec else None
    if not rec or not path.is_file():
        return JSONResponse({"error": "not found"}, status_code=404)
    safe_name = rec.original_name.encode("ascii", "ignore").decode() or "file"
    return FileResponse(
        path, media_type=rec.mime_type,
        headers={
            "Content-Disposition": f'inline; filename="{safe_name}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, max-age=0, must-revalidate",
        },
    )


@router.post("/library/file/{file_uuid}/delete")
async def delete_file(file_uuid: str, request: Request, db: Session = Depends(get_db)):
    orcid_id = _require_login(request)
    if not orcid_id:
        return JSONResponse({"error": "not authenticated"}, status_code=401)
    rec = db.query(LibraryFile).filter(
        LibraryFile.uuid == file_uuid, LibraryFile.orcid_id == orcid_id
    ).first()
    if not rec:
        return JSONResponse({"error": "not found"}, status_code=404)
    stored = rec.stored_name
    db.delete(rec)
    db.commit()
    storage.delete_stored(stored)
    return JSONResponse({"ok": True, "used_bytes": _used_bytes(orcid_id, db)})


# ── Move to collection (AJAX) ─────────────────────────────────────────────────

@router.post("/library/entry/{entry_id}/move")
async def move_entry(
    entry_id: DbId,
    request: Request,
    collection_id: str = Form(""),
    db: Session = Depends(get_db),
):
    orcid_id = _require_login(request)
    if not orcid_id:
        return JSONResponse({"error": "not authenticated"}, status_code=401)

    sp = db.query(SavedPaper).filter(
        SavedPaper.id == entry_id, SavedPaper.orcid_id == orcid_id
    ).first()
    if not sp:
        return JSONResponse({"error": "not found"}, status_code=404)

    col_id = _parse_id(collection_id)
    if col_id:
        col = db.query(Collection).filter(
            Collection.id == col_id, Collection.orcid_id == orcid_id
        ).first()
        col_id = col.id if col else None

    sp.collection_id = col_id
    db.commit()
    return JSONResponse({"ok": True})


# ── Collection management ─────────────────────────────────────────────────────

@router.post("/library/collections/new-json")
async def create_collection_json(
    request: Request,
    name: str = Form(...),
    parent_id: str = Form(""),
    db: Session = Depends(get_db),
):
    """AJAX variant — returns {id, name} instead of a redirect."""
    orcid_id = _require_login(request)
    if not orcid_id:
        return JSONResponse({"error": "not authenticated"}, status_code=401)

    name = name.strip()[:200]
    if not name:
        return JSONResponse({"error": "name required"}, status_code=422)

    pid = _parse_id(parent_id)
    if pid:
        parent = db.query(Collection).filter(
            Collection.id == pid, Collection.orcid_id == orcid_id
        ).first()
        if not parent or _collection_depth(parent) >= MAX_DEPTH - 1:
            pid = None

    col = Collection(orcid_id=orcid_id, name=name, parent_id=pid)
    db.add(col)
    db.commit()
    db.refresh(col)
    return JSONResponse({"id": col.id, "name": col.name})


@router.post("/library/collections/new")
async def create_collection(
    request: Request,
    name: str = Form(...),
    parent_id: str = Form(""),
    db: Session = Depends(get_db),
):
    orcid_id = _require_login(request)
    if not orcid_id:
        return RedirectResponse("/auth/login?next=/library", status_code=303)

    name = name.strip()[:200]
    if not name:
        return RedirectResponse("/library", status_code=303)

    pid = _parse_id(parent_id)

    # Validate parent + check depth
    if pid:
        parent = db.query(Collection).filter(
            Collection.id == pid, Collection.orcid_id == orcid_id
        ).first()
        if not parent:
            pid = None
        elif _collection_depth(parent) >= MAX_DEPTH - 1:
            # Already at max depth — silently make it a root collection
            pid = None

    db.add(Collection(orcid_id=orcid_id, name=name, parent_id=pid))
    db.commit()

    return_to = f"/library?collection={pid}" if pid else "/library"
    return RedirectResponse(return_to, status_code=303)


@router.post("/library/collections/{col_id}/rename")
async def rename_collection(
    col_id: DbId,
    request: Request,
    name: str = Form(...),
    db: Session = Depends(get_db),
):
    orcid_id = _require_login(request)
    if not orcid_id:
        return JSONResponse({"error": "not authenticated"}, status_code=401)

    col = db.query(Collection).filter(
        Collection.id == col_id, Collection.orcid_id == orcid_id
    ).first()
    if not col:
        return JSONResponse({"error": "not found"}, status_code=404)

    col.name = name.strip()[:200] or col.name
    db.commit()
    return JSONResponse({"ok": True, "name": col.name})


@router.post("/library/collections/{col_id}/delete")
async def delete_collection(
    col_id: DbId,
    request: Request,
    db: Session = Depends(get_db),
):
    orcid_id = _require_login(request)
    if not orcid_id:
        return JSONResponse({"error": "not authenticated"}, status_code=401)

    col = db.query(Collection).filter(
        Collection.id == col_id, Collection.orcid_id == orcid_id
    ).first()
    if not col:
        return JSONResponse({"error": "not found"}, status_code=404)

    # Move all direct saved papers to unsorted
    db.query(SavedPaper).filter(SavedPaper.collection_id == col_id).update(
        {"collection_id": None}
    )
    # Move child collections to root level
    db.query(Collection).filter(Collection.parent_id == col_id).update(
        {"parent_id": col.parent_id}
    )
    db.delete(col)
    db.commit()
    return JSONResponse({"ok": True})


# ── Export ────────────────────────────────────────────────────────────────────

@router.get("/library/export/{scope}.bib")
async def export_bib(
    scope: str,
    request: Request,
    db: Session = Depends(get_db),
):
    orcid_id = _require_login(request)
    if not orcid_id:
        return JSONResponse({"error": "not authenticated"}, status_code=401)

    entries = _get_export_entries(scope, orcid_id, db)
    body = "\n\n".join(_to_bibtex(sp) for sp in entries)
    filename = f"chemrepro-{_export_label(scope)}.bib"
    return PlainTextResponse(
        body,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        media_type="application/x-bibtex",
    )


@router.get("/library/export/{scope}.ris")
async def export_ris(
    scope: str,
    request: Request,
    db: Session = Depends(get_db),
):
    orcid_id = _require_login(request)
    if not orcid_id:
        return JSONResponse({"error": "not authenticated"}, status_code=401)

    entries = _get_export_entries(scope, orcid_id, db)
    body = "\n\n".join(_to_ris(sp) for sp in entries)
    filename = f"chemrepro-{_export_label(scope)}.ris"
    return PlainTextResponse(
        body,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        media_type="application/x-research-info-systems",
    )


def _export_label(scope: str) -> str:
    """'all', 'unsorted' or a collection id; never raw URL text in the download header."""
    if scope == "0":
        return "unsorted"
    col_id = _parse_id(scope)
    return str(col_id) if col_id else "all"


def _get_export_entries(scope: str, orcid_id: str, db: Session) -> list[SavedPaper]:
    q = db.query(SavedPaper).filter(SavedPaper.orcid_id == orcid_id)
    if scope == "0":
        return q.filter(SavedPaper.collection_id.is_(None)).all()
    col_id = _parse_id(scope)
    if col_id:
        q = q.filter(SavedPaper.collection_id == col_id)
    return q.all()
