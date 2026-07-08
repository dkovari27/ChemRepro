"""
Bulk-convert all standard-mode reviews to ChemRepro (new_design) format.

Usage:
    DATABASE_URL=<railway_url> python scripts/migrate_standard_to_nd.py

Rules:
- reproducibility_score 1-5 maps directly to nd_star 1-5.
- Reviews with no reproducibility_score are deleted (no data to map).
- If a ChemRepro review already exists for the same doi+orcid_id, the
  standard review is deleted to avoid a unique-constraint conflict.
- For nd_star=1, nd_failure_context is randomly chosen between
  "original_tested" and "extension_only".
"""

import os
import random
from datetime import datetime, timezone

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

DATABASE_URL = os.environ["DATABASE_URL"]
engine = create_engine(DATABASE_URL)

FAILURE_CONTEXTS = ["original_tested", "extension_only"]

with Session(engine) as db:
    rows = db.execute(
        text("SELECT id, doi, orcid_id, reproducibility_score FROM ratings WHERE scoring_mode = 'standard'")
    ).fetchall()

    deleted = converted = skipped = 0

    for row in rows:
        rid, doi, orcid_id, score = row

        if score is None:
            db.execute(text("DELETE FROM ratings WHERE id = :id"), {"id": rid})
            deleted += 1
            continue

        conflict = db.execute(
            text("SELECT 1 FROM ratings WHERE doi = :doi AND orcid_id = :oid AND scoring_mode = 'new_design'"),
            {"doi": doi, "oid": orcid_id},
        ).first()

        if conflict:
            db.execute(text("DELETE FROM ratings WHERE id = :id"), {"id": rid})
            deleted += 1
            continue

        ctx = random.choice(FAILURE_CONTEXTS) if score == 1 else None
        db.execute(
            text("""
                UPDATE ratings
                SET nd_star             = :star,
                    nd_failure_context  = :ctx,
                    scoring_mode        = 'new_design',
                    updated_at          = :now
                WHERE id = :id
            """),
            {"star": score, "ctx": ctx, "now": datetime.now(timezone.utc), "id": rid},
        )
        converted += 1

    db.commit()

print(f"Done: {converted} converted, {deleted} deleted, {skipped} skipped.")
