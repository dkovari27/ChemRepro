"""
Seed the admin-curated banned_terms table with a batch of profanity slang and
common misspellings (fuck/shit/bitch/ass/dick families, plus a few milder
swears). These are literal whole-word entries, matched the same way as any
word an admin adds by hand at /admin/banned-words, no code changes required
to add more later; just add them there.

Idempotent: mirrors the dedup logic in admin_add_banned_word() (case-insensitive,
skips terms that already exist), so it's safe to re-run.

Run:  python scripts/seed_banned_terms.py
(DATABASE_URL must be set)
"""

import os

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

DATABASE_URL = os.environ["DATABASE_URL"]
engine = create_engine(DATABASE_URL)

TERMS = [
    # "Fuck" family
    "fuckery", "fuckup", "fuckups", "fuckwit", "fuckwits",
    "motherfucker", "motherfuckers", "motherfucking", "clusterfuck",
    "fuckboy", "fuckface",
    "fuk", "fuking", "fukin", "fukn", "fucc", "fuxx", "fuxk",
    "fuq", "fuqing", "phuck", "phuk", "fck", "fcking", "fckin", "fkin",

    # "Shit" family
    "shithead", "shitheads", "shitface", "horseshit", "dogshit",
    "shyt", "shyte", "sh1t", "shiit",

    # "Bitch" family
    "bitchy", "biatch", "biotch", "b1tch",

    # "Ass" family
    "ass", "dumbass", "jackass", "asswipe", "assface",

    # "Dick" family
    "dickhead", "dickheads", "d1ck", "dik",

    # Other common slang / misspellings
    "hoe", "hoes", "sloot", "slvt", "pu55y",

    # Milder swears
    "crap", "crappy", "damn", "dammit", "goddamn", "goddammit",
]

SEEDED_BY = "seed_script:2026-08-11"


def main() -> None:
    with Session(engine) as db:
        added, skipped = 0, 0
        for raw in TERMS:
            term_clean = raw.strip().lower()
            existing = db.execute(
                text("SELECT id FROM banned_terms WHERE term = :t COLLATE NOCASE")
                if engine.dialect.name == "sqlite"
                else text("SELECT id FROM banned_terms WHERE LOWER(term) = LOWER(:t)"),
                {"t": term_clean},
            ).first()
            if existing:
                skipped += 1
                continue
            db.execute(
                text("INSERT INTO banned_terms (term, added_by, created_at) "
                     "VALUES (:t, :by, CURRENT_TIMESTAMP)"),
                {"t": term_clean, "by": SEEDED_BY},
            )
            added += 1
        db.commit()
        print(f"Added {added} new terms, skipped {skipped} already present "
              f"(out of {len(TERMS)} total).")


if __name__ == "__main__":
    main()
