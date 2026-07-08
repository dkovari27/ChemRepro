"""
One-time migration: strip leading "Abstract" (and variations) from paper.abstract rows.

Artefact of CrossRef JATS XML parsing — now fixed upstream in crossref.py for new
fetches, but existing rows may still carry the prefix.

Run locally:
    cd chemrepro
    python scripts/fix_abstract_prefix.py

Run against Railway (set DATABASE_URL first):
    DATABASE_URL="postgresql://..." python scripts/fix_abstract_prefix.py
"""

import re
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import create_engine, text
from app.config import settings

_PREFIX_RE = re.compile(
    r'^(Abstract\.?\s*:?\s*|ABSTRACT\.?\s*:?\s*)',
    re.IGNORECASE,
)


def main() -> None:
    engine = create_engine(settings.DATABASE_URL)

    with engine.begin() as conn:
        rows = conn.execute(
            text("SELECT doi, abstract FROM paper WHERE abstract IS NOT NULL")
        ).fetchall()

    fixed = []
    for doi, abstract in rows:
        cleaned = _PREFIX_RE.sub('', abstract).lstrip()
        if cleaned != abstract:
            fixed.append((doi, cleaned))

    if not fixed:
        print("No rows need fixing.")
        return

    print(f"Found {len(fixed)} row(s) to fix:")
    for doi, cleaned in fixed:
        print(f"  {doi[:60]!r:64s} → {cleaned[:60]!r}")

    confirm = input("\nApply changes? [y/N] ").strip().lower()
    if confirm != 'y':
        print("Aborted.")
        return

    with engine.begin() as conn:
        for doi, cleaned in fixed:
            conn.execute(
                text("UPDATE paper SET abstract = :abstract WHERE doi = :doi"),
                {"abstract": cleaned, "doi": doi},
            )

    print(f"Done. {len(fixed)} row(s) updated.")


if __name__ == "__main__":
    main()
