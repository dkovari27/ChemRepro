#!/usr/bin/env python3
"""Fix OrgSyn reviews: replace bare procedure DOI in observation text with sentence-case title.

Usage:
  python scripts/fix_orgsyn_titles.py --dry-run
  python scripts/fix_orgsyn_titles.py

  # Railway PostgreSQL:
  set DATABASE_URL=postgresql://...
  python scripts/fix_orgsyn_titles.py
"""
import io
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

from app.models.rating import Rating


def to_sentence_case(title: str) -> str:
    """Convert ALL CAPS (or any case) to sentence case, splitting on ': ' for subtitles."""
    if not title:
        return title
    parts = title.split(': ')
    result = []
    for part in parts:
        low = part.lower()
        result.append(low[0].upper() + low[1:] if low else low)
    return ': '.join(result)


def fetch_orgsyn_title(doi: str) -> str | None:
    """Fetch the procedure title for an OrgSyn DOI via CrossRef."""
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
    return re.sub(r"<[^>]+>", "", titles[0]).strip()


_ORGSYN_DOI_RE = re.compile(r"(10\.15227/orgsyn\.[^\s\"',;)\]]+)")


def fix_observation(obs: str, doi_to_title: dict) -> str:
    """Replace bare OrgSyn DOIs in observation text with quoted sentence-case titles."""
    def _replace(m: re.Match) -> str:
        raw = m.group(1)
        doi = raw.rstrip(".,;)")
        trailing = raw[len(doi):]
        title = doi_to_title.get(doi)
        if title:
            return f'"{to_sentence_case(title)}"{trailing}'
        return m.group(0)
    return _ORGSYN_DOI_RE.sub(_replace, obs)


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

    ratings = db.query(Rating).filter(
        Rating.reproducibility_observation.like("%10.15227/orgsyn%")
    ).all()

    if not ratings:
        print("No ratings found with bare OrgSyn DOIs. Nothing to do.")
        return

    print(f"Found {len(ratings)} rating(s) with bare OrgSyn DOIs.")

    all_dois: set[str] = set()
    for r in ratings:
        for m in _ORGSYN_DOI_RE.finditer(r.reproducibility_observation or ""):
            all_dois.add(m.group(1).rstrip(".,;)"))

    print(f"Unique OrgSyn DOIs to resolve: {sorted(all_dois)}\n")

    doi_to_title: dict[str, str] = {}
    for doi in sorted(all_dois):
        print(f"Fetching: {doi}")
        title = fetch_orgsyn_title(doi)
        if title:
            sc = to_sentence_case(title)
            print(f"  Raw:        {title}")
            print(f"  Sent. case: {sc}")
            doi_to_title[doi] = title
        print()

    if not doi_to_title:
        print("No titles resolved. Aborting.")
        return

    print("=" * 60)
    updated = 0
    for rating in ratings:
        old = rating.reproducibility_observation or ""
        new = fix_observation(old, doi_to_title)
        if new == old:
            print(f"  id={rating.id}: no change needed")
            continue
        print(f"\n  id={rating.id}:")
        print(f"    BEFORE: {old[:150]}")
        print(f"    AFTER:  {new[:150]}")
        if not dry_run:
            rating.reproducibility_observation = new
            updated += 1

    if not dry_run and updated:
        db.commit()
        print(f"\nCommitted {updated} update(s).")
    elif dry_run:
        print(f"\n(dry run: no changes written)")
    elif not updated:
        print("\nNo changes needed.")


if __name__ == "__main__":
    main()
