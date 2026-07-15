"""
Replace broken data-URI images in seeded reviews with real https:// image URLs.

Run:  python scripts/fix_review_images.py
(DATABASE_URL must be set)
"""

import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

DATABASE_URL = os.environ["DATABASE_URL"]
engine = create_engine(DATABASE_URL)

# picsum.photos with a fixed seed returns the same image every time
FIXES = [
    # (doi, orcid_id, new_observation_text)
    (
        "10.1021/acs.joc.4c02690",
        "0000-0003-4563-7893",
        "Reproduced core spiroacetal scaffold and extended to a 4-fluorobenzyl substrate. "
        "Yield 58% (cf. 62% parent), dr >20:1. No new functional group class introduced.\n\n"
        "![TLC plate](https://picsum.photos/seed/tlc42/400/220)",
    ),
    (
        "10.1002/anie.202109193",
        "0000-0002-3452-6782",
        "Enantioselective Diels-Alder step (Scheme 2, Step 3): ee 91% (reported 93%), "
        "yield 76% (reported 78%). CBS catalyst must be prepared fresh; "
        "stored catalyst dropped ee to ~70%.\n\n"
        "![NMR spectrum](https://picsum.photos/seed/nmr17/400/220)",
    ),
    (
        "10.1021/jacs.3c13492",
        "0000-0001-2341-5671",
        "Convergent coupling step (Scheme 4) reproduced in 71% yield (reported 74%). "
        "Extended to ent-heilonine using the antipodal chiral ligand: 68% yield, ee >98% by chiral HPLC. "
        "Genuine extension to a new enantiomeric series.\n\n"
        "![Reaction setup](https://picsum.photos/seed/chem99/400/220)",
    ),
]

with Session(engine) as db:
    for doi, orcid, obs in FIXES:
        db.execute(
            text("""
                UPDATE ratings
                SET reproducibility_observation = :obs
                WHERE doi = :doi AND orcid_id = :orcid AND scoring_mode = 'new_design'
            """),
            {"obs": obs, "doi": doi, "orcid": orcid},
        )
    db.commit()
    print(f"Done: {len(FIXES)} reviews updated.")
