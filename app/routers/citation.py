"""Citation text and downloadable citation files for a paper."""
import re

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.paper import Paper
from app.services import citation as cite
from app.services.crossref import is_valid_doi, normalise_doi

router = APIRouter()

_FORMATS = {
    "ris": (cite.to_ris, "application/x-research-info-systems", "ris"),
    "enw": (cite.to_endnote, "application/x-endnote-refer", "enw"),
    "bib": (cite.to_bibtex, "application/x-bibtex", "bib"),
}


async def _load(doi: str, db: Session) -> dict:
    doi = normalise_doi(doi)
    if not is_valid_doi(doi):
        raise HTTPException(status_code=422, detail="Invalid DOI")
    paper = db.get(Paper, doi)
    fallback = None
    if paper:
        fallback = {
            "title": paper.title,
            "authors": cite.authors_from_json(paper.authors),
            "journal": paper.journal,
            "year": paper.year,
        }
    data = await cite.get_citation_data(doi, fallback)
    if not data:
        raise HTTPException(status_code=404, detail="Citation data not found")
    return data


@router.get("/citation/json/{doi:path}")
async def citation_json(doi: str, db: Session = Depends(get_db)):
    data = await _load(doi, db)
    return JSONResponse({"text": cite.format_text(data), "doi": data["doi"]})


@router.get("/citation/{fmt}/{doi:path}")
async def citation_file(fmt: str, doi: str, db: Session = Depends(get_db)):
    if fmt not in _FORMATS:
        raise HTTPException(status_code=404, detail="Unknown format")
    data = await _load(doi, db)
    render, media_type, ext = _FORMATS[fmt]
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", data["doi"])
    return Response(
        render(data),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{safe}.{ext}"'},
    )
