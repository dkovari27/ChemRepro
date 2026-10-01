from datetime import datetime, timezone
from xml.sax.saxutils import escape

from fastapi import APIRouter, Depends, Request
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.rating import Rating
from app.utils.seo import site_base

router = APIRouter()

# Sitemap protocol limit per file; ChemRepro is far below it for now.
_MAX_URLS = 50000


@router.get("/robots.txt", response_class=PlainTextResponse)
async def robots_txt(request: Request):
    base = site_base(request)
    return (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /admin\n"
        "Disallow: /auth/\n"
        "Disallow: /api/\n"
        "Disallow: /library\n"
        "Disallow: /profile\n"
        "Disallow: /search\n"
        "Disallow: /classic\n"
        "Disallow: /design-archive/\n"
        "Disallow: /nd\n"
        f"\nSitemap: {base}/sitemap.xml\n"
    )


@router.get("/sitemap.xml")
async def sitemap_xml(request: Request, db: Session = Depends(get_db)):
    """Home, static pages, and every paper with at least one visible review.

    Papers without reviews are noindex, so they are not listed.
    """
    base = site_base(request)
    rows = (
        db.query(Rating.doi, func.max(Rating.created_at))
        .filter(Rating.scoring_mode == "new_design", Rating.ai_flagged == False)  # noqa: E712
        .group_by(Rating.doi)
        .order_by(func.max(Rating.created_at).desc())
        .limit(_MAX_URLS - 10)
        .all()
    )
    urls = [(f"{base}{p}", None) for p in ("/", "/about", "/privacy", "/terms")]
    for doi, last in rows:
        urls.append((f"{base}/paper/{doi}", last))

    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for loc, last in urls:
        entry = f"<url><loc>{escape(loc)}</loc>"
        if last:
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            entry += f"<lastmod>{last.date().isoformat()}</lastmod>"
        out.append(entry + "</url>")
    out.append("</urlset>")
    return Response("\n".join(out), media_type="application/xml")
