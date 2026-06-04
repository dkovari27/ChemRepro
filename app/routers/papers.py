import json

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.comment import Comment
from app.models.like import Like
from app.models.paper import Paper
from app.models.rating import Rating
from app.routers.auth import DEV_FAKE_USERS
from app.services.crossref import fetch_paper_metadata, is_valid_doi, normalise_doi

router = APIRouter(tags=["papers"])
templates = Jinja2Templates(directory="app/templates")

OUTCOME_SCORES = {
    "no_repro": 1,
    "no_extension": 2,
    "reproduced": 3,
    "repro_extension_failed": 4,
    "extended": 5,
}

OUTCOME_LABELS = {
    "no_repro":               "Did not work on original",
    "no_extension":           "Did not work on extension",
    "reproduced":             "Reproduced original",
    "repro_extension_failed": "Reproduced, extension failed",
    "extended":               "Extended",
}

# Best → worst display order
OUTCOME_ORDER = ["extended", "repro_extension_failed", "reproduced", "no_extension", "no_repro"]

# Tailwind color classes per outcome (bar bg, text)
OUTCOME_COLORS = {
    "extended":               ("bg-blue-500",   "text-blue-700"),
    "repro_extension_failed": ("bg-teal-500",   "text-teal-700"),
    "reproduced":             ("bg-green-500",  "text-green-700"),
    "no_extension":           ("bg-orange-400", "text-orange-700"),
    "no_repro":               ("bg-red-500",    "text-red-700"),
}

_SCORE_EXPR = case(
    (Rating.outcome == "no_repro", 1),
    (Rating.outcome == "no_extension", 2),
    (Rating.outcome == "reproduced", 3),
    (Rating.outcome == "repro_extension_failed", 4),
    (Rating.outcome == "extended", 5),
    else_=None,
)


def _get_paper_scores(doi: str, db: Session) -> dict:
    row = db.query(
        func.avg(_SCORE_EXPR).label("avg_score"),
        func.count(Rating.id).label("count"),
    ).filter(Rating.doi == doi).one()

    breakdown_rows = (
        db.query(Rating.outcome, func.count(Rating.id))
        .filter(Rating.doi == doi, Rating.outcome.isnot(None))
        .group_by(Rating.outcome)
        .all()
    )
    breakdown = {outcome: count for outcome, count in breakdown_rows}

    return {
        "avg_score": round(float(row.avg_score), 1) if row.avg_score else None,
        "rating_count": row.count,
        "breakdown": breakdown,
    }


def _format_authors(authors_json: str) -> str:
    try:
        all_authors = json.loads(authors_json)
    except Exception:
        return authors_json
    if len(all_authors) > 4:
        return ", ".join(all_authors[:3]) + ", … " + all_authors[-1]
    if len(all_authors) == 4:
        return ", ".join(all_authors[:3]) + ", " + all_authors[-1]
    return ", ".join(all_authors)


def _dev_context() -> dict:
    return {
        "dev_mode": settings.ORCID_ENV != "production",
        "dev_users": list(enumerate(name for _, name in DEV_FAKE_USERS)),
    }


def _scoring_context() -> dict:
    return {
        "outcome_labels": OUTCOME_LABELS,
        "outcome_order": OUTCOME_ORDER,
        "outcome_colors": OUTCOME_COLORS,
        "outcome_scores": OUTCOME_SCORES,
    }


