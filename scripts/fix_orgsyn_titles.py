#!/usr/bin/env python3
"""Fix OrgSyn reviews: set "[[DOI]]" format in observations and upsert sentence-case paper titles.

Lookup is by target paper DOI (rating.doi), not by rating ID, so it works correctly
across both local SQLite and Railway PostgreSQL regardless of auto-increment differences.

Usage:
  python scripts/fix_orgsyn_titles.py --dry-run
  python scripts/fix_orgsyn_titles.py

  # Railway PostgreSQL:
  set DATABASE_URL=postgresql://...
  python scripts/fix_orgsyn_titles.py
"""
import io
import json
import os
import re
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.models.paper import Paper
from app.models.rating import Rating

# Maps target paper DOI (rating.doi) -> OrgSyn procedure DOI (10.15227/orgsyn.*)
# These are the 4 existing AI-OrgSyn reviews.
TARGET_TO_ORGSYN: dict[str, str] = {
    "10.1002/0471264180.os079.21":    "10.15227/orgsyn.079.0176",
    "10.1055/s-1981-29624":           "10.15227/orgsyn.078.0135",
    "10.1021/ol0156751":              "10.15227/orgsyn.081.0054",
    "10.1016/s0040-4039(02)00215-0":  "10.15227/orgsyn.081.0001",
}


def to_sentence_case(title: str) -> str:
    """Sentence case with chemistry notation preserved.

    - Capitalises first letter of each colon-separated part.
    - Single letters in parens stay uppercase: (E), (Z), (R), (S).
    - Single letters before hyphen or comma stay uppercase: N-, O-, N,N-.
    """
    if not title:
        return title
    parts = title.split(': ')
    result = []
    for part in parts:
        low = part.lower()
        result.append(low[0].upper() + low[1:] if low else low)
    text = ': '.join(result)
    text = re.sub(r'\(([a-z])\)', lambda m: '(' + m.group(1).upper() + ')', text)
    text = re.sub(r'\b([a-z])(?=[,\-])', lambda m: m.group(1).upper(), text)
    return text


def fetch_crossref_meta(doi: str) -> dict | None:
    url = f"https://api.crossref.org/works/{doi}"
    try:
        r = httpx.get(url, headers={"User-Agent": "ChemRepro/1.0 (mailto:chemrepro@gmail.com)"}, timeout=15)
    except httpx.RequestError as e:
        print(f"  CrossRef request failed: {e}")
        return None
    if r.status_code != 200:
        print(f"  CrossRef HTTP {r.status_code}")
        return None
    data = r.json().get("message", {})
    titles = data.get("title", [])
    if not titles:
        print(f"  No title")
        return None
    raw_title = re.sub(r"<[^>]+>", "", titles[0]).strip()
    authors = json.dumps([
        f"{a.get('given', '')} {a.get('family', '')}".strip()
        for a in data.get("author", []) if a.get("family")
    ])
    container = data.get("container-title", [])
    published = data.get("published-print") or data.get("published-online") or {}
    parts = published.get("date-parts", [[]])
    year = parts[0][0] if parts and parts[0] else None
    abstract_raw = data.get("abstract", "")
    abstract = re.sub(r"<[^>]+>", "", abstract_raw).strip() or None
    if abstract:
        abstract = re.sub(r"^Abstract\s*", "", abstract, flags=re.IGNORECASE).strip() or None
    return {
        "doi": doi, "raw_title": raw_title, "authors": authors,
        "journal": container[0] if container else None, "year": year, "abstract": abstract,
    }


_SOURCED_QUOTED_RE = re.compile(r'(Sourced from Org\. Synth\. )"([^"]*)"')
_ORGSYN_DOI_RE = re.compile(r"(10\.15227/orgsyn\.[^\s\"',;)\]\[]+)")


def fix_observation(obs: str, orgsyn_doi: str) -> str:
    """Replace bare OrgSyn DOI or quoted plain title with [[DOI]] format."""
    target = f'"[[{orgsyn_doi}]]"'
    if target in obs:
        return obs  # already correct
    if orgsyn_doi in obs:
        # Bare DOI: wrap and add surrounding quotes
        return obs.replace(orgsyn_doi, target)
    m = _SOURCED_QUOTED_RE.search(obs)
    if m:
        # Quoted plain-text title: replace with [[DOI]]
        return obs[:m.start()] + m.group(1) + target + obs[m.end():]
    return obs


