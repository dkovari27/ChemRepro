import json
from datetime import datetime, timezone

from app.utils.design import collect_doi_refs, index_tpl, paper_classic_tpl, paper_tpl, register_globals, render_md_refs
from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app import prompts
from app.config import settings
from app.utils.moderation import is_clean as _is_clean
from app.utils.ai_moderation import moderate_comment_bg, moderate_rating_bg
from app.database import get_db
from app.models.author_notification import AuthorNotification
from app.models.comment import Comment, CommentLike
from app.models.like import Like
from app.models.notification import Notification
from app.models.paper import Paper
from app.models.paper_subscription import PaperSubscription
from app.models.collection import Collection
from app.models.saved_paper import SavedPaper
from app.models.rating import Rating
from app.models.user import User
from app.routers.auth import DEV_FAKE_USERS
from app.services.author_notify import notify_author_if_possible
from app.services.crossref import fetch_paper_metadata, is_valid_doi, normalise_doi, resolve_url_to_doi

router = APIRouter(tags=["papers"])
templates = Jinja2Templates(directory="app/templates")
register_globals(templates)


def _collections_flat(orcid_id: str, db: Session) -> list[tuple]:
    all_cols = db.query(Collection).filter(
        Collection.orcid_id == orcid_id).all()
    by_parent: dict = {}
    for c in all_cols:
        by_parent.setdefault(c.parent_id, []).append(c)

    result: list = []

    def walk(parent_id, depth):
        for c in sorted(by_parent.get(parent_id, []), key=lambda x: x.name.lower()):
            result.append((c, depth))
            walk(c.id, depth + 1)

    walk(None, 0)
    return result


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
OUTCOME_ORDER = ["extended", "repro_extension_failed",
                 "reproduced", "no_extension", "no_repro"]

# Tailwind color classes per outcome (bar bg, text)
OUTCOME_COLORS = {
    "extended":               ("bg-blue-500",   "text-blue-700"),
    "repro_extension_failed": ("bg-teal-500",   "text-teal-700"),
    "reproduced":             ("bg-green-500",  "text-green-700"),
    "no_extension":           ("bg-orange-400", "text-orange-700"),
    "no_repro":               ("bg-red-500",    "text-red-700"),
}

ND_STAR_LABELS = {
    1: "Did not work",
    2: "Reproduced with deviation",
    3: "Reproduced as published",
    4: "Minor extension (no new functional group)",
    5: "Major extension (new functional group)",
}
ND_STAR_ORDER = [5, 4, 3, 2, 1]
ND_STAR_COLORS = {
    5: ("bg-blue-500",   "text-blue-700"),
    4: ("bg-teal-500",   "text-teal-700"),
    3: ("bg-green-500",  "text-green-700"),
    2: ("bg-orange-400", "text-orange-700"),
    1: ("bg-red-500",    "text-red-700"),
}
ND_FAILURE_CONTEXT_LABELS = {
    "original_tested": "Tested original",
    "extension_only":  "Extension only",
}

_SCORE_EXPR = case(
    (Rating.outcome == "no_repro", 1),
    (Rating.outcome == "no_extension", 2),
    (Rating.outcome == "reproduced", 3),
    (Rating.outcome == "repro_extension_failed", 4),
    (Rating.outcome == "extended", 5),
    else_=None,
)


def _get_nd_paper_scores(doi: str, db: Session) -> dict:
    nd_filter = [Rating.doi == doi, Rating.scoring_mode ==
                 "new_design", Rating.nd_star.isnot(None)]
    row = db.query(
        func.avg(Rating.nd_star).label("avg_star"),
        func.count(Rating.id).label("count"),
    ).filter(*nd_filter).one()
    dist_rows = (
        db.query(Rating.nd_star, func.count(Rating.id))
        .filter(*nd_filter)
        .group_by(Rating.nd_star)
        .all()
    )
    return {
        "nd_avg_star": round(float(row.avg_star), 1) if row.avg_star else None,
        "nd_rating_count": row.count,
        "nd_star_dist": {star: cnt for star, cnt in dist_rows},
    }


def _get_paper_scores(doi: str, db: Session) -> dict:
    std_filter = [Rating.doi == doi, Rating.scoring_mode == "standard"]
    row = db.query(
        func.avg(_SCORE_EXPR).label("avg_score"),
        func.count(Rating.id).label("count"),
    ).filter(*std_filter).one()

    breakdown_rows = (
        db.query(Rating.outcome, func.count(Rating.id))
        .filter(*std_filter, Rating.outcome.isnot(None))
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
        # hidden for user testing; endpoint still works at /auth/dev-login/{i}
        "dev_mode": False,
        "dev_users": list(enumerate(name for _, name in DEV_FAKE_USERS)),
    }


def _scoring_context() -> dict:
    return {
        "outcome_labels": OUTCOME_LABELS,
        "outcome_order": OUTCOME_ORDER,
        "outcome_colors": OUTCOME_COLORS,
        "outcome_scores": OUTCOME_SCORES,
    }


@router.get("/design-archive/standard/", response_class=HTMLResponse)
async def design_archive_standard(request: Request, db: Session = Depends(get_db)):
    orcid_id = request.session.get("orcid_id")

    def _enrich(papers):
        return [
            {"paper": p, "display_authors": _format_authors(
                p.authors), **_get_paper_scores(p.doi, db)}
            for p in papers
        ]

    last_rated_sq = (
        db.query(Rating.doi, func.max(Rating.created_at).label("last_rated"))
        .group_by(Rating.doi)
        .subquery()
    )

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

    my_doi_set = {e["paper"].doi for e in my_papers}
    community_candidates = (
        db.query(Paper)
        .join(last_rated_sq, Paper.doi == last_rated_sq.c.doi)
        .order_by(last_rated_sq.c.last_rated.desc())
        .limit(10 + len(my_doi_set))
        .all()
    )
    community_papers = _enrich(
        [p for p in community_candidates if p.doi not in my_doi_set][:10])

    return templates.TemplateResponse("index.html", {
        "request": request,
        "my_papers": my_papers,
        "community_papers": community_papers,
        "user_name": request.session.get("user_name"),
        "orcid_id": orcid_id,
        "site_version": "standard",
        "switch_urls": {"standard": "/design-archive/standard/", "classic": "/classic/", "new_design": "/nd/"},
        **_dev_context(),
        **_scoring_context(),
    })


@router.get("/search", response_class=HTMLResponse)
async def search(request: Request, doi: str = "", db: Session = Depends(get_db)):
    if not doi:
        return RedirectResponse("/")

    if doi.strip().lower() == "demo":
        return RedirectResponse("/paper/demo", status_code=303)

    # Some publisher URLs (PubMed, ScienceDirect) need an async API call to resolve to DOI
    resolved = await resolve_url_to_doi(doi)
    doi = resolved if resolved else normalise_doi(doi)

    if not is_valid_doi(doi):
        return templates.TemplateResponse("index_nd.html", {
            "request": request,
            "error": "That doesn't look like a valid DOI. Try: 10.xxxx/...",
            "my_papers": [],
            "community_papers": [],
            "user_name": request.session.get("user_name"),
            "orcid_id": request.session.get("orcid_id"),
            "site_version": "new_design",
            "switch_urls": {"standard": "/design-archive/standard/", "classic": "/classic/", "new_design": "/nd/"},
            **_dev_context(),
            **_nd_scoring_context(),
        })

    paper = db.get(Paper, doi)
    if not paper:
        meta = await fetch_paper_metadata(doi)
        if not meta:
            return templates.TemplateResponse("index_nd.html", {
                "request": request,
                "error": f"No paper found for DOI: {doi}",
                "my_papers": [],
                "community_papers": [],
                "user_name": request.session.get("user_name"),
                "orcid_id": request.session.get("orcid_id"),
                "site_version": "new_design",
                "switch_urls": {"standard": "/design-archive/standard/", "classic": "/classic/", "new_design": "/nd/"},
                **_dev_context(),
                **_nd_scoring_context(),
            })
        paper = Paper(**meta)
        db.add(paper)
        db.commit()
        db.refresh(paper)

    return RedirectResponse(f"/paper/{doi}", status_code=303)


# ── Helpers (defined early so edit/notification routes can reference them) ────

def _maybe_notify(
    db: Session,
    *,
    notif_type: str,
    actor_orcid_id: str,
    actor_name: str,
    rating: Rating,
    paper: Paper,
) -> None:
    """Create a notification for the review author, unless they are the actor."""
    if rating.orcid_id == actor_orcid_id:
        return
    db.add(Notification(
        recipient_orcid_id=rating.orcid_id,
        type=notif_type,
        actor_name=actor_name,
        rating_id=rating.id,
        doi=paper.doi,
        paper_title=(paper.title or "")[:200],
    ))


def _own_rating_or_404(rating_id: int, orcid_id: str, db: Session) -> Rating:
    r = db.get(Rating, rating_id)
    if not r:
        raise HTTPException(status_code=404, detail="Review not found")
    if r.orcid_id != orcid_id:
        raise HTTPException(status_code=403, detail="Not your review")
    return r


def _delete_rating(r: Rating, db: Session) -> None:
    db.query(Like).filter(Like.rating_id == r.id).delete()
    db.query(Comment).filter(Comment.rating_id == r.id).delete()
    db.delete(r)
    db.commit()


