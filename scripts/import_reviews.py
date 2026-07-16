#!/usr/bin/env python3
"""
Bulk-import reviews from a JSON file into ChemRepro.

Usage:
  # Real user, dry run first:
  python scripts/import_reviews.py reviews.json --orcid 0009-0007-7610-9001 --dry-run

  # AI scraper profile (creates profile automatically if missing):
  python scripts/import_reviews.py reviews.json --ai-name OrgSyn --dry-run
  python scripts/import_reviews.py reviews.json --ai-name OrgSyn

  # Railway PostgreSQL:
  set DATABASE_URL=postgresql://postgres:PASSWORD@acela.proxy.rlwy.net:17700/railway
  python scripts/import_reviews.py reviews.json --ai-name OrgSyn

Required packages: httpx sqlalchemy psycopg (for PostgreSQL only)
"""
import argparse
import io
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.models.paper import Paper
from app.models.rating import Rating
from app.models.user import User

AI_CAREER_STAGE = "Data curation agent"


def make_session(db_url: str):
    url = db_url
    if url.startswith("sqlite:///./") or url == "sqlite:///./chemrepro.db":
        url = f"sqlite:///{PROJECT_ROOT / 'chemrepro.db'}"
    elif "postgres" in url:
        url = re.sub(r"^postgres(ql)?://", "postgresql+psycopg://", url)
    connect_args = {"check_same_thread": False} if "sqlite" in url else {}
    engine = create_engine(url, connect_args=connect_args)
    return sessionmaker(bind=engine)()


def ensure_ai_user(db, orcid_id: str, display_name: str, dry_run: bool) -> bool:
    """Create AI reviewer profile if it does not exist. Returns True if user exists after this call."""
    user = db.get(User, orcid_id)
    if user:
        print(f"  Profile {orcid_id!r} already exists (name={user.name!r})")
        return True
    print(f"  Profile {orcid_id!r} not found, creating...")
    if dry_run:
        print(f"  DRY RUN: would create profile name={display_name!r}, career_stage={AI_CAREER_STAGE!r}")
        return True
    db.add(User(
        orcid_id=orcid_id,
        name=display_name,
        nickname=display_name,
        career_stage=AI_CAREER_STAGE,
        career_stage_set=True,
        pledge_accepted=True,
        is_demo=False,
    ))
    db.commit()
    print(f"  Created: {display_name!r} (orcid_id={orcid_id!r}, career_stage={AI_CAREER_STAGE!r})")
    return True


def fetch_crossref(doi: str) -> dict | None:
    url = f"https://api.crossref.org/works/{doi}"
    try:
        r = httpx.get(url, headers={"User-Agent": "ChemRepro/1.0 (mailto:chemrepro@gmail.com)"}, timeout=12)
    except httpx.RequestError as exc:
        print(f"         CrossRef request failed: {exc}")
        return None
    if r.status_code != 200:
        print(f"         CrossRef returned HTTP {r.status_code}")
        return None
    data = r.json().get("message", {})

    title_parts = data.get("title", [])
    title = re.sub(r"<[^>]+>", "", title_parts[0] if title_parts else "").strip() or "Unknown title"

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

    return {"doi": doi, "title": title, "authors": authors, "journal": journal, "year": year, "abstract": abstract}


VALID_STARS = {1, 2, 3, 4, 5}
VALID_CONTEXTS = {"original_tested", "extension_only"}
STAR_LABEL = {1: "did not work", 2: "partial", 3: "reproduced", 4: "minor extension", 5: "major extension"}