@router.get("/", response_class=HTMLResponse)
async def index(request: Request, db: Session = Depends(get_db)):
    orcid_id = request.session.get("orcid_id")

    def _enrich(papers):
        return [
            {"paper": p, "display_authors": _format_authors(p.authors), **_get_paper_scores(p.doi, db)}
            for p in papers
        ]

    # Sub-query: most recent rating date per paper
    last_rated_sq = (
        db.query(Rating.doi, func.max(Rating.created_at).label("last_rated"))
        .group_by(Rating.doi)
        .subquery()
    )

    # Papers the logged-in user rated, ordered by their own latest rating
    my_papers = []
    if orcid_id:
        my_dois_sq = (
            db.query(Rating.doi)
            .filter(Rating.orcid_id == orcid_id)
            .subquery()
        )
        my_papers = _enrich(
            db.query(Paper)
            .join(my_dois_sq, Paper.doi == my_dois_sq.c.doi)
            .join(last_rated_sq, Paper.doi == last_rated_sq.c.doi)
            .order_by(last_rated_sq.c.last_rated.desc())
            .limit(5)
            .all()
        )

    # Community feed: most recently rated, excluding user's own papers already shown
    my_doi_set = {e["paper"].doi for e in my_papers}
    community_candidates = (
        db.query(Paper)
        .join(last_rated_sq, Paper.doi == last_rated_sq.c.doi)
        .order_by(last_rated_sq.c.last_rated.desc())
        .limit(10 + len(my_doi_set))
        .all()
    )
    community_papers = _enrich([p for p in community_candidates if p.doi not in my_doi_set][:10])

    return templates.TemplateResponse("index.html", {
        "request": request,
        "my_papers": my_papers,
        "community_papers": community_papers,
        "user_name": request.session.get("user_name"),
        "orcid_id": orcid_id,
        **_dev_context(),
        **_scoring_context(),
    })


@router.get("/search", response_class=HTMLResponse)
async def search(request: Request, doi: str = "", db: Session = Depends(get_db)):
    if not doi:
        return RedirectResponse("/")

    doi = normalise_doi(doi)
    if not is_valid_doi(doi):
        return templates.TemplateResponse("index.html", {
            "request": request,
            "error": "That doesn't look like a valid DOI. Try: 10.xxxx/...",
            "papers": [],
            "user_name": request.session.get("user_name"),
            "orcid_id": request.session.get("orcid_id"),
            **_dev_context(),
            **_scoring_context(),
        })

    paper = db.get(Paper, doi)
    if not paper:
        meta = await fetch_paper_metadata(doi)
        if not meta:
            return templates.TemplateResponse("index.html", {
                "request": request,
                "error": f"No paper found for DOI: {doi}",
                "papers": [],
                "user_name": request.session.get("user_name"),
                "orcid_id": request.session.get("orcid_id"),
                **_dev_context(),
                **_scoring_context(),
            })
        paper = Paper(**meta)
        db.add(paper)
        db.commit()
        db.refresh(paper)

    return RedirectResponse(f"/paper/{doi}", status_code=303)


