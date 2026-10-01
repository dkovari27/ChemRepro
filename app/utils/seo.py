"""SEO helpers: canonical URLs and robots policy for the base template.

Policy is an allowlist: only the pages named here are indexable by default.
Paper pages opt in themselves (see paper_nd.html) once they have reviews, so
auto-created lookups with no reviews never become thin duplicate content.
"""
from urllib.parse import quote

from fastapi import Request

from app.config import settings

INDEXABLE_PATHS = {"/", "/about", "/privacy", "/terms"}

# Legacy design variants whose canonical page lives elsewhere.
_CANONICAL_PREFIXES = (
    ("/classic/paper/", "/paper/"),
    ("/design-archive/standard/paper/", "/paper/"),
)
_CANONICAL_HOME = {"/classic", "/classic/", "/nd", "/nd/", "/design-archive/standard/"}


def site_base(request: Request) -> str:
    base = settings.SITE_URL.rstrip("/")
    if "127.0.0.1" in base or "localhost" in base:
        return str(request.base_url).rstrip("/")
    return base


def canonical_url(request: Request) -> str:
    path = request.url.path
    if path in _CANONICAL_HOME:
        path = "/"
    else:
        for old, new in _CANONICAL_PREFIXES:
            if path.startswith(old):
                path = new + path[len(old):]
                break
    return site_base(request) + quote(path, safe="/:()<>;@,-._~")


def default_robots(request: Request) -> str:
    if request.url.path in INDEXABLE_PATHS and not request.url.query:
        return "index,follow"
    return "noindex,follow"


def register_seo_globals(templates_instance) -> None:
    g = templates_instance.env.globals
    g["canonical_url"] = canonical_url
    g["default_robots"] = default_robots
    g["site_base"] = site_base


def paper_jsonld(request: Request, paper, authors: list, scores: dict) -> dict | None:
    """schema.org ScholarlyArticle (+ AggregateRating) for a reviewed paper.

    Returns None for papers with no reviews, which are served noindex.
    Individual reviews are deliberately left out of the markup.
    """
    if not scores.get("nd_rating_count"):
        return None
    ld = {
        "@context": "https://schema.org",
        "@type": "ScholarlyArticle",
        "name": paper.title,
        "url": f"{site_base(request)}/paper/{paper.doi}",
        "identifier": paper.doi,
        "sameAs": f"https://doi.org/{paper.doi}",
    }
    people = [{"@type": "Person", "name": a} for a in authors if a]
    if people:
        ld["author"] = people
    if paper.year:
        ld["datePublished"] = str(paper.year)
    if paper.journal:
        ld["isPartOf"] = {"@type": "Periodical", "name": paper.journal}
    scored = sum(c for star, c in scores.get("nd_star_dist", {}).items() if star is not None)
    if scores.get("nd_avg_star") and scored:
        ld["aggregateRating"] = {
            "@type": "AggregateRating",
            "ratingValue": scores["nd_avg_star"],
            "ratingCount": scored,
            "bestRating": 5,
            "worstRating": 1,
        }
    return ld
