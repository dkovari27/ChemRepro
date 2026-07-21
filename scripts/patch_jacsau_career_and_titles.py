#!/usr/bin/env python3
"""
Patch Railway DB:
  1. Normalize whitespace in paper titles that have embedded \n from CrossRef JATS XML.
  2. Set career_stage_snapshot = 'Data curation agent' for all AI-JACSAU ratings.

Usage:
  set DATABASE_URL=postgresql://...
  python scripts/patch_jacsau_career_and_titles.py
  python scripts/patch_jacsau_career_and_titles.py --dry-run
"""
import argparse
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.models.paper import Paper
from app.models.rating import Rating


def normalise_title(t: str) -> str:
    return " ".join(t.split()).strip() if t else t


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    db_url = os.environ.get("DATABASE_URL", "sqlite:///./chemrepro.db")
    db_url = re.sub(r"^postgres(ql)?://", "postgresql+psycopg://", db_url)
    engine = create_engine(db_url)
    Session = sessionmaker(bind=engine)
    db = Session()

    mode = "DRY RUN" if args.dry_run else "LIVE"
    print(f"\n{'='*55}\n  DB  : {db_url[:65]}\n  Mode: {mode}\n{'='*55}\n")

    # 1. Fix paper titles with embedded newlines
    papers = db.query(Paper).filter(Paper.title.contains("\n")).all()
    print(f"Papers with \\n in title: {len(papers)}")
    for p in papers:
        fixed = normalise_title(p.title)
        print(f"  [{p.doi}]")
        print(f"    BEFORE: {p.title!r}")
        print(f"    AFTER : {fixed!r}")
        if not args.dry_run:
            p.title = fixed

    if not args.dry_run and papers:
        db.commit()
        print(f"  -> {len(papers)} title(s) updated\n")
    elif papers:
        print("  -> (dry run, no changes)\n")
    else:
        print("  -> none found\n")

    # 2. Fix career_stage_snapshot on all AI-JACSAU ratings
    ratings = db.query(Rating).filter(
        Rating.orcid_id == "AI-JACSAU",
        Rating.career_stage_snapshot != "Data curation agent",
    ).all()
    print(f"AI-JACSAU ratings with wrong career_stage_snapshot: {len(ratings)}")
    for r in ratings:
        print(f"  rating id={r.id}  doi={r.doi}  current={r.career_stage_snapshot!r}")
        if not args.dry_run:
            r.career_stage_snapshot = "Data curation agent"

    if not args.dry_run and ratings:
        db.commit()
        print(f"  -> {len(ratings)} rating(s) updated\n")
    elif ratings:
        print("  -> (dry run, no changes)\n")
    else:
        print("  -> none found (already correct)\n")

    db.close()


if __name__ == "__main__":
    main()
