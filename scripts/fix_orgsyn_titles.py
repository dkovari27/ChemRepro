#!/usr/bin/env python3
"""Fix OrgSyn reviews: replace bare procedure DOI (or previously-quoted title) in observation
text with "[[DOI]]" format, and upsert paper records with sentence-case titles.

This preserves the clickable link and mini-card behavior while showing a human-readable
sentence-case title instead of an ALL-CAPS title or a bare DOI.

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

# Explicit mapping for records that were previously fixed with quoted-title format
# (bare DOI was already removed; we need to know which DOI belongs to which rating)
EXPLICIT_PATCHES: dict[int, str] = {
    55: "10.15227/orgsyn.079.0176",
    56: "10.15227/orgsyn.078.0135",
    57: "10.15227/orgsyn.081.0054",
    58: "10.15227/orgsyn.081.0001",
}


def to_sentence_case(title: str) -> str:
    """Convert ALL CAPS (or any case) to sentence case.

    Splits on ': ' to handle subtitles. Preserves single-letter chemistry notation:
    - Letters in parentheses stay uppercase: (E), (Z), (R), (S)
    - Single letters before hyphen or comma stay uppercase: N-benzyl, N,N-dimethyl
    """
    if not title:
        return title
    parts = title.split(': ')
    result = []
    for part in parts:
        low = part.lower()
        result.append(low[0].upper() + low[1:] if low else low)
    text = ': '.join(result)
    # Uppercase single letters in parentheses: (e) -> (E), (z) -> (Z)
    text = re.sub(r'\(([a-z])\)', lambda m: '(' + m.group(1).upper() + ')', text)
    # Uppercase single letters before hyphen or comma (heteroatom/stereo prefixes):
    # n-benzyl -> N-benzyl, n,n-dimethyl -> N,N-dimethyl
    text = re.sub(r'\b([a-z])(?=[,\-])', lambda m: m.group(1).upper(), text)
    return text


def fetch_crossref_meta(doi: str) -> dict | None:
    """Fetch full metadata for a DOI from CrossRef."""
    url = f"https://api.crossref.org/works/{doi}"
    try:
        r = httpx.get(url, headers={"User-Agent": "ChemRepro/1.0 (mailto:chemrepro@gmail.com)"}, timeout=15)
    except httpx.RequestError as e:
        print(f"  CrossRef request failed for {doi}: {e}")
        return None
    if r.status_code != 200:
        print(f"  CrossRef returned HTTP {r.status_code} for {doi}")
        return None
    data = r.json().get("message", {})
    titles = data.get("title", [])
    if not titles:
        print(f"  No title found for {doi}")
        return None
    raw_title = re.sub(r"<[^>]+>", "", titles[0]).strip()
    authors = json.dumps([
        f"{a.get('given', '')} {a.get('family', '')}".strip()
        for a in data.get("author", []) if a.get("family")
    ])
    container = data.get("container-title", [])
    journal = container[0] if container else None
    published = data.get("published-print") or data.get("published-online") or {}
    parts = published.get("date-parts", [[]])
    year = parts[0][0] if parts and parts[0] else None
    abstract_raw = data.get("abstract", "")
    abstract = re.sub(r"<[^>]+>", "", abstract_raw).strip() or None
    if abstract:
        abstract = re.sub(r"^Abstract\s*", "", abstract, flags=re.IGNORECASE).strip() or None
    return {"doi": doi, "raw_title": raw_title, "authors": authors, "journal": journal,
            "year": year, "abstract": abstract}


_ORGSYN_DOI_RE = re.compile(r"(10\.15227/orgsyn\.[^\s\"',;)\]\[]+)")
_SOURCED_QUOTED_RE = re.compile(r'(Sourced from Org\. Synth\. )"([^"]+)"')
_SOURCED_BRACKET_RE = re.compile(r'(Sourced from Org\. Synth\. )"\[\[10\.15227/orgsyn\.[^\]]+\]\]"')


def fix_observation(obs: str, orgsyn_doi: str) -> str:
    """Replace bare OrgSyn DOI or previously-quoted title with [[DOI]] format."""
    # Case 1: observation already in correct "[[DOI]]" format — nothing to do
    if f'"[[{orgsyn_doi}]]"' in obs:
        return obs
    # Case 2: bare DOI in text (e.g. original format or Railway DB state)
    if orgsyn_doi in obs:
        return obs.replace(orgsyn_doi, f'"[[{orgsyn_doi}]]"')
    # Case 3: previously fixed with quoted plain-text title (local DB after first run)
    m = _SOURCED_QUOTED_RE.search(obs)
    if m:
        return obs[:m.start()] + m.group(1) + f'"[[{orgsyn_doi}]]"' + obs[m.end():]
    return obs


def upsert_paper(db, meta: dict, title_sc: str, dry_run: bool) -> None:
    """Insert or update paper record with sentence-case title."""
    doi = meta["doi"]
    paper = db.get(Paper, doi)
    if paper is None:
        print(f"  Paper {doi}: not in DB, inserting with sentence-case title")
        if not dry_run:
            db.add(Paper(
                doi=doi,
                title=title_sc,
                authors=meta["authors"],
                journal=meta["journal"],
                year=meta["year"],
                abstract=meta["abstract"],
            ))
    else:
        if paper.title != title_sc:
            print(f"  Paper {doi}: updating title")
            print(f"    FROM: {paper.title}")
            print(f"    TO:   {title_sc}")
            if not dry_run:
                paper.title = title_sc
        else:
            print(f"  Paper {doi}: title already correct")


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

    # Collect all rating → orgsyn_doi pairs to fix
    # Source A: explicit patches for records whose bare DOI was already removed
    patches: dict[int, str] = dict(EXPLICIT_PATCHES)

    # Source B: any ratings still containing a bare OrgSyn DOI
    bare_ratings = db.query(Rating).filter(
        Rating.reproducibility_observation.like("%10.15227/orgsyn%")
    ).all()
    for r in bare_ratings:
        for m in _ORGSYN_DOI_RE.finditer(r.reproducibility_observation or ""):
            doi = m.group(1).rstrip(".,;)")
            if r.id not in patches:
                patches[r.id] = doi

    if not patches:
        print("Nothing to fix.")
        return

    all_dois = set(patches.values())
    print(f"Ratings to fix: {sorted(patches.keys())}")
    print(f"OrgSyn DOIs:    {sorted(all_dois)}\n")

    # Fetch metadata for all unique OrgSyn DOIs
    doi_to_meta: dict[str, dict] = {}
    doi_to_sc: dict[str, str] = {}
    for doi in sorted(all_dois):
        print(f"CrossRef: {doi}")
        meta = fetch_crossref_meta(doi)
        if not meta:
            print(f"  FAILED — skipping\n")
            continue
        sc = to_sentence_case(meta["raw_title"])
        print(f"  Raw:        {meta['raw_title']}")
        print(f"  Sent. case: {sc}\n")
        doi_to_meta[doi] = meta
        doi_to_sc[doi] = sc

    if not doi_to_meta:
        print("No metadata resolved. Aborting.")
        return

    print("=" * 60)
    updated_ratings = 0
    for rating_id, orgsyn_doi in sorted(patches.items()):
        if orgsyn_doi not in doi_to_sc:
            print(f"  id={rating_id}: skipping (CrossRef failed for {orgsyn_doi})")
            continue

        rating = db.get(Rating, rating_id)
        if rating is None:
            print(f"  id={rating_id}: not found in DB")
            continue

        sc = doi_to_sc[orgsyn_doi]
        old = rating.reproducibility_observation or ""
        new = fix_observation(old, orgsyn_doi)

        print(f"\n  id={rating_id} ({orgsyn_doi}):")
        if new != old:
            print(f"    OBS BEFORE: {old[:140]}")
            print(f"    OBS AFTER:  {new[:140]}")
            if not dry_run:
                rating.reproducibility_observation = new
                updated_ratings += 1
        else:
            print(f"    OBS: no change needed")

        # Upsert paper with sentence-case title
        meta = doi_to_meta[orgsyn_doi]
        upsert_paper(db, meta, sc, dry_run)

    if not dry_run:
        db.commit()
        print(f"\nCommitted: {updated_ratings} observation(s) updated + paper records upserted.")
    else:
        print(f"\n(dry run: no changes written)")


if __name__ == "__main__":
    main()