# ── Demo paper (must be before the greedy /paper/{doi:path} route) ───────────

@router.get("/paper/demo", response_class=HTMLResponse)
async def demo_paper_page(request: Request):
    return templates.TemplateResponse("demo.html", {
        "request": request,
        "user_name": request.session.get("user_name"),
        "orcid_id": request.session.get("orcid_id"),
        "site_version": "new_design",
        "switch_urls": {"standard": "/paper/demo", "classic": "/paper/demo", "new_design": "/paper/demo"},
        **_nd_scoring_context(),
    })


@router.get("/demo", response_class=HTMLResponse)
async def demo_index_page(request: Request):
    start_tour = bool(request.session.pop("tour_pending", None))
    return templates.TemplateResponse("demo_index.html", {
        "request": request,
        "user_name": request.session.get("user_name"),
        "orcid_id": request.session.get("orcid_id"),
        "start_tour": start_tour,
        **_nd_scoring_context(),
    })


# ── Standard: GET edit (must be before the greedy /design-archive/standard/paper/{doi:path} route) ───

@router.get("/design-archive/standard/paper/{doi:path}/ratings/{rating_id}/edit", response_class=HTMLResponse)
async def edit_rating_page(doi: str, rating_id: int, request: Request, db: Session = Depends(get_db)):
    orcid_id = request.session.get("orcid_id")
    if not orcid_id:
        return RedirectResponse(f"/auth/guest-setup?next=/design-archive/standard/paper/{doi}", status_code=303)
    r = _own_rating_or_404(rating_id, orcid_id, db)
    paper = db.get(Paper, doi)
    if not paper:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse("edit_rating.html", {
        "request": request,
        "paper": paper,
        "rating": r,
        "outcome_labels": OUTCOME_LABELS,
        "outcome_order": OUTCOME_ORDER,
        "outcome_scores": OUTCOME_SCORES,
        "prompts": __import__("app.prompts", fromlist=["prompts"]),
        "user_name": request.session.get("user_name"),
        "orcid_id": orcid_id,
        "site_version": "standard",
        "switch_urls": {"standard": "/", "classic": "/classic/", "new_design": "/nd/"},
    })