def upsert_paper(db, meta: dict, title_sc: str, dry_run: bool) -> None:
    doi = meta["doi"]
    paper = db.get(Paper, doi)
    if paper is None:
        print(f"    PAPER: inserting {doi} with sentence-case title")
        if not dry_run:
            db.add(Paper(
                doi=doi, title=title_sc, authors=meta["authors"],
                journal=meta["journal"], year=meta["year"], abstract=meta["abstract"],
            ))
    elif paper.title != title_sc:
        print(f"    PAPER: updating title")
        print(f"      FROM: {paper.title[:80]}")
        print(f"      TO:   {title_sc[:80]}")
        if not dry_run:
            paper.title = title_sc
    else:
        print(f"    PAPER: title already correct")


def make_session(db_url: str):
    if db_url.startswith("sqlite:///./") or db_url == "sqlite:///./chemrepro.db":
        db_url = f"sqlite:///{PROJECT_ROOT / 'chemrepro.db'}"
    elif "postgres" in db_url:
        db_url = re.sub(r"^postgres(ql)?://", "postgresql+psycopg://", db_url)
    connect_args = {"check_same_thread": False} if "sqlite" in db_url else {}
    engine = create_engine(db_url, connect_args=connect_args)
    return sessionmaker(bind=engine)()


def main():
    dry_run = "--dry-run" in sys.argv
    db_url = os.environ.get("DATABASE_URL", "sqlite:///./chemrepro.db")
    db = make_session(db_url)

    print(f"\nDB  : {db_url[:65]}{'...' if len(db_url) > 65 else ''}")
    print(f"Mode: {'DRY RUN' if dry_run else 'LIVE'}\n")

    # Find AI-OrgSyn ratings whose target DOI we know
    found: list[tuple[Rating, str]] = []  # (rating, orgsyn_doi)
    for target_doi, orgsyn_doi in TARGET_TO_ORGSYN.items():
        rating = db.query(Rating).filter(
            Rating.doi == target_doi,
            Rating.orcid_id == "AI-OrgSyn",
        ).first()
        if rating:
            found.append((rating, orgsyn_doi))
        else:
            print(f"  WARNING: no AI-OrgSyn rating found for target {target_doi}")

    if not found:
        print("Nothing to fix.")
        return

    print(f"Found {len(found)} AI-OrgSyn rating(s) to process.\n")

    # Fetch CrossRef metadata for all unique OrgSyn DOIs
    all_orgsyn_dois = {orgsyn_doi for _, orgsyn_doi in found}
    doi_to_meta: dict[str, dict] = {}
    doi_to_sc: dict[str, str] = {}

    for doi in sorted(all_orgsyn_dois):
        print(f"CrossRef: {doi}")
        meta = fetch_crossref_meta(doi)
        if not meta:
            print(f"  FAILED\n")
            continue
        sc = to_sentence_case(meta["raw_title"])
        print(f"  Raw:        {meta['raw_title']}")
        print(f"  Sent. case: {sc}\n")
        doi_to_meta[doi] = meta
        doi_to_sc[doi] = sc

    print("=" * 60)
    updated = 0
    for rating, orgsyn_doi in found:
        if orgsyn_doi not in doi_to_sc:
            print(f"\n  rating id={rating.id} ({rating.doi}): CrossRef failed, skipping")
            continue

        sc = doi_to_sc[orgsyn_doi]
        old = rating.reproducibility_observation or ""
        new = fix_observation(old, orgsyn_doi)

        print(f"\n  rating id={rating.id}, target={rating.doi}")
        print(f"  orgsyn_doi: {orgsyn_doi}")
        if new != old:
            print(f"    OBS BEFORE: {old[:130]}")
            print(f"    OBS AFTER:  {new[:130]}")
            if not dry_run:
                rating.reproducibility_observation = new
                updated += 1
        else:
            print(f"    OBS: already correct")

        upsert_paper(db, doi_to_meta[orgsyn_doi], sc, dry_run)

    if not dry_run:
        db.commit()
        print(f"\nDone: {updated} observation(s) updated.")
    else:
        print(f"\n(dry run: no changes written)")


if __name__ == "__main__":
    main()
