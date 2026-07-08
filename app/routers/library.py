"""
My Library: save papers to named collections, add private notes, export BibTeX/RIS.
Saving a paper also creates/removes the PaperSubscription (alerts).
"""
import json
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.collection import Collection
from app.models.paper_subscription import PaperSubscription
from app.models.saved_paper import SavedPaper
from app.utils.design import register_globals, render_md

templates = Jinja2Templates(directory="app/templates")
register_globals(templates)

router = APIRouter()

MAX_DEPTH = 5  # max nesting levels (0 = root, 4 = deepest allowed child)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _require_login(request: Request):
    return request.session.get("orcid_id")


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


def _to_bibtex(sp: SavedPaper) -> str:
    p = sp.paper
    authors = _authors_list(p.authors)
    key = _bibtex_key(authors, p.year, p.doi)
    author_str = " and ".join(authors)
    lines = [
        f"@article{{{key},",
        f"  author  = {{{author_str}}},",
        f"  title   = {{{p.title}}},",
    ]
    if p.journal:
        lines.append(f"  journal = {{{p.journal}}},")
    if p.year:
        lines.append(f"  year    = {{{p.year}}},")
    lines.append(f"  doi     = {{{p.doi}}},")
    lines.append("}")
    return "\n".join(lines)


def _to_ris(sp: SavedPaper) -> str:
    p = sp.paper
    authors = _authors_list(p.authors)
    lines = ["TY  - JOUR"]
    for a in authors:
        lines.append(f"AU  - {a}")
    lines.append(f"TI  - {p.title}")
    if p.journal:
        lines.append(f"JO  - {p.journal}")
    if p.year:
        lines.append(f"PY  - {p.year}")
    lines.append(f"DO  - {p.doi}")
    if sp.notes:
        lines.append(f"N1  - {sp.notes.replace(chr(10), ' ')}")
    lines.append("ER  - ")
    return "\n".join(lines)


# ── Library page ──────────────────────────────────────────────────────────────

@router.get("/library")
async def library_page(
    request: Request,
    collection: int | None = None,
    db: Session = Depends(get_db),
):
    orcid_id = _require_login(request)
    if not orcid_id:
        return RedirectResponse(f"/auth/login?next=/library", status_code=303)

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

    return templates.TemplateResponse("library.html", {
        "request": request,
        "orcid_id": orcid_id,
        "user_name": request.session.get("user_name"),
        "cols_flat": cols_flat,
        "saved_papers": saved_papers,
        "active_col": active_col,
        "active_col_id": collection,
        "total_saved": db.query(SavedPaper).filter(SavedPaper.orcid_id == orcid_id).count(),
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

    col_id = int(collection_id) if collection_id.strip() else None

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

    if existing:
        existing.collection_id = col_id
        existing.notes = notes.strip() or None
    else:
        db.add(SavedPaper(orcid_id=orcid_id, doi=doi, collection_id=col_id, notes=notes.strip() or None))

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
        db.delete(existing)
        _sync_subscription(orcid_id, doi, saved=False, db=db)
        db.commit()

    return JSONResponse({"saved": False})


# ── Notes update (AJAX) ───────────────────────────────────────────────────────

@router.post("/library/entry/{entry_id}/notes")
async def update_notes(
    entry_id: int,
    request: Request,
    notes: str = Form(""),
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

    sp.notes = notes.strip() or None
    db.commit()
    return JSONResponse({"ok": True, "rendered_html": render_md(sp.notes) if sp.notes else ""})


# ── Move to collection (AJAX) ─────────────────────────────────────────────────

@router.post("/library/entry/{entry_id}/move")
async def move_entry(
    entry_id: int,
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

    col_id = int(collection_id) if collection_id.strip() else None
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

    pid = int(parent_id) if parent_id.strip() else None
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

    pid = int(parent_id) if parent_id.strip() else None

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
    col_id: int,
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
    col_id: int,
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
    filename = f"chemrepro-{scope}.bib"
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
    filename = f"chemrepro-{scope}.ris"
    return PlainTextResponse(
        body,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        media_type="application/x-research-info-systems",
    )


def _get_export_entries(scope: str, orcid_id: str, db: Session) -> list[SavedPaper]:
    q = db.query(SavedPaper).filter(SavedPaper.orcid_id == orcid_id)
    if scope != "all":
        try:
            col_id = int(scope)
            q = q.filter(SavedPaper.collection_id == col_id)
        except ValueError:
            pass
    return q.all()