@router.get("/design-archive/standard/paper/{doi:path}", response_class=HTMLResponse)
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
    elif paper.abstract is None:
        meta = await fetch_paper_metadata(doi)
        if meta and meta.get("abstract"):
            paper.abstract = meta["abstract"]
            db.commit()

    scores = _get_paper_scores(doi, db)

    # ── Scoring mode (v2 = single score | classic = repro stars + outcome) ─
    scoring_mode = request.query_params.get("mode", "v2")
    if scoring_mode not in ("v2", "classic"):
        scoring_mode = "v2"

    # Classic mode: also compute average repro score
    classic_scores = {}
    if scoring_mode == "classic":
        row = (
            db.query(func.avg(Rating.reproducibility_score).label("avg_repro"))
            .filter(Rating.doi == doi, Rating.scoring_mode == "classic",
                    Rating.reproducibility_score.isnot(None))
            .one()
        )
        classic_scores["avg_repro"] = round(
            float(row.avg_repro), 1) if row.avg_repro else None

    # ── Filter / sort / paginate ─────────────────────────────────────────
    PAGE_SIZE = 25
    active_outcome = request.query_params.get("outcome", "")
    active_scope = request.query_params.get("scope",   "")
    active_sort = request.query_params.get("sort",    "newest")
    try:
        active_page = max(1, int(request.query_params.get("page", 1)))
    except ValueError:
        active_page = 1

    q = db.query(Rating).filter(Rating.doi == doi, Rating.scoring_mode == "standard", Rating.ai_flagged == False)  # noqa: E712
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
        q = q.order_by(_SCORE_EXPR.desc().nullslast(),
                       Rating.created_at.desc())
    elif active_sort == "lowest":
        q = q.order_by(_SCORE_EXPR.asc().nullsfirst(),
                       Rating.created_at.desc())
    elif active_sort == "most_liked":
        like_sq = (
            select(Like.rating_id, func.count(Like.id).label("lc"))
            .group_by(Like.rating_id)
            .subquery()
        )
        q = q.outerjoin(like_sq, Rating.id == like_sq.c.rating_id)
        q = q.order_by(func.coalesce(like_sq.c.lc, 0).desc(),
                       Rating.created_at.desc())
    else:
        q = q.order_by(Rating.created_at.desc())

    reviews = q.offset((active_page - 1) * PAGE_SIZE).limit(PAGE_SIZE).all()

    # ── Comments + comment likes ──────────────────────────────────────────
    all_comments = (
        db.query(Comment)
        .filter(Comment.doi == doi, Comment.ai_flagged == False)  # noqa: E712
        .order_by(Comment.created_at.asc())
        .all()
    )
    # Separate top-level comments (parent_id=None) from replies
    comment_map: dict[int, list] = {}   # rating_id → [top-level Comment]
    reply_map: dict[int, list] = {}     # comment_id → [reply Comment]
    for c in all_comments:
        if c.parent_id:
            reply_map.setdefault(c.parent_id, []).append(c)
        elif c.rating_id:
            comment_map.setdefault(c.rating_id, []).append(c)

    # Comment like counts and user's liked comment ids
    comment_ids = [c.id for c in all_comments]
    comment_like_rows = (
        db.query(CommentLike.comment_id, func.count(CommentLike.id))
        .filter(CommentLike.comment_id.in_(comment_ids))
        .group_by(CommentLike.comment_id)
        .all()
    ) if comment_ids else []
    comment_like_counts = {cid: cnt for cid, cnt in comment_like_rows}

    orcid_id = request.session.get("orcid_id")
    user_comment_likes: set[int] = set()
    if orcid_id and comment_ids:
        user_comment_likes = {
            row.comment_id for row in
            db.query(CommentLike.comment_id)
            .filter(CommentLike.orcid_id == orcid_id, CommentLike.comment_id.in_(comment_ids))
            .all()
        }
    user_already_rated = (
        db.query(Rating).filter(
            Rating.doi == doi, Rating.orcid_id == orcid_id, Rating.scoring_mode == "standard"
        ).first()
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

    # Collect all DOIs referenced in review text and comments, then batch-load
    _ref_texts = (
        [r.reproducibility_observation for r in reviews]
        + [r.scope_observation for r in reviews]
        + [r.modification_details for r in reviews]
        + [c.content for c in all_comments]
    )
    _ref_dois = collect_doi_refs(_ref_texts) - {doi}
    papers_by_doi: dict = {}
    if _ref_dois:
        for _p in db.query(Paper).filter(Paper.doi.in_(_ref_dois)).all():
            papers_by_doi[_p.doi] = _p
        # Auto-fetch any referenced paper not yet in the DB (saves for future loads too)
        for _missing_doi in _ref_dois - papers_by_doi.keys():
            try:
                _meta = await fetch_paper_metadata(_missing_doi)
                if _meta:
                    _new_p = Paper(**_meta)
                    db.add(_new_p)
                    db.commit()
                    db.refresh(_new_p)
                    papers_by_doi[_missing_doi] = _new_p
            except Exception:
                db.rollback()

    saved_entry = (
        db.query(SavedPaper).filter(
            SavedPaper.orcid_id == orcid_id,
            SavedPaper.doi == doi,
        ).first()
        if orcid_id else None
    )
    user_collections_flat = _collections_flat(orcid_id, db) if orcid_id else []

    return templates.TemplateResponse(paper_tpl(request), {
        "request": request,
        "paper": paper,
        "authors": authors,
        "scores": scores,
        "reviews": reviews,
        "comment_map": comment_map,
        "reply_map": reply_map,
        "comment_like_counts": comment_like_counts,
        "user_comment_likes": user_comment_likes,
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
        "saved_entry": saved_entry,
        "user_collections_flat": user_collections_flat,
        "papers_by_doi": papers_by_doi,
        "prompts": prompts,
        "site_version": "standard",
        "switch_urls": {"standard": f"/design-archive/standard/paper/{doi}", "classic": f"/classic/paper/{doi}", "new_design": f"/paper/{doi}"},
        **_scoring_context(),
    })


@router.post("/design-archive/standard/paper/{doi:path}/comment")
async def submit_comment(
    doi: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    rating_id: int = Form(...),
    content: str = Form(""),
):
    orcid_id = request.session.get("orcid_id")
    if not orcid_id:
        return RedirectResponse(f"/auth/guest-setup?next={request.url.path}", status_code=303)
    if not content.strip():
        return RedirectResponse(f"/design-archive/standard/paper/{doi}", status_code=303)
    if not _is_clean(content):
        raise HTTPException(
            status_code=422, detail="Content contains prohibited language.")

    paper = db.get(Paper, doi)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    rating = db.get(Rating, rating_id)
    comment = Comment(
        doi=doi,
        rating_id=rating_id,
        orcid_id=orcid_id,
        content=content.strip()[:2000],
    )
    db.add(comment)
    if rating:
        _maybe_notify(
            db,
            notif_type="comment",
            actor_orcid_id=orcid_id,
            actor_name=request.session.get("user_name", "Someone"),
            rating=rating,
            paper=paper,
        )
    _notify_paper_subscribers(
        db, doi=doi, paper=paper, notif_type="new_comment",
        actor_name=request.session.get("user_name", "Someone"),
        rating_id=rating_id,
        exclude_orcid=orcid_id,
    )
    db.commit()
    background_tasks.add_task(moderate_comment_bg, comment.id)
    return RedirectResponse(f"/design-archive/standard/paper/{doi}#review-{rating_id}", status_code=303)


@router.post("/design-archive/standard/paper/{doi:path}/ratings/{rating_id}/like")
async def toggle_like(doi: str, rating_id: int, request: Request, db: Session = Depends(get_db)):
    wants_json = "application/json" in request.headers.get("Accept", "")
    orcid_id = request.session.get("orcid_id")
    if not orcid_id:
        if wants_json:
            return JSONResponse({"error": "not authenticated"}, status_code=401)
        return RedirectResponse(f"/auth/guest-setup?next={request.url.path}", status_code=303)

    existing = db.query(Like).filter(
        Like.rating_id == rating_id, Like.orcid_id == orcid_id).first()
    if existing:
        db.delete(existing)
        liked = False
    else:
        db.add(Like(rating_id=rating_id, orcid_id=orcid_id))
        liked = True
        rating = db.get(Rating, rating_id)
        if rating:
            paper = db.get(Paper, doi)
            if paper:
                _maybe_notify(
                    db,
                    notif_type="like",
                    actor_orcid_id=orcid_id,
                    actor_name=request.session.get("user_name", "Someone"),
                    rating=rating,
                    paper=paper,
                )
    db.commit()

    count = db.query(func.count(Like.id)).filter(
        Like.rating_id == rating_id).scalar()

    if wants_json:
        return JSONResponse({"liked": liked, "count": count})
    return RedirectResponse(f"/design-archive/standard/paper/{doi}#review-{rating_id}", status_code=303)


@router.post("/design-archive/standard/paper/{doi:path}/rate")
async def submit_rating(
    doi: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    outcome: str = Form(""),
    reproducibility_score: str = Form(""),
    reproducibility_observation: str = Form(""),
    scope_level: str = Form(""),
    scope_observation: str = Form(""),
    modification_details: str = Form(""),
    coi_confirmed: str = Form(""),
    scoring_mode: str = Form("v2"),
):
    scoring_mode = "standard"  # form always submits standard; classic has its own endpoint
    orcid_id = request.session.get("orcid_id")
    if not orcid_id:
        return RedirectResponse(f"/auth/guest-setup?next={request.url.path}", status_code=303)

    paper = db.get(Paper, doi)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    if coi_confirmed != "on":
        raise HTTPException(
            status_code=422, detail="You must confirm no conflict of interest")
    if not _is_clean(reproducibility_observation, scope_observation, modification_details):
        raise HTTPException(
            status_code=422, detail="Content contains prohibited language.")

    existing = db.query(Rating).filter(
        Rating.doi == doi, Rating.orcid_id == orcid_id, Rating.scoring_mode == "standard"
    ).first()
    if existing:
        raise HTTPException(
            status_code=409, detail="You have already rated this paper")

    repro_score_int = int(
        reproducibility_score) if reproducibility_score else None
    if repro_score_int is not None and not (1 <= repro_score_int <= 5):
        raise HTTPException(
            status_code=422, detail="Reproducibility score must be 1–5")

    rating = Rating(
        doi=doi,
        orcid_id=orcid_id,
        outcome=outcome or None,
        reproducibility_score=repro_score_int,
        reproducibility_observation=reproducibility_observation[:1000] or None,
        scope_level=scope_level or None,
        scope_observation=scope_observation[:1000] or None,
        modification_details=modification_details[:1000] or None,
        scoring_mode=scoring_mode,
    )
    db.add(rating)
    db.flush()  # get rating.id before commit
    _notify_paper_subscribers(
        db, doi=doi, paper=paper, notif_type="new_review",
        actor_name=request.session.get("user_name", "Someone"),
        rating_id=rating.id,
        exclude_orcid=orcid_id,
    )
    db.commit()
    base_url = str(request.base_url).rstrip("/")
    background_tasks.add_task(
        notify_author_if_possible, doi, paper.title or "", rating.id, db, base_url
    )
    background_tasks.add_task(moderate_rating_bg, rating.id)
    return RedirectResponse(f"/design-archive/standard/paper/{doi}", status_code=303)


# ── Subscription toggle ───────────────────────────────────────────────────────

@router.post("/design-archive/standard/paper/{doi:path}/subscribe")
async def toggle_subscribe(doi: str, request: Request, db: Session = Depends(get_db)):
    orcid_id = request.session.get("orcid_id")
    if not orcid_id:
        return JSONResponse({"error": "not authenticated"}, status_code=401)
    existing = db.query(PaperSubscription).filter(
        PaperSubscription.doi == doi, PaperSubscription.orcid_id == orcid_id
    ).first()
    if existing:
        db.delete(existing)
        subscribed = False
    else:
        db.add(PaperSubscription(orcid_id=orcid_id, doi=doi))
        subscribed = True
    db.commit()
    return JSONResponse({"subscribed": subscribed})


# ── Comment likes ────────────────────────────────────────────────────────────

@router.post("/design-archive/standard/paper/{doi:path}/comment/{comment_id}/like")
async def toggle_comment_like(doi: str, comment_id: int, request: Request, db: Session = Depends(get_db)):
    wants_json = "application/json" in request.headers.get("Accept", "")
    orcid_id = request.session.get("orcid_id")
    if not orcid_id:
        return JSONResponse({"error": "not authenticated"}, status_code=401)

    existing = db.query(CommentLike).filter(
        CommentLike.comment_id == comment_id, CommentLike.orcid_id == orcid_id
    ).first()
    if existing:
        db.delete(existing)
        liked = False
    else:
        db.add(CommentLike(comment_id=comment_id, orcid_id=orcid_id))
        liked = True
        # Notify comment author
        comment = db.get(Comment, comment_id)
        if comment and comment.orcid_id != orcid_id:
            paper = db.get(Paper, doi)
            if paper:
                db.add(Notification(
                    recipient_orcid_id=comment.orcid_id,
                    type="comment_like",
                    actor_name=request.session.get("user_name", "Someone"),
                    rating_id=comment.rating_id or 0,
                    doi=doi,
                    paper_title=(paper.title or "")[:200],
                ))
    db.commit()

    count = db.query(func.count(CommentLike.id)).filter(
        CommentLike.comment_id == comment_id).scalar()
    if wants_json:
        return JSONResponse({"liked": liked, "count": count})
    return RedirectResponse(f"/design-archive/standard/paper/{doi}", status_code=303)


# ── Edit a comment ───────────────────────────────────────────────────────────

@router.post("/design-archive/standard/paper/{doi:path}/comment/{comment_id}/edit")
async def edit_comment(
    doi: str,
    comment_id: int,
    request: Request,
    content: str = Form(""),
    db: Session = Depends(get_db),
):
    orcid_id = request.session.get("orcid_id")
    if not orcid_id:
        return JSONResponse({"error": "not authenticated"}, status_code=401)

    comment = db.query(Comment).filter(
        Comment.id == comment_id,
        Comment.doi == doi,
        Comment.orcid_id == orcid_id,
    ).first()
    if not comment:
        return JSONResponse({"error": "not found"}, status_code=404)

    content = content.strip()[:2000]
    if not content:
        return JSONResponse({"error": "content required"}, status_code=422)
    if not _is_clean(content):
        return JSONResponse({"error": "prohibited language"}, status_code=422)

    comment.content = content
    db.commit()

    # Build papers_by_doi for any referenced DOIs in the edited text
    _ref_dois = collect_doi_refs([content]) - {doi}
    _papers: dict = {}
    if _ref_dois:
        for _p in db.query(Paper).filter(Paper.doi.in_(_ref_dois)).all():
            _papers[_p.doi] = _p
        for _d in _ref_dois - _papers.keys():
            try:
                _meta = await fetch_paper_metadata(_d)
                if _meta:
                    _np = Paper(**_meta)
                    db.add(_np)
                    db.commit()
                    db.refresh(_np)
                    _papers[_d] = _np
            except Exception:
                db.rollback()

    return JSONResponse({"ok": True, "rendered_html": render_md_refs(content, _papers)})


# ── Reply to a comment (1 level deep) ────────────────────────────────────────

@router.post("/design-archive/standard/paper/{doi:path}/comment/{parent_id}/reply")
async def submit_reply(
    doi: str,
    parent_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    content: str = Form(""),
):
    orcid_id = request.session.get("orcid_id")
    if not orcid_id:
        return RedirectResponse(f"/auth/guest-setup?next=/design-archive/standard/paper/{doi}", status_code=303)
    content = content.strip()[:2000]
    if not content:
        return RedirectResponse(f"/design-archive/standard/paper/{doi}", status_code=303)
    if not _is_clean(content):
        raise HTTPException(
            status_code=422, detail="Content contains prohibited language.")

    parent = db.get(Comment, parent_id)
    if not parent:
        raise HTTPException(status_code=404, detail="Comment not found")

    reply = Comment(
        doi=doi,
        rating_id=parent.rating_id,
        parent_id=parent_id,
        orcid_id=orcid_id,
        content=content,
    )
    db.add(reply)

    # Notify parent comment author
    if parent.orcid_id != orcid_id:
        paper = db.get(Paper, doi)
        if paper:
            db.add(Notification(
                recipient_orcid_id=parent.orcid_id,
                type="comment_reply",
                actor_name=request.session.get("user_name", "Someone"),
                rating_id=parent.rating_id or 0,
                doi=doi,
                paper_title=(paper.title or "")[:200],
            ))
    db.commit()
    background_tasks.add_task(moderate_comment_bg, reply.id)
    anchor = f"#review-{parent.rating_id}" if parent.rating_id else ""
    return RedirectResponse(f"/design-archive/standard/paper/{doi}{anchor}", status_code=303)


# ── Classic-view variants (redirect back to /classic/paper/{doi}) ─────────────

@router.post("/classic/paper/{doi:path}/comment")
async def classic_submit_comment(
    doi: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    rating_id: int = Form(...),
    content: str = Form(""),
):
    orcid_id = request.session.get("orcid_id")
    if not orcid_id:
        return RedirectResponse(f"/auth/guest-setup?next=/classic/paper/{doi}", status_code=303)
    if not content.strip():
        return RedirectResponse(f"/classic/paper/{doi}", status_code=303)
    if not _is_clean(content):
        raise HTTPException(
            status_code=422, detail="Content contains prohibited language.")

    paper = db.get(Paper, doi)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    rating = db.get(Rating, rating_id)
    comment = Comment(
        doi=doi,
        rating_id=rating_id,
        orcid_id=orcid_id,
        content=content.strip()[:2000],
    )
    db.add(comment)
    if rating:
        _maybe_notify(
            db,
            notif_type="comment",
            actor_orcid_id=orcid_id,
            actor_name=request.session.get("user_name", "Someone"),
            rating=rating,
            paper=paper,
        )
    _notify_paper_subscribers(
        db, doi=doi, paper=paper, notif_type="new_comment",
        actor_name=request.session.get("user_name", "Someone"),
        rating_id=rating_id,
        exclude_orcid=orcid_id,
    )
    db.commit()
    background_tasks.add_task(moderate_comment_bg, comment.id)
    return RedirectResponse(f"/classic/paper/{doi}#review-{rating_id}", status_code=303)


@router.post("/classic/paper/{doi:path}/comment/{parent_id}/reply")
async def classic_submit_reply(
    doi: str,
    parent_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    content: str = Form(""),
):
    orcid_id = request.session.get("orcid_id")
    if not orcid_id:
        return RedirectResponse(f"/auth/guest-setup?next=/classic/paper/{doi}", status_code=303)
    content = content.strip()[:2000]
    if not content:
        return RedirectResponse(f"/classic/paper/{doi}", status_code=303)
    if not _is_clean(content):
        raise HTTPException(
            status_code=422, detail="Content contains prohibited language.")

    parent = db.get(Comment, parent_id)
    if not parent:
        raise HTTPException(status_code=404, detail="Comment not found")

    reply = Comment(
        doi=doi,
        rating_id=parent.rating_id,
        parent_id=parent_id,
        orcid_id=orcid_id,
        content=content,
    )
    db.add(reply)

    if parent.orcid_id != orcid_id:
        paper = db.get(Paper, doi)
        if paper:
            db.add(Notification(
                recipient_orcid_id=parent.orcid_id,
                type="comment_reply",
                actor_name=request.session.get("user_name", "Someone"),
                rating_id=parent.rating_id or 0,
                doi=doi,
                paper_title=(paper.title or "")[:200],
            ))
    db.commit()
    background_tasks.add_task(moderate_comment_bg, reply.id)
    anchor = f"#review-{parent.rating_id}" if parent.rating_id else ""
    return RedirectResponse(f"/classic/paper/{doi}{anchor}", status_code=303)


def _notify_paper_subscribers(
    db: Session,
    *,
    doi: str,
    paper: Paper,
    notif_type: str,
    actor_name: str,
    rating_id: int,
    exclude_orcid: str | None = None,
) -> None:
    """Create in-app notifications for all subscribers of a paper."""
    subs = db.query(PaperSubscription).filter(
        PaperSubscription.doi == doi).all()
    for sub in subs:
        if sub.orcid_id == exclude_orcid:
            continue
        db.add(Notification(
            recipient_orcid_id=sub.orcid_id,
            type=notif_type,
            actor_name=actor_name,
            rating_id=rating_id,
            doi=doi,
            paper_title=(paper.title or "")[:200],
        ))


# ── Author notification opt-out ───────────────────────────────────────────────

def _opt_out_ctx(request, record, token, done=None):
    return {
        "request": request,
        "record": record,
        "token": token,
        "done": done,
        "user_name": request.session.get("user_name"),
        "orcid_id": request.session.get("orcid_id"),
        "site_version": "standard",
        "switch_urls": {"standard": "/", "classic": "/classic/", "new_design": "/nd/"},
    }


@router.get("/notify/opt-out/{token}", response_class=HTMLResponse)
async def author_opt_out(token: str, request: Request, db: Session = Depends(get_db)):
    record = db.query(AuthorNotification).filter(
        AuthorNotification.opt_out_token == token
    ).first()
    done = request.query_params.get("done")
    return templates.TemplateResponse("opt_out.html", _opt_out_ctx(request, record, token, done))


@router.get("/notify/opt-out/{token}/paper")
@router.post("/notify/opt-out/{token}/paper")
async def author_opt_out_paper(token: str, request: Request, db: Session = Depends(get_db)):
    record = db.query(AuthorNotification).filter(
        AuthorNotification.opt_out_token == token
    ).first()
    if record and not record.opted_out:
        record.opted_out = True
        db.commit()
    return RedirectResponse(f"/notify/opt-out/{token}?done=paper", status_code=303)


@router.get("/notify/opt-out/{token}/all")
@router.post("/notify/opt-out/{token}/all")
async def author_opt_out_all(token: str, request: Request, db: Session = Depends(get_db)):
    record = db.query(AuthorNotification).filter(
        AuthorNotification.opt_out_token == token
    ).first()
    if record:
        db.query(AuthorNotification).filter(
            AuthorNotification.email_hash == record.email_hash
        ).update({"opted_out": True, "global_opted_out": True}, synchronize_session=False)
        db.commit()
    return RedirectResponse(f"/notify/opt-out/{token}?done=all", status_code=303)


@router.get("/design-demo/scoring-ab", response_class=HTMLResponse)
async def design_demo_scoring_ab(request: Request):
    if settings.ORCID_ENV == "production":
        raise HTTPException(status_code=403)
    from app import prompts as _prompts
    return templates.TemplateResponse("design_demo_scoring_ab.html", {
        "request": request,
        "outcome_labels": OUTCOME_LABELS,
        "outcome_colors": OUTCOME_COLORS,
        "outcome_order": OUTCOME_ORDER,
        "outcome_scores": OUTCOME_SCORES,
        "prompts": _prompts,
        "user_name": request.session.get("user_name"),
        "orcid_id": request.session.get("orcid_id"),
    })


@router.get("/classic/", response_class=HTMLResponse)
@router.get("/classic", response_class=HTMLResponse)
async def classic_index(request: Request, db: Session = Depends(get_db)):
    orcid_id = request.session.get("orcid_id")

    def _enrich_classic(papers):
        out = []
        for p in papers:
            repro_row = (
                db.query(func.avg(Rating.reproducibility_score).label("avg_repro"),
                         func.count(Rating.id).label("rc"))
                .filter(Rating.doi == p.doi, Rating.scoring_mode == "classic",
                        Rating.reproducibility_score.isnot(None)).one()
            )
            ext_row = (
                db.query(func.avg(Rating.generalisability_score).label("avg_ext"),
                         func.count(Rating.id).label("ec"))
                .filter(Rating.doi == p.doi, Rating.scoring_mode == "classic",
                        Rating.generalisability_score.isnot(None)).one()
            )
            repro_dist = {i: (db.query(func.count(Rating.id))
                              .filter(Rating.doi == p.doi, Rating.scoring_mode == "classic",
                                      Rating.reproducibility_score == i).scalar() or 0)
                          for i in range(1, 6)}
            ext_dist = {i: (db.query(func.count(Rating.id))
                            .filter(Rating.doi == p.doi, Rating.scoring_mode == "classic",
                        Rating.generalisability_score == i).scalar() or 0)
                        for i in range(1, 6)}
            out.append({
                "paper": p,
                "display_authors": _format_authors(p.authors),
                "avg_repro": round(float(repro_row.avg_repro), 1) if repro_row.avg_repro else None,
                "avg_ext": round(float(ext_row.avg_ext), 1) if ext_row.avg_ext else None,
                "repro_dist": repro_dist,
                "ext_dist": ext_dist,
                "total_repro": sum(repro_dist.values()),
                "total_ext": sum(ext_dist.values()),
            })
        return out

    last_rated_sq = (
        db.query(Rating.doi, func.max(Rating.created_at).label("last_rated"))
        .group_by(Rating.doi).subquery()
    )
    my_papers, my_doi_set = [], set()
    if orcid_id:
        my_dois_sq = db.query(Rating.doi).filter(
            Rating.orcid_id == orcid_id).subquery()
        my_papers = _enrich_classic(
            db.query(Paper)
            .join(my_dois_sq, Paper.doi == my_dois_sq.c.doi)
            .join(last_rated_sq, Paper.doi == last_rated_sq.c.doi)
            .order_by(last_rated_sq.c.last_rated.desc()).limit(5).all()
        )
        my_doi_set = {e["paper"].doi for e in my_papers}

    community_candidates = (
        db.query(Paper).join(last_rated_sq, Paper.doi == last_rated_sq.c.doi)
        .order_by(last_rated_sq.c.last_rated.desc()).limit(10 + len(my_doi_set)).all()
    )
    community_papers = _enrich_classic(
        [p for p in community_candidates if p.doi not in my_doi_set][:10])

    return templates.TemplateResponse(index_tpl(request), {
        "request": request,
        "my_papers": my_papers,
        "community_papers": community_papers,
        "user_name": request.session.get("user_name"),
        "orcid_id": orcid_id,
        "site_version": "classic",
        "switch_urls": {"standard": "/", "classic": "/classic/", "new_design": "/nd/"},
        **_dev_context(),
        **_scoring_context(),
    })


# ── Classic: GET edit (must be before the greedy /classic/paper/{doi:path} route) ──

@router.get("/classic/paper/{doi:path}/ratings/{rating_id}/edit", response_class=HTMLResponse)
async def classic_edit_rating_page(doi: str, rating_id: int, request: Request, db: Session = Depends(get_db)):
    orcid_id = request.session.get("orcid_id")
    if not orcid_id:
        return RedirectResponse(f"/auth/guest-setup?next=/classic/paper/{doi}", status_code=303)
    r = _own_rating_or_404(rating_id, orcid_id, db)
    paper = db.get(Paper, doi)
    if not paper:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse("edit_rating_classic.html", {
        "request": request,
        "paper": paper,
        "rating": r,
        "prompts": __import__("app.prompts", fromlist=["prompts"]),
        "user_name": request.session.get("user_name"),
        "orcid_id": orcid_id,
        "site_version": "classic",
        "switch_urls": {"standard": "/", "classic": "/classic/", "new_design": "/nd/"},
    })


@router.get("/classic/paper/{doi:path}", response_class=HTMLResponse)
async def classic_paper_page(doi: str, request: Request, db: Session = Depends(get_db)):
    paper = db.get(Paper, doi)
    if not paper:
        meta = await fetch_paper_metadata(doi)
        if not meta:
            raise HTTPException(status_code=404, detail="Paper not found")
        paper = Paper(**meta)
        db.add(paper)
        db.commit()
        db.refresh(paper)
    elif paper.abstract is None:
        meta = await fetch_paper_metadata(doi)
        if meta and meta.get("abstract"):
            paper.abstract = meta["abstract"]
            db.commit()

    # Classic dual scores
    repro_row = (
        db.query(func.avg(Rating.reproducibility_score).label("avg_repro"),
                 func.count(Rating.id).label("repro_count"))
        .filter(Rating.doi == doi, Rating.scoring_mode == "classic",
                Rating.reproducibility_score.isnot(None))
        .one()
    )
    ext_row = (
        db.query(func.avg(Rating.generalisability_score).label("avg_ext"),
                 func.count(Rating.id).label("ext_count"))
        .filter(Rating.doi == doi, Rating.scoring_mode == "classic",
                Rating.generalisability_score.isnot(None))
        .one()
    )
    # Repro breakdown distribution 1-5
    repro_dist = {
        i: (db.query(func.count(Rating.id))
            .filter(Rating.doi == doi, Rating.scoring_mode == "classic",
                    Rating.reproducibility_score == i)
            .scalar() or 0)
        for i in range(1, 6)
    }
    ext_dist = {
        i: (db.query(func.count(Rating.id))
            .filter(Rating.doi == doi, Rating.scoring_mode == "classic",
                    Rating.generalisability_score == i)
            .scalar() or 0)
        for i in range(1, 6)
    }
    classic_scores = {
        "avg_repro": round(float(repro_row.avg_repro), 1) if repro_row.avg_repro else None,
        "avg_ext": round(float(ext_row.avg_ext), 1) if ext_row.avg_ext else None,
        "repro_count": repro_row.repro_count,
        "ext_count": ext_row.ext_count,
        "repro_dist": repro_dist,
        "ext_dist": ext_dist,
        "total_repro": sum(repro_dist.values()),
        "total_ext": sum(ext_dist.values()),
    }

    # Pagination / filter / sort (same logic as Standard)
    PAGE_SIZE = 25
    active_sort = request.query_params.get("sort", "newest")
    try:
        active_page = max(1, int(request.query_params.get("page", 1)))
    except ValueError:
        active_page = 1

    q = db.query(Rating).filter(Rating.doi == doi, Rating.scoring_mode == "classic", Rating.ai_flagged == False)  # noqa: E712
    total_count = q.count()
    total_pages = max(1, (total_count + PAGE_SIZE - 1) // PAGE_SIZE)
    active_page = min(active_page, total_pages)

    if active_sort == "oldest":
        q = q.order_by(Rating.created_at.asc())
    elif active_sort == "most_liked":
        like_sq = (
            select(Like.rating_id, func.count(Like.id).label("lc"))
            .group_by(Like.rating_id).subquery()
        )
        q = q.outerjoin(like_sq, Rating.id == like_sq.c.rating_id)
        q = q.order_by(func.coalesce(like_sq.c.lc, 0).desc(),
                       Rating.created_at.desc())
    else:
        q = q.order_by(Rating.created_at.desc())

    reviews = q.offset((active_page - 1) * PAGE_SIZE).limit(PAGE_SIZE).all()

    all_comments = (
        db.query(Comment)
        .filter(Comment.doi == doi, Comment.ai_flagged == False)  # noqa: E712
        .order_by(Comment.created_at.asc()).all()
    )
    comment_map: dict[int, list] = {}
    reply_map: dict[int, list] = {}
    for c in all_comments:
        if c.parent_id:
            reply_map.setdefault(c.parent_id, []).append(c)
        elif c.rating_id:
            comment_map.setdefault(c.rating_id, []).append(c)

    comment_ids = [c.id for c in all_comments]
    comment_like_rows = (
        db.query(CommentLike.comment_id, func.count(CommentLike.id))
        .filter(CommentLike.comment_id.in_(comment_ids))
        .group_by(CommentLike.comment_id)
        .all()
    ) if comment_ids else []
    comment_like_counts = {cid: cnt for cid, cnt in comment_like_rows}

    orcid_id = request.session.get("orcid_id")
    user_comment_likes: set[int] = set()
    if orcid_id and comment_ids:
        user_comment_likes = {
            row.comment_id for row in
            db.query(CommentLike.comment_id)
            .filter(CommentLike.orcid_id == orcid_id, CommentLike.comment_id.in_(comment_ids))
            .all()
        }

    user_already_rated = (
        db.query(Rating).filter(Rating.doi == doi, Rating.orcid_id == orcid_id,
                                Rating.scoring_mode == "classic").first()
        if orcid_id else None
    )

    try:
        authors = json.loads(paper.authors)
    except Exception:
        authors = [paper.authors]

    rating_ids = [r.id for r in reviews]
    like_rows = (
        db.query(Like.rating_id, func.count(Like.id))
        .filter(Like.rating_id.in_(rating_ids)).group_by(Like.rating_id).all()
    ) if rating_ids else []
    like_counts = {rid: cnt for rid, cnt in like_rows}
    user_likes: set[int] = set()
    if orcid_id and rating_ids:
        user_likes = {
            row.rating_id for row in
            db.query(Like.rating_id)
            .filter(Like.orcid_id == orcid_id, Like.rating_id.in_(rating_ids)).all()
        }

    _ref_texts_c = (
        [r.reproducibility_observation for r in reviews]
        + [r.scope_observation for r in reviews]
        + [r.modification_details for r in reviews]
        + [c.content for c in all_comments]
    )
    _ref_dois_c = collect_doi_refs(_ref_texts_c) - {doi}
    papers_by_doi: dict = {}
    if _ref_dois_c:
        for _p in db.query(Paper).filter(Paper.doi.in_(_ref_dois_c)).all():
            papers_by_doi[_p.doi] = _p
        for _missing_doi in _ref_dois_c - papers_by_doi.keys():
            try:
                _meta = await fetch_paper_metadata(_missing_doi)
                if _meta:
                    _new_p = Paper(**_meta)
                    db.add(_new_p)
                    db.commit()
                    db.refresh(_new_p)
                    papers_by_doi[_missing_doi] = _new_p
            except Exception:
                db.rollback()

    saved_entry = (
        db.query(SavedPaper).filter(
            SavedPaper.orcid_id == orcid_id,
            SavedPaper.doi == doi,
        ).first()
        if orcid_id else None
    )
    user_collections_flat = _collections_flat(orcid_id, db) if orcid_id else []

    return templates.TemplateResponse(paper_classic_tpl(request), {
        "request": request,
        "paper": paper,
        "authors": authors,
        "classic_scores": classic_scores,
        "reviews": reviews,
        "comment_map": comment_map,
        "reply_map": reply_map,
        "comment_like_counts": comment_like_counts,
        "user_comment_likes": user_comment_likes,
        "like_counts": like_counts,
        "user_likes": user_likes,
        "total_count": total_count,
        "total_pages": total_pages,
        "active_page": active_page,
        "active_sort": active_sort,
        "user_name": request.session.get("user_name"),
        "orcid_id": orcid_id,
        "user_already_rated": user_already_rated,
        "saved_entry": saved_entry,
        "user_collections_flat": user_collections_flat,
        "papers_by_doi": papers_by_doi,
        "prompts": prompts,
        "site_version": "classic",
        "switch_urls": {"standard": f"/design-archive/standard/paper/{doi}", "classic": f"/classic/paper/{doi}", "new_design": f"/paper/{doi}"},
    })


@router.post("/classic/paper/{doi:path}/rate")
async def classic_submit_rating(
    doi: str, request: Request, db: Session = Depends(get_db),
    reproducibility_score: str = Form(""),
    reproducibility_observation: str = Form(""),
    generalisability_score: str = Form(""),
    scope_observation: str = Form(""),
    coi_confirmed: str = Form(""),
):
    orcid_id = request.session.get("orcid_id")
    if not orcid_id:
        return RedirectResponse(f"/auth/guest-setup?next=/classic/paper/{doi}", status_code=303)
    if coi_confirmed != "on":
        raise HTTPException(
            status_code=422, detail="Conflict of interest confirmation required")

    existing = db.query(Rating).filter(
        Rating.doi == doi, Rating.orcid_id == orcid_id, Rating.scoring_mode == "classic"
    ).first()
    if existing:
        raise HTTPException(
            status_code=409, detail="You have already rated this paper in Classic mode")

    paper = db.get(Paper, doi)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    repro_int = int(reproducibility_score) if reproducibility_score else None
    ext_int = int(generalisability_score) if generalisability_score else None
    if repro_int is not None and not (1 <= repro_int <= 5):
        raise HTTPException(
            status_code=422, detail="Reproducibility score must be 1–5")
    if ext_int is not None and not (1 <= ext_int <= 5):
        raise HTTPException(
            status_code=422, detail="Extension score must be 1–5")

    db.add(Rating(
        doi=doi,
        orcid_id=orcid_id,
        scoring_mode="classic",
        reproducibility_score=repro_int,
        reproducibility_observation=reproducibility_observation.strip()[
            :1000] or None,
        generalisability_score=ext_int,
        scope_observation=scope_observation.strip()[:1000] or None,
    ))
    db.commit()
    return RedirectResponse(f"/classic/paper/{doi}", status_code=303)


# ── Standard: edit / delete ──────────────────────────────────────────────────

@router.post("/design-archive/standard/paper/{doi:path}/ratings/{rating_id}/delete")
async def delete_rating(doi: str, rating_id: int, request: Request, db: Session = Depends(get_db)):
    orcid_id = request.session.get("orcid_id")
    if not orcid_id:
        raise HTTPException(status_code=403, detail="Not authenticated")
    r = _own_rating_or_404(rating_id, orcid_id, db)
    _delete_rating(r, db)
    return RedirectResponse(f"/design-archive/standard/paper/{doi}", status_code=303)


@router.post("/design-archive/standard/paper/{doi:path}/ratings/{rating_id}/edit")
async def edit_rating_submit(
    doi: str, rating_id: int, request: Request, db: Session = Depends(get_db),
    outcome: str = Form(""),
    reproducibility_observation: str = Form(""),
    scope_level: str = Form(""),
    scope_observation: str = Form(""),
    modification_details: str = Form(""),
):
    orcid_id = request.session.get("orcid_id")
    if not orcid_id:
        raise HTTPException(status_code=403)
    r = _own_rating_or_404(rating_id, orcid_id, db)
    if outcome:
        r.outcome = outcome
    r.reproducibility_observation = reproducibility_observation.strip()[
        :1000] or None
    r.scope_level = scope_level or None
    r.scope_observation = scope_observation.strip()[:1000] or None
    r.modification_details = modification_details.strip()[:1000] or None
    r.updated_at = datetime.now(timezone.utc)
    db.commit()
    return RedirectResponse(f"/design-archive/standard/paper/{doi}#review-{rating_id}", status_code=303)


# ── Classic: edit / delete ───────────────────────────────────────────────────

@router.post("/classic/paper/{doi:path}/ratings/{rating_id}/delete")
async def classic_delete_rating(doi: str, rating_id: int, request: Request, db: Session = Depends(get_db)):
    orcid_id = request.session.get("orcid_id")
    if not orcid_id:
        raise HTTPException(status_code=403, detail="Not authenticated")
    r = _own_rating_or_404(rating_id, orcid_id, db)
    _delete_rating(r, db)
    return RedirectResponse(f"/classic/paper/{doi}", status_code=303)


@router.post("/classic/paper/{doi:path}/ratings/{rating_id}/edit")
async def classic_edit_rating_submit(
    doi: str, rating_id: int, request: Request, db: Session = Depends(get_db),
    reproducibility_score: str = Form(""),
    reproducibility_observation: str = Form(""),
    generalisability_score: str = Form(""),
    scope_observation: str = Form(""),
):
    orcid_id = request.session.get("orcid_id")
    if not orcid_id:
        raise HTTPException(status_code=403)
    r = _own_rating_or_404(rating_id, orcid_id, db)
    repro_int = int(reproducibility_score) if reproducibility_score else None
    ext_int = int(generalisability_score) if generalisability_score else None
    if repro_int is not None and not (1 <= repro_int <= 5):
        raise HTTPException(status_code=422)
    if ext_int is not None and not (1 <= ext_int <= 5):
        raise HTTPException(status_code=422)
    r.reproducibility_score = repro_int
    r.reproducibility_observation = reproducibility_observation.strip()[
        :1000] or None
    r.generalisability_score = ext_int
    r.scope_observation = scope_observation.strip()[:1000] or None
    r.updated_at = datetime.now(timezone.utc)
    db.commit()
    return RedirectResponse(f"/classic/paper/{doi}#review-{rating_id}", status_code=303)


@router.get("/about", response_class=HTMLResponse)
async def about(request: Request):
    return templates.TemplateResponse("about.html", {
        "request": request,
        "user_name": request.session.get("user_name"),
        "orcid_id": request.session.get("orcid_id"),
        "site_version": "standard",
        "switch_urls": {"standard": "/", "classic": "/classic/", "new_design": "/nd/"},
    })


# ── ChemRepro rating mode ─────────────────────────────────────────────────────

def _nd_scoring_context() -> dict:
    return {
        "nd_star_labels": ND_STAR_LABELS,
        "nd_star_order": ND_STAR_ORDER,
        "nd_star_colors": ND_STAR_COLORS,
        "nd_failure_context_labels": ND_FAILURE_CONTEXT_LABELS,
    }


@router.get("/", response_class=HTMLResponse)
@router.get("/nd/", response_class=HTMLResponse)
@router.get("/nd", response_class=HTMLResponse)
async def nd_index(request: Request, db: Session = Depends(get_db)):
    orcid_id = request.session.get("orcid_id")

    def _enrich_nd(papers):
        return [
            {"paper": p, "display_authors": _format_authors(
                p.authors), **_get_nd_paper_scores(p.doi, db)}
            for p in papers
        ]

    last_rated_sq = (
        db.query(Rating.doi, func.max(Rating.created_at).label("last_rated"))
        .filter(Rating.scoring_mode.in_(["new_design", "standard"]))
        .group_by(Rating.doi)
        .subquery()
    )

    my_papers = []
    if orcid_id:
        my_dois_sq = (
            db.query(Rating.doi)
            .filter(Rating.orcid_id == orcid_id, Rating.scoring_mode.in_(["new_design", "standard"]))
            .subquery()
        )
        my_papers = _enrich_nd(
            db.query(Paper)
            .join(my_dois_sq, Paper.doi == my_dois_sq.c.doi)
            .join(last_rated_sq, Paper.doi == last_rated_sq.c.doi)
            .order_by(last_rated_sq.c.last_rated.desc())
            .limit(5)
            .all()
        )

    my_doi_set = {e["paper"].doi for e in my_papers}
    community_candidates = (
        db.query(Paper)
        .join(last_rated_sq, Paper.doi == last_rated_sq.c.doi)
        .order_by(last_rated_sq.c.last_rated.desc())
        .limit(10 + len(my_doi_set))
        .all()
    )
    community_papers = _enrich_nd(
        [p for p in community_candidates if p.doi not in my_doi_set][:10])

    return templates.TemplateResponse("index_nd.html", {
        "request": request,
        "my_papers": my_papers,
        "community_papers": community_papers,
        "user_name": request.session.get("user_name"),
        "orcid_id": orcid_id,
        "site_version": "new_design",
        "switch_urls": {"standard": "/", "classic": "/classic/", "new_design": "/nd/"},
        **_dev_context(),
        **_nd_scoring_context(),
    })


@router.get("/paper/{doi:path}/ratings/{rating_id}/edit", response_class=HTMLResponse)
async def nd_edit_rating_page(doi: str, rating_id: int, request: Request, db: Session = Depends(get_db)):
    orcid_id = request.session.get("orcid_id")
    if not orcid_id:
        return RedirectResponse(f"/auth/guest-setup?next=/paper/{doi}", status_code=303)
    r = _own_rating_or_404(rating_id, orcid_id, db)
    paper = db.get(Paper, doi)
    if not paper:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse("edit_rating_nd.html", {
        "request": request,
        "paper": paper,
        "rating": r,
        "user_name": request.session.get("user_name"),
        "orcid_id": orcid_id,
        "site_version": "new_design",
        "switch_urls": {"standard": "/", "classic": "/classic/", "new_design": "/nd/"},
        **_nd_scoring_context(),
    })



@router.get("/paper/{doi:path}", response_class=HTMLResponse)
async def nd_paper_page(doi: str, request: Request, db: Session = Depends(get_db)):
    paper = db.get(Paper, doi)
    if not paper:
        meta = await fetch_paper_metadata(doi)
        if not meta:
            raise HTTPException(status_code=404, detail="Paper not found")
        paper = Paper(**meta)
        db.add(paper)
        db.commit()
        db.refresh(paper)
    elif paper.abstract is None:
        meta = await fetch_paper_metadata(doi)
        if meta and meta.get("abstract"):
            paper.abstract = meta["abstract"]
            db.commit()

    nd_scores = _get_nd_paper_scores(doi, db)

    PAGE_SIZE = 25
    active_star = request.query_params.get("star",  "")
    active_ctx = request.query_params.get("ctx",   "")
    active_sort = request.query_params.get("sort",  "newest")
    try:
        active_page = max(1, int(request.query_params.get("page", 1)))
    except ValueError:
        active_page = 1

    q = db.query(Rating).filter(
        Rating.doi == doi, Rating.scoring_mode == "new_design", Rating.ai_flagged == False  # noqa: E712
    )
    if active_star:
        try:
            q = q.filter(Rating.nd_star == int(active_star))
        except ValueError:
            pass
    if active_ctx:
        q = q.filter(Rating.nd_failure_context == active_ctx)

    total_count = q.count()
    total_pages = max(1, (total_count + PAGE_SIZE - 1) // PAGE_SIZE)
    active_page = min(active_page, total_pages)

    if active_sort == "oldest":
        q = q.order_by(Rating.created_at.asc())
    elif active_sort == "highest":
        q = q.order_by(Rating.nd_star.desc().nullslast(),
                       Rating.created_at.desc())
    elif active_sort == "lowest":
        q = q.order_by(Rating.nd_star.asc().nullsfirst(),
                       Rating.created_at.desc())
    elif active_sort == "most_liked":
        like_sq = (
            select(Like.rating_id, func.count(Like.id).label("lc"))
            .group_by(Like.rating_id)
            .subquery()
        )
        q = q.outerjoin(like_sq, Rating.id == like_sq.c.rating_id)
        q = q.order_by(func.coalesce(like_sq.c.lc, 0).desc(),
                       Rating.created_at.desc())
    else:
        q = q.order_by(Rating.created_at.desc())

    reviews = q.offset((active_page - 1) * PAGE_SIZE).limit(PAGE_SIZE).all()

    all_comments = (
        db.query(Comment)
        .filter(Comment.doi == doi, Comment.ai_flagged == False)  # noqa: E712
        .order_by(Comment.created_at.asc())
        .all()
    )
    comment_map: dict[int, list] = {}
    reply_map: dict[int, list] = {}
    for c in all_comments:
        if c.parent_id:
            reply_map.setdefault(c.parent_id, []).append(c)
        elif c.rating_id:
            comment_map.setdefault(c.rating_id, []).append(c)

    comment_ids = [c.id for c in all_comments]
    comment_like_rows = (
        db.query(CommentLike.comment_id, func.count(CommentLike.id))
        .filter(CommentLike.comment_id.in_(comment_ids))
        .group_by(CommentLike.comment_id)
        .all()
    ) if comment_ids else []
    comment_like_counts = {cid: cnt for cid, cnt in comment_like_rows}

    orcid_id = request.session.get("orcid_id")
    user_comment_likes: set[int] = set()
    if orcid_id and comment_ids:
        user_comment_likes = {
            row.comment_id for row in
            db.query(CommentLike.comment_id)
            .filter(CommentLike.orcid_id == orcid_id, CommentLike.comment_id.in_(comment_ids))
            .all()
        }

    user_already_rated = (
        db.query(Rating).filter(
            Rating.doi == doi, Rating.orcid_id == orcid_id, Rating.scoring_mode == "new_design"
        ).first()
        if orcid_id else None
    )

    try:
        authors = json.loads(paper.authors)
    except Exception:
        authors = [paper.authors]

    # Also fetch standard-mode reviews for this paper (shown in a legacy section)
    standard_reviews = (
        db.query(Rating)
        .filter(Rating.doi == doi, Rating.scoring_mode == "standard", Rating.ai_flagged == False)  # noqa: E712
        .order_by(Rating.created_at.desc())
        .all()
    )

    all_rating_ids = [r.id for r in reviews] + [r.id for r in standard_reviews]
    rating_ids = [r.id for r in reviews]
    like_rows = (
        db.query(Like.rating_id, func.count(Like.id))
        .filter(Like.rating_id.in_(all_rating_ids))
        .group_by(Like.rating_id)
        .all()
    ) if all_rating_ids else []
    like_counts = {rid: cnt for rid, cnt in like_rows}

    user_likes: set[int] = set()
    if orcid_id and all_rating_ids:
        user_likes = {
            row.rating_id for row in
            db.query(Like.rating_id)
            .filter(Like.orcid_id == orcid_id, Like.rating_id.in_(all_rating_ids))
            .all()
        }

    _ref_texts = (
        [r.reproducibility_observation for r in reviews]
        + [r.reproducibility_observation for r in standard_reviews]
        + [r.scope_observation for r in standard_reviews if r.scope_observation]
        + [c.content for c in all_comments]
    )
    _ref_dois = collect_doi_refs(_ref_texts) - {doi}
    papers_by_doi: dict = {}
    if _ref_dois:
        for _p in db.query(Paper).filter(Paper.doi.in_(_ref_dois)).all():
            papers_by_doi[_p.doi] = _p
        for _missing_doi in _ref_dois - papers_by_doi.keys():
            try:
                _meta = await fetch_paper_metadata(_missing_doi)
                if _meta:
                    _new_p = Paper(**_meta)
                    db.add(_new_p)
                    db.commit()
                    db.refresh(_new_p)
                    papers_by_doi[_missing_doi] = _new_p
            except Exception:
                db.rollback()

    saved_entry = (
        db.query(SavedPaper).filter(
            SavedPaper.orcid_id == orcid_id,
            SavedPaper.doi == doi,
        ).first()
        if orcid_id else None
    )
    user_collections_flat = _collections_flat(orcid_id, db) if orcid_id else []

    return templates.TemplateResponse("paper_nd.html", {
        "request": request,
        "paper": paper,
        "authors": authors,
        "nd_scores": nd_scores,
        "reviews": reviews,
        "standard_reviews": standard_reviews,
        "outcome_labels": OUTCOME_LABELS,
        "outcome_scores": OUTCOME_SCORES,
        "comment_map": comment_map,
        "reply_map": reply_map,
        "comment_like_counts": comment_like_counts,
        "user_comment_likes": user_comment_likes,
        "like_counts": like_counts,
        "user_likes": user_likes,
        "total_count": total_count,
        "total_pages": total_pages,
        "active_page": active_page,
        "active_star": active_star,
        "active_ctx": active_ctx,
        "active_sort": active_sort,
        "user_name": request.session.get("user_name"),
        "orcid_id": orcid_id,
        "user_already_rated": user_already_rated,
        "saved_entry": saved_entry,
        "user_collections_flat": user_collections_flat,
        "papers_by_doi": papers_by_doi,
        "site_version": "new_design",
        "switch_urls": {"standard": f"/design-archive/standard/paper/{doi}", "classic": f"/classic/paper/{doi}", "new_design": f"/paper/{doi}"},
        **_nd_scoring_context(),
    })


@router.post("/paper/{doi:path}/comment")
async def nd_submit_comment(
    doi: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    rating_id: int = Form(...),
    content: str = Form(""),
):
    orcid_id = request.session.get("orcid_id")
    if not orcid_id:
        return RedirectResponse(f"/auth/guest-setup?next=/paper/{doi}", status_code=303)
    if not content.strip():
        return RedirectResponse(f"/paper/{doi}", status_code=303)
    if not _is_clean(content):
        raise HTTPException(
            status_code=422, detail="Content contains prohibited language.")
    paper = db.get(Paper, doi)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    rating = db.get(Rating, rating_id)
    comment = Comment(doi=doi, rating_id=rating_id,
                      orcid_id=orcid_id, content=content.strip()[:2000])
    db.add(comment)
    if rating:
        _maybe_notify(db, notif_type="comment", actor_orcid_id=orcid_id,
                      actor_name=request.session.get("user_name", "Someone"), rating=rating, paper=paper)
    _notify_paper_subscribers(db, doi=doi, paper=paper, notif_type="new_comment",
                              actor_name=request.session.get(
                                  "user_name", "Someone"),
                              rating_id=rating_id, exclude_orcid=orcid_id)
    db.commit()
    background_tasks.add_task(moderate_comment_bg, comment.id)
    return RedirectResponse(f"/paper/{doi}#review-{rating_id}", status_code=303)


@router.post("/paper/{doi:path}/comment/{parent_id}/reply")
async def nd_submit_reply(
    doi: str, parent_id: int, request: Request,
    background_tasks: BackgroundTasks, db: Session = Depends(get_db),
    content: str = Form(""),
):
    orcid_id = request.session.get("orcid_id")
    if not orcid_id:
        return RedirectResponse(f"/auth/guest-setup?next=/paper/{doi}", status_code=303)
    content = content.strip()[:2000]
    if not content:
        return RedirectResponse(f"/paper/{doi}", status_code=303)
    if not _is_clean(content):
        raise HTTPException(
            status_code=422, detail="Content contains prohibited language.")
    parent = db.get(Comment, parent_id)
    if not parent:
        raise HTTPException(status_code=404, detail="Comment not found")
    reply = Comment(doi=doi, rating_id=parent.rating_id,
                    parent_id=parent_id, orcid_id=orcid_id, content=content)
    db.add(reply)
    if parent.orcid_id != orcid_id:
        paper = db.get(Paper, doi)
        if paper:
            db.add(Notification(
                recipient_orcid_id=parent.orcid_id, type="comment_reply",
                actor_name=request.session.get("user_name", "Someone"),
                rating_id=parent.rating_id or 0, doi=doi, paper_title=(paper.title or "")[:200],
            ))
    db.commit()
    background_tasks.add_task(moderate_comment_bg, reply.id)
    anchor = f"#review-{parent.rating_id}" if parent.rating_id else ""
    return RedirectResponse(f"/paper/{doi}{anchor}", status_code=303)


@router.post("/paper/{doi:path}/ratings/{rating_id}/like")
async def nd_toggle_like(doi: str, rating_id: int, request: Request, db: Session = Depends(get_db)):
    wants_json = "application/json" in request.headers.get("Accept", "")
    orcid_id = request.session.get("orcid_id")
    if not orcid_id:
        if wants_json:
            return JSONResponse({"error": "not authenticated"}, status_code=401)
        return RedirectResponse(f"/auth/guest-setup?next={request.url.path}", status_code=303)
    existing = db.query(Like).filter(
        Like.rating_id == rating_id, Like.orcid_id == orcid_id).first()
    if existing:
        db.delete(existing)
        liked = False
    else:
        db.add(Like(rating_id=rating_id, orcid_id=orcid_id))
        liked = True
        rating = db.get(Rating, rating_id)
        if rating:
            paper = db.get(Paper, doi)
            if paper:
                _maybe_notify(db, notif_type="like", actor_orcid_id=orcid_id,
                              actor_name=request.session.get("user_name", "Someone"), rating=rating, paper=paper)
    db.commit()
    count = db.query(func.count(Like.id)).filter(
        Like.rating_id == rating_id).scalar()
    if wants_json:
        return JSONResponse({"liked": liked, "count": count})
    return RedirectResponse(f"/paper/{doi}#review-{rating_id}", status_code=303)


@router.post("/paper/{doi:path}/comment/{comment_id}/like")
async def nd_toggle_comment_like(doi: str, comment_id: int, request: Request, db: Session = Depends(get_db)):
    wants_json = "application/json" in request.headers.get("Accept", "")
    orcid_id = request.session.get("orcid_id")
    if not orcid_id:
        return JSONResponse({"error": "not authenticated"}, status_code=401)
    existing = db.query(CommentLike).filter(
        CommentLike.comment_id == comment_id, CommentLike.orcid_id == orcid_id
    ).first()
    if existing:
        db.delete(existing)
        liked = False
    else:
        db.add(CommentLike(comment_id=comment_id, orcid_id=orcid_id))
        liked = True
        comment = db.get(Comment, comment_id)
        if comment and comment.orcid_id != orcid_id:
            paper = db.get(Paper, doi)
            if paper:
                db.add(Notification(
                    recipient_orcid_id=comment.orcid_id, type="comment_like",
                    actor_name=request.session.get("user_name", "Someone"),
                    rating_id=comment.rating_id or 0, doi=doi, paper_title=(paper.title or "")[:200],
                ))
    db.commit()
    count = db.query(func.count(CommentLike.id)).filter(
        CommentLike.comment_id == comment_id).scalar()
    if wants_json:
        return JSONResponse({"liked": liked, "count": count})
    return RedirectResponse(f"/paper/{doi}", status_code=303)


@router.post("/paper/{doi:path}/rate")
async def nd_submit_rating(
    doi: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    nd_star: str = Form(""),
    nd_failure_context: str = Form(""),
    reproducibility_observation: str = Form(""),
    coi_confirmed: str = Form(""),
):
    orcid_id = request.session.get("orcid_id")
    if not orcid_id:
        return RedirectResponse(f"/auth/guest-setup?next=/paper/{doi}", status_code=303)

    paper = db.get(Paper, doi)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    if coi_confirmed != "on":
        raise HTTPException(
            status_code=422, detail="You must confirm no conflict of interest")
    if not _is_clean(reproducibility_observation):
        raise HTTPException(
            status_code=422, detail="Content contains prohibited language.")

    star_int = int(nd_star) if nd_star else None
    if star_int is None or not (1 <= star_int <= 5):
        raise HTTPException(
            status_code=422, detail="Star rating 1–5 is required")

    ctx = nd_failure_context.strip() or None
    if star_int == 1 and ctx not in ("original_tested", "extension_only"):
        raise HTTPException(
            status_code=422, detail="Failure context is required for a 1-star review")
    if star_int != 1:
        ctx = None

    existing = db.query(Rating).filter(
        Rating.doi == doi, Rating.orcid_id == orcid_id, Rating.scoring_mode == "new_design"
    ).first()
    if existing:
        raise HTTPException(
            status_code=409, detail="You have already rated this paper")

    rating = Rating(
        doi=doi,
        orcid_id=orcid_id,
        scoring_mode="new_design",
        nd_star=star_int,
        nd_failure_context=ctx,
        reproducibility_observation=reproducibility_observation.strip()[
            :1000] or None,
    )
    db.add(rating)
    db.flush()
    _notify_paper_subscribers(
        db, doi=doi, paper=paper, notif_type="new_review",
        actor_name=request.session.get("user_name", "Someone"),
        rating_id=rating.id, exclude_orcid=orcid_id,
    )
    db.commit()
    base_url = str(request.base_url).rstrip("/")
    background_tasks.add_task(
        notify_author_if_possible, doi, paper.title or "", rating.id, db, base_url)
    background_tasks.add_task(moderate_rating_bg, rating.id)
    return RedirectResponse(f"/paper/{doi}", status_code=303)


@router.post("/paper/{doi:path}/ratings/{rating_id}/delete")
async def nd_delete_rating(doi: str, rating_id: int, request: Request, db: Session = Depends(get_db)):
    orcid_id = request.session.get("orcid_id")
    if not orcid_id:
        raise HTTPException(status_code=403, detail="Not authenticated")
    r = _own_rating_or_404(rating_id, orcid_id, db)
    _delete_rating(r, db)
    return RedirectResponse(f"/paper/{doi}", status_code=303)



@router.post("/paper/{doi:path}/ratings/{rating_id}/edit")
async def nd_edit_rating_submit(
    doi: str, rating_id: int, request: Request, db: Session = Depends(get_db),
    nd_star: str = Form(""),
    nd_failure_context: str = Form(""),
    reproducibility_observation: str = Form(""),
):
    orcid_id = request.session.get("orcid_id")
    if not orcid_id:
        raise HTTPException(status_code=403)
    r = _own_rating_or_404(rating_id, orcid_id, db)

    star_int = int(nd_star) if nd_star else None
    if star_int is None or not (1 <= star_int <= 5):
        raise HTTPException(
            status_code=422, detail="Star rating 1–5 is required")

    ctx = nd_failure_context.strip() or None
    if star_int == 1 and ctx not in ("original_tested", "extension_only"):
        raise HTTPException(
            status_code=422, detail="Failure context is required for a 1-star review")
    if star_int != 1:
        ctx = None

    r.nd_star = star_int
    r.nd_failure_context = ctx
    r.reproducibility_observation = reproducibility_observation.strip()[
        :1000] or None
    r.updated_at = datetime.now(timezone.utc)
    db.commit()
    return RedirectResponse(f"/paper/{doi}#review-{rating_id}", status_code=303)


@router.get("/privacy", response_class=HTMLResponse)
async def privacy(request: Request):
    return templates.TemplateResponse("privacy.html", {
        "request": request,
        "user_name": request.session.get("user_name"),
        "orcid_id": request.session.get("orcid_id"),
        "site_version": "standard",
        "switch_urls": {"standard": "/", "classic": "/classic/"},
    })


@router.get("/terms", response_class=HTMLResponse)
async def terms(request: Request):
    return templates.TemplateResponse("terms.html", {
        "request": request,
        "user_name": request.session.get("user_name"),
        "orcid_id": request.session.get("orcid_id"),
        "site_version": "standard",
        "switch_urls": {"standard": "/", "classic": "/classic/"},
    })


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

    reviews = db.query(Rating).filter(Rating.doi == DEMO_DOI).order_by(
        Rating.created_at.desc()).all()
    scored = [OUTCOME_SCORES[r.outcome]
              for r in reviews if r.outcome in OUTCOME_SCORES]
    score_a = round(sum(scored) / len(scored), 1) if scored else None
    breakdown = {}
    for r in reviews:
        if r.outcome:
            breakdown[r.outcome] = breakdown.get(r.outcome, 0) + 1
    distribution = [(o, OUTCOME_LABELS[o], breakdown.get(o, 0))
                    for o in OUTCOME_ORDER]

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
