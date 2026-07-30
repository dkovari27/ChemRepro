"""
/api/v1/* — structured JSON endpoints for authorized external consumers and AI tools.
All routes require a valid X-API-Key header. Request access via chemrepro@gmail.com.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.api_key import ApiKey
from app.models.paper import Paper
from app.models.rating import Rating
from app.schemas.paper import PaperWithScores
from app.schemas.rating import RatingOut, AggregatedScores
from app.services.crossref import fetch_paper_metadata, is_valid_doi, normalise_doi

router = APIRouter(prefix="/api/v1", tags=["API v1"])

# Outcome → numeric score (1–5) for standard-mode ratings
_OUTCOME_SCORE = case(
    (Rating.outcome == "no_repro", 1),
    (Rating.outcome == "no_extension", 2),
    (Rating.outcome == "reproduced", 3),
    (Rating.outcome == "repro_extension_failed", 4),
    (Rating.outcome == "extended", 5),
    else_=None,
)


def _check_api_key(request: Request, db: Session) -> ApiKey:
    raw_key = request.headers.get("X-API-Key")
    if not raw_key:
        raise HTTPException(
            status_code=401,
            detail="API key required. Add an X-API-Key header. Request access: chemrepro@gmail.com",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    key_hash = ApiKey.hash_key(raw_key)
    key = db.query(ApiKey).filter(ApiKey.key_hash == key_hash, ApiKey.is_active == True).first()  # noqa: E712
    if not key:
        raise HTTPException(status_code=403, detail="Invalid or inactive API key")
    key.last_used = datetime.utcnow()
    db.commit()
    return key


@router.get("/papers", response_model=list[PaperWithScores])
async def list_papers(request: Request, limit: int = 20, offset: int = 0, db: Session = Depends(get_db)):
    """Return recently added papers with aggregated scores."""
    _check_api_key(request, db)
    papers = db.query(Paper).order_by(Paper.fetched_at.desc()).offset(offset).limit(min(limit, 100)).all()
    result = []
    for p in papers:
        row = db.query(
            func.avg(_OUTCOME_SCORE),
            func.count(Rating.id),
        ).filter(Rating.doi == p.doi, Rating.scoring_mode != "classic").one()
        result.append(PaperWithScores(
            doi=p.doi,
            title=p.title,
            authors=p.authors,
            journal=p.journal,
            year=p.year,
            fetched_at=p.fetched_at,
            avg_reproducibility=round(float(row[0]), 2) if row[0] else None,
            avg_generalisability=None,
            rating_count=row[1],
        ))
    return result


@router.get("/papers/{doi:path}", response_model=PaperWithScores)
async def get_paper(doi: str, request: Request, db: Session = Depends(get_db)):
    """
    Fetch a paper by DOI. If not in DB, queries CrossRef and caches it.
    DOI can be bare (10.1000/xyz123) or URL-encoded.
    """
    _check_api_key(request, db)
    doi = normalise_doi(doi)
    if not is_valid_doi(doi):
        raise HTTPException(status_code=422, detail="Invalid DOI format")

    paper = db.get(Paper, doi)
    if not paper:
        meta = await fetch_paper_metadata(doi)
        if not meta:
            raise HTTPException(status_code=404, detail="Paper not found in CrossRef")
        paper = Paper(**meta)
        db.add(paper)
        db.commit()
        db.refresh(paper)

    row = db.query(
        func.avg(_OUTCOME_SCORE),
        func.count(Rating.id),
    ).filter(Rating.doi == doi, Rating.scoring_mode != "classic").one()

    return PaperWithScores(
        doi=paper.doi,
        title=paper.title,
        authors=paper.authors,
        journal=paper.journal,
        year=paper.year,
        fetched_at=paper.fetched_at,
        avg_reproducibility=round(float(row[0]), 2) if row[0] else None,
        avg_generalisability=None,
        rating_count=row[1],
    )


@router.get("/papers/{doi:path}/ratings", response_model=list[RatingOut])
async def get_paper_ratings(doi: str, request: Request, db: Session = Depends(get_db)):
    """Return all individual ratings for a paper. Reviewer ORCID iDs are NOT included."""
    _check_api_key(request, db)
    doi = normalise_doi(doi)
    paper = db.get(Paper, doi)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    ratings = db.query(Rating).filter(
        Rating.doi == doi,
        Rating.ai_flagged == False,  # noqa: E712
        Rating.pending_admin_review == False,  # noqa: E712
    ).order_by(Rating.created_at.desc()).all()
    return ratings


@router.get("/papers/{doi:path}/scores", response_model=AggregatedScores)
async def get_paper_scores(doi: str, request: Request, db: Session = Depends(get_db)):
    """Aggregated scores for a paper."""
    _check_api_key(request, db)
    doi = normalise_doi(doi)
    paper = db.get(Paper, doi)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    row = db.query(
        func.avg(_OUTCOME_SCORE),
        func.count(Rating.id),
    ).filter(Rating.doi == doi, Rating.scoring_mode != "classic").one()

    return AggregatedScores(
        doi=doi,
        rating_count=row[1],
        avg_reproducibility=round(float(row[0]), 2) if row[0] else None,
        avg_generalisability=None,
    )