@router.get("/paper/{doi:path}", response_class=HTMLResponse)
async def paper_page(doi: str, request: Request, db: Session = Depends(get_db)):
    paper = db.get(Paper, doi)
    if not paper:
        meta = await fetch_paper_metadata(doi)
        if not meta:
            raise HTTPException(status_code=404, detail="Paper not found")
        paper = Paper(**meta)
        db.add(paper)
        db.commit()
        db.refresh(paper)

    scores = _get_paper_scores(doi, db)

    # ── Filter / sort / paginate ─────────────────────────────────────────
    PAGE_SIZE = 25
    active_outcome = request.query_params.get("outcome", "")
    active_scope   = request.query_params.get("scope",   "")
    active_sort    = request.query_params.get("sort",    "newest")
    try:
        active_page = max(1, int(request.query_params.get("page", 1)))
    except ValueError:
        active_page = 1

    q = db.query(Rating).filter(Rating.doi == doi)
    if active_outcome:
        q = q.filter(Rating.outcome == active_outcome)
    if active_scope:
        q = q.filter(Rating.scope_level == active_scope)

    total_count = q.count()
    total_pages = max(1, (total_count + PAGE_SIZE - 1) // PAGE_SIZE)
    active_page = min(active_page, total_pages)

    if active_sort == "oldest":
        q = q.order_by(Rating.created_at.asc())
    elif active_sort == "highest":
        q = q.order_by(_SCORE_EXPR.desc().nullslast(), Rating.created_at.desc())
    elif active_sort == "lowest":
        q = q.order_by(_SCORE_EXPR.asc().nullsfirst(), Rating.created_at.desc())
    elif active_sort == "most_liked":
        like_sq = (
            select(Like.rating_id, func.count(Like.id).label("lc"))
            .group_by(Like.rating_id)
            .subquery()
        )
        q = q.outerjoin(like_sq, Rating.id == like_sq.c.rating_id)
        q = q.order_by(func.coalesce(like_sq.c.lc, 0).desc(), Rating.created_at.desc())
    else:
        q = q.order_by(Rating.created_at.desc())

    reviews = q.offset((active_page - 1) * PAGE_SIZE).limit(PAGE_SIZE).all()

    # ── Comments + likes ─────────────────────────────────────────────────
    all_comments = (
        db.query(Comment)
        .filter(Comment.doi == doi)
        .order_by(Comment.created_at.asc())
        .all()
    )
    comment_map: dict[int, list] = {}
    for c in all_comments:
        if c.rating_id:
            comment_map.setdefault(c.rating_id, []).append(c)

    orcid_id = request.session.get("orcid_id")
    user_already_rated = (
        db.query(Rating).filter(Rating.doi == doi, Rating.orcid_id == orcid_id).first()
        if orcid_id else None
    )

    try:
        authors = json.loads(paper.authors)
    except Exception:
        authors = [paper.authors]

    rating_ids = [r.id for r in reviews]
    like_rows = (
        db.query(Like.rating_id, func.count(Like.id))
        .filter(Like.rating_id.in_(rating_ids))
        .group_by(Like.rating_id)
        .all()
    ) if rating_ids else []
    like_counts = {rid: cnt for rid, cnt in like_rows}

    user_likes: set[int] = set()
    if orcid_id and rating_ids:
        user_likes = {
            row.rating_id for row in
            db.query(Like.rating_id)
            .filter(Like.orcid_id == orcid_id, Like.rating_id.in_(rating_ids))
            .all()
        }

    return templates.TemplateResponse("paper.html", {
        "request": request,
        "paper": paper,
        "authors": authors,
        "scores": scores,
        "reviews": reviews,
        "comment_map": comment_map,
        "like_counts": like_counts,
        "user_likes": user_likes,
        "total_count": total_count,
        "total_pages": total_pages,
        "active_page": active_page,
        "active_outcome": active_outcome,
        "active_scope": active_scope,
        "active_sort": active_sort,
        "user_name": request.session.get("user_name"),
        "orcid_id": orcid_id,
        "user_already_rated": user_already_rated,
        **_scoring_context(),
    })


@router.post("/paper/{doi:path}/comment")
async def submit_comment(
    doi: str,
    request: Request,
    db: Session = Depends(get_db),
    rating_id: int = Form(...),
    content: str = Form(""),
):
    orcid_id = request.session.get("orcid_id")
    if not orcid_id:
        return RedirectResponse(f"/auth/guest-setup?next={request.url.path}", status_code=303)
    if not content.strip():
        return RedirectResponse(f"/paper/{doi}", status_code=303)

    paper = db.get(Paper, doi)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    comment = Comment(
        doi=doi,
        rating_id=rating_id,
        orcid_id=orcid_id,
        content=content.strip()[:2000],
    )
    db.add(comment)
    db.commit()
    return RedirectResponse(f"/paper/{doi}#review-{rating_id}", status_code=303)


@router.post("/paper/{doi:path}/ratings/{rating_id}/like")
async def toggle_like(doi: str, rating_id: int, request: Request, db: Session = Depends(get_db)):
    wants_json = "application/json" in request.headers.get("Accept", "")
    orcid_id = request.session.get("orcid_id")
    if not orcid_id:
        if wants_json:
            return JSONResponse({"error": "not authenticated"}, status_code=401)
        return RedirectResponse(f"/auth/guest-setup?next={request.url.path}", status_code=303)

    existing = db.query(Like).filter(Like.rating_id == rating_id, Like.orcid_id == orcid_id).first()
    if existing:
        db.delete(existing)
        liked = False
    else:
        db.add(Like(rating_id=rating_id, orcid_id=orcid_id))
        liked = True
    db.commit()

    count = db.query(func.count(Like.id)).filter(Like.rating_id == rating_id).scalar()

    if wants_json:
        return JSONResponse({"liked": liked, "count": count})
    return RedirectResponse(f"/paper/{doi}#review-{rating_id}", status_code=303)


@router.post("/paper/{doi:path}/rate")
async def submit_rating(
    doi: str,
    request: Request,
    db: Session = Depends(get_db),
    outcome: str = Form(""),
    reproducibility_score: str = Form(""),
    reproducibility_observation: str = Form(""),
    scope_level: str = Form(""),
    scope_observation: str = Form(""),
    modification_details: str = Form(""),
    coi_confirmed: str = Form(""),
):
    orcid_id = request.session.get("orcid_id")
    if not orcid_id:
        return RedirectResponse(f"/auth/guest-setup?next={request.url.path}", status_code=303)

    paper = db.get(Paper, doi)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    if coi_confirmed != "on":
        raise HTTPException(status_code=422, detail="You must confirm no conflict of interest")

    existing = db.query(Rating).filter(Rating.doi == doi, Rating.orcid_id == orcid_id).first()
    if existing:
        raise HTTPException(status_code=409, detail="You have already rated this paper")

    repro_score_int = int(reproducibility_score) if reproducibility_score else None
    if repro_score_int is not None and not (1 <= repro_score_int <= 5):
        raise HTTPException(status_code=422, detail="Reproducibility score must be 1–5")

    rating = Rating(
        doi=doi,
        orcid_id=orcid_id,
        outcome=outcome or None,
        reproducibility_score=repro_score_int,
        reproducibility_observation=reproducibility_observation[:1000] or None,
        scope_level=scope_level or None,
        scope_observation=scope_observation[:1000] or None,
        modification_details=modification_details[:1000] or None,
    )
    db.add(rating)
    db.commit()
    return RedirectResponse(f"/paper/{doi}", status_code=303)


@router.get("/design-demo/scoring", response_class=HTMLResponse)
async def design_demo_scoring(request: Request):
    if settings.ORCID_ENV == "production":
        raise HTTPException(status_code=403)
    return templates.TemplateResponse("design_demo_scoring.html", {
        "request": request,
        "outcome_labels": OUTCOME_LABELS,
        "outcome_colors": OUTCOME_COLORS,
        "outcome_order": OUTCOME_ORDER,
        "user_name": request.session.get("user_name"),
        "orcid_id": request.session.get("orcid_id"),
    })


@router.get("/design-demo", response_class=HTMLResponse)
async def design_demo(request: Request, db: Session = Depends(get_db)):
    if settings.ORCID_ENV == "production":
        raise HTTPException(status_code=403)

    DEMO_DOI = "10.0000/chemrepro.demo.2024"
    paper = db.get(Paper, DEMO_DOI)
    if not paper:
        raise HTTPException(status_code=404, detail="Run seed_demo.py first")

    reviews = db.query(Rating).filter(Rating.doi == DEMO_DOI).order_by(Rating.created_at.desc()).all()
    scored = [OUTCOME_SCORES[r.outcome] for r in reviews if r.outcome in OUTCOME_SCORES]
    score_a = round(sum(scored) / len(scored), 1) if scored else None
    breakdown = {}
    for r in reviews:
        if r.outcome:
            breakdown[r.outcome] = breakdown.get(r.outcome, 0) + 1
    distribution = [(o, OUTCOME_LABELS[o], breakdown.get(o, 0)) for o in OUTCOME_ORDER]

    return templates.TemplateResponse("design_demo.html", {
        "request": request,
        "paper": paper,
        "display_authors": _format_authors(paper.authors),
        "reviews": reviews,
        "score_a": score_a,
        "breakdown": breakdown,
        "outcome_labels": OUTCOME_LABELS,
        "outcome_colors": OUTCOME_COLORS,
        "distribution": distribution,
        "total": len(reviews),
        "user_name": request.session.get("user_name"),
        "orcid_id": request.session.get("orcid_id"),
    })
