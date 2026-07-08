"""
/api/v1/* — clean JSON endpoints for external consumers and AI tools.
All routes are public (read). Write operations go through the HTML form flow.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.database import get_db
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


@router.get("/papers", response_model=list[PaperWithScores])
async def list_papers(limit: int = 20, offset: int = 0, db: Session = Depends(get_db)):
    """Return recently added papers with aggregated scores."""
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
async def get_paper(doi: str, db: Session = Depends(get_db)):
    """
    Fetch a paper by DOI. If not in DB, queries CrossRef and caches it.
    DOI can be bare (10.1000/xyz123) or URL-encoded.
    """
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
async def get_paper_ratings(doi: str, db: Session = Depends(get_db)):
    """Return all individual ratings for a paper. Reviewer ORCID iDs are NOT included."""
    doi = normalise_doi(doi)
    paper = db.get(Paper, doi)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    ratings = db.query(Rating).filter(Rating.doi == doi).order_by(Rating.created_at.desc()).all()
    return ratings


@router.get("/papers/{doi:path}/scores", response_model=AggregatedScores)
async def get_paper_scores(doi: str, db: Session = Depends(get_db)):
    """Aggregated scores for a paper."""
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