def main():
    parser = argparse.ArgumentParser(description="Bulk-import ChemRepro reviews from JSON")
    parser.add_argument("file", help="Path to JSON reviews file")

    id_group = parser.add_mutually_exclusive_group(required=True)
    id_group.add_argument("--orcid", help="Real reviewer ORCID (e.g. 0009-0007-7610-9001)")
    id_group.add_argument("--ai-name", metavar="SCRAPER",
                          help="AI scraper name, e.g. OrgSyn: sets orcid_id=AI-OrgSyn, creates profile if missing")

    parser.add_argument("--career-stage", help="Override career_stage_snapshot for all rows")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing to DB")
    args = parser.parse_args()

    if args.ai_name:
        orcid_id = f"AI-{args.ai_name}"
        display_name = f"AI-{args.ai_name}"
        default_career = AI_CAREER_STAGE
    else:
        orcid_id = args.orcid
        display_name = None
        default_career = None

    db_url = os.environ.get("DATABASE_URL", "sqlite:///./chemrepro.db")
    db = make_session(db_url)

    print(f"\n{'='*55}")
    print(f"  Reviewer : {orcid_id}")
    print(f"  DB       : {db_url[:65]}{'...' if len(db_url) > 65 else ''}")
    print(f"  Mode     : {'DRY RUN' if args.dry_run else 'LIVE'}")
    print(f"{'='*55}\n")

    if args.ai_name:
        ensure_ai_user(db, orcid_id, display_name, args.dry_run)
        print()

    data = json.loads(Path(args.file).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        print("ERROR: JSON file must be a list of review objects.")
        sys.exit(1)

    print(f"Importing {len(data)} review(s)...\n")
    ok = skip = fail = 0

    for i, row in enumerate(data, 1):
        doi = (row.get("doi") or "").strip()
        if not doi:
            print(f"  [{i:>3}] SKIP: missing doi field")
            skip += 1
            continue

        nd_star = row.get("nd_star")
        if nd_star not in VALID_STARS:
            print(f"  [{i:>3}] {doi}: FAIL: nd_star must be 1-5, got {nd_star!r}")
            fail += 1
            continue

        ctx = row.get("nd_failure_context") or None
        if nd_star == 1:
            if ctx not in VALID_CONTEXTS:
                print(f"  [{i:>3}] {doi}: FAIL: nd_failure_context must be 'original_tested' or 'extension_only' for 1-star")
                fail += 1
                continue
        else:
            ctx = None

        career = args.career_stage or row.get("career_stage_snapshot") or default_career
        observation = ((row.get("reproducibility_observation") or "").strip()) or None

        paper = db.get(Paper, doi)
        if paper is None:
            print(f"  [{i:>3}] {doi}: not in DB, fetching from CrossRef...")
            meta = fetch_crossref(doi)
            if meta is None:
                print(f"  [{i:>3}] {doi}: FAIL: CrossRef lookup failed")
                fail += 1
                continue
            print(f"         title: {meta['title'][:75]}")
            if not args.dry_run:
                paper = Paper(**meta)
                db.add(paper)
                db.flush()
        else:
            print(f"  [{i:>3}] {doi}: {paper.title[:65]!r}")

        existing = db.query(Rating).filter(
            Rating.doi == doi,
            Rating.orcid_id == orcid_id,
            Rating.scoring_mode == "new_design",
        ).first()
        if existing:
            print(f"         SKIP: already reviewed (rating id={existing.id})")
            skip += 1
            continue

        print(f"         star={nd_star} ({STAR_LABEL.get(nd_star, '?')}){f', ctx={ctx}' if ctx else ''}")

        if not args.dry_run:
            rating = Rating(
                doi=doi,
                orcid_id=orcid_id,
                scoring_mode="new_design",
                nd_star=nd_star,
                nd_failure_context=ctx,
                reproducibility_observation=observation,
                career_stage_snapshot=career,
                is_demo=False,
            )
            db.add(rating)
            db.commit()
            print(f"         INSERTED id={rating.id}")
        else:
            print(f"         would insert")
        ok += 1

    print(f"\n{'='*55}")
    print(f"  Inserted : {ok}")
    print(f"  Skipped  : {skip}")
    print(f"  Failed   : {fail}")
    if args.dry_run:
        print("  (dry run: no changes made)")
    print()


if __name__ == "__main__":
    main()
