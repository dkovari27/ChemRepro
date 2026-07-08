"""
One-shot patch for the live Railway database:
1. Adds is_demo column to ratings and users (safe no-op if already exists).
2. Marks all seeded demo reviews and users with is_demo = true.
3. Fixes the 3 broken image reviews to use real https:// URLs.

Run:  python scripts/patch_demo_tags.py
(DATABASE_URL must be set)

Cleanup when testing is over:
    DELETE FROM comment_likes
      WHERE comment_id IN (SELECT id FROM comments WHERE orcid_id IN
        (SELECT orcid_id FROM users WHERE is_demo = true));
    DELETE FROM comments
      WHERE orcid_id IN (SELECT orcid_id FROM users WHERE is_demo = true);
    DELETE FROM likes
      WHERE rating_id IN (SELECT id FROM ratings WHERE is_demo = true);
    DELETE FROM ratings WHERE is_demo = true;
    DELETE FROM users WHERE is_demo = true;
"""

import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

DATABASE_URL = os.environ["DATABASE_URL"]
engine = create_engine(DATABASE_URL)

DEMO_ORCIDS = [
    "0000-0001-2341-5671",
    "0000-0002-3452-6782",
    "0000-0003-4563-7893",
    "0000-0004-5674-8904",
    "0000-0005-6785-9015",
    "0000-0006-7896-0126",
]

IMAGE_FIXES = [
    (
        "10.1021/acs.joc.4c02690", "0000-0003-4563-7893",
        "Reproduced core spiroacetal scaffold and extended to a 4-fluorobenzyl substrate. "
        "Yield 58% (cf. 62% parent), dr >20:1. No new functional group class introduced.\n\n"
        "![TLC plate](https://picsum.photos/seed/tlc42/400/220)",
    ),
    (
        "10.1002/anie.202109193", "0000-0002-3452-6782",
        "Enantioselective Diels-Alder step (Scheme 2, Step 3): ee 91% (reported 93%), "
        "yield 76% (reported 78%). CBS catalyst must be prepared fresh; "
        "stored catalyst dropped ee to ~70%.\n\n"
        "![NMR spectrum](https://picsum.photos/seed/nmr17/400/220)",
    ),
    (
        "10.1021/jacs.3c13492", "0000-0001-2341-5671",
        "Convergent coupling step (Scheme 4) reproduced in 71% yield (reported 74%). "
        "Extended to ent-heilonine using antipodal chiral ligand: 68% yield, ee >98% by chiral HPLC. "
        "Genuine extension to a new enantiomeric series.\n\n"
        "![Reaction setup](https://picsum.photos/seed/chem99/400/220)",
    ),
]

orcid_placeholders = ", ".join(f"'{o}'" for o in DEMO_ORCIDS)

with Session(engine) as db:
    # Add columns (ignore error if already exist)
    for stmt in [
        "ALTER TABLE ratings ADD COLUMN IF NOT EXISTS is_demo BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE users   ADD COLUMN IF NOT EXISTS is_demo BOOLEAN NOT NULL DEFAULT FALSE",
    ]:
        db.execute(text(stmt))

    # Tag demo users
    db.execute(text(f"UPDATE users SET is_demo = true WHERE orcid_id IN ({orcid_placeholders})"))

    # Tag demo ratings
    db.execute(text(f"UPDATE ratings SET is_demo = true WHERE orcid_id IN ({orcid_placeholders})"))

    # Fix broken image observations
    for doi, orcid, obs in IMAGE_FIXES:
        db.execute(
            text("UPDATE ratings SET reproducibility_observation = :obs WHERE doi = :doi AND orcid_id = :orcid"),
            {"obs": obs, "doi": doi, "orcid": orcid},
        )

    db.commit()
    print("Done: is_demo columns added, demo records tagged, image URLs fixed.")
    print()
    print("To clean up later, run:")
    print("  DELETE FROM comment_likes WHERE comment_id IN (SELECT id FROM comments WHERE orcid_id IN (SELECT orcid_id FROM users WHERE is_demo = true));")
    print("  DELETE FROM comments WHERE orcid_id IN (SELECT orcid_id FROM users WHERE is_demo = true);")
    print("  DELETE FROM likes WHERE rating_id IN (SELECT id FROM ratings WHERE is_demo = true);")
    print("  DELETE FROM ratings WHERE is_demo = true;")
    print("  DELETE FROM users WHERE is_demo = true;")
