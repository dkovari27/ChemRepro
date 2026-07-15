"""
Seed demo ChemRepro reviews, comments, and placeholder images for the 5 live papers.

Run:  python scripts/seed_demo_reviews.py
(DATABASE_URL must be set)
"""

import os
import random
from datetime import datetime, timezone, timedelta

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

DATABASE_URL = os.environ["DATABASE_URL"]
engine = create_engine(DATABASE_URL)

# ── Placeholder images (picsum.photos — fixed seed = same image every time) ──

NMR = "![NMR spectrum](https://picsum.photos/seed/nmr17/400/220)"
TLC = "![TLC plate](https://picsum.photos/seed/tlc42/400/220)"

# ── Fake users ────────────────────────────────────────────────────────────────

USERS = [
    ("0000-0001-2341-5671", "Dr. Sarah Mitchell",  "sarah_m",    "Postdoc"),
    ("0000-0002-3452-6782", "James Hoffmann",       "j_hoffmann", "PhD student"),
    ("0000-0003-4563-7893", "Prof. Elena Vasquez",  "e_vasquez",  "Academic PI"),
    ("0000-0004-5674-8904", "Thomas Brenner",       "t_brenner",  "Industry / CRO chemist"),
    ("0000-0005-6785-9015", "Dr. Aiko Tanaka",      "aiko_t",     "Postdoc"),
    ("0000-0006-7896-0126", "Lars Eriksson",        "l_eriksson", "Independent researcher"),
]

# ── Reviews ───────────────────────────────────────────────────────────────────
# (doi, nd_star, nd_failure_context, user_idx, observation_text)

REVIEWS = [
    # Paper 1 — Bis-morpholine Spiroacetals
    (
        "10.1021/acs.joc.4c02690", 3, None, 0,
        "Repeated the spiroacetalisation sequence (Steps 1-4, Table 2). "
        "BF3·OEt2 cyclisation at -78 C to rt proceeded cleanly. "
        "Isolated yield 62% (reported 65%), NMR fully consistent.\n\n" + NMR,
    ),
    (
        "10.1021/acs.joc.4c02690", 2, None, 1,
        "The oxazoline formation (Scheme 3, Step 6) required raising temperature from 80 C to 100 C "
        "for full conversion; at 80 C only ~40% product after 12 h. "
        "Yield 44% vs. reported 71%. Strict anhydrous conditions essential.",
    ),
    (
        "10.1021/acs.joc.4c02690", 4, None, 2,
        "Reproduced core spiroacetal scaffold and extended to a 4-fluorobenzyl substrate. "
        "Yield 58% (cf. 62% parent), dr >20:1. "
        "No new functional group class introduced.\n\n" + TLC,
    ),

    # Paper 2 — Deaminative Halogenation
    (
        "10.1016/j.isci.2023.106255", 3, None, 3,
        "Reproduced deaminative bromination of benzylamine (Table 1, entry 3) using NBS/Cu(OTf)2. "
        "Conversion >95% by GC after 2 h at rt; yield 78% (reported 81%). "
        "Slow addition of NBS critical to avoid over-bromination.",
    ),
    (
        "10.1016/j.isci.2023.106255", 1, "original_tested", 4,
        "Could not reproduce iodination of primary aliphatic amine (Table 3, entry 7). "
        "I2/CuI/DMSO at 60 C gave <5% product by GC-MS; dominant by-product was the diazonium species. "
        "Fresh CuI and anhydrous DMSO made no difference. Aromatic substrates worked fine.",
    ),
    (
        "10.1016/j.isci.2023.106255", 4, None, 5,
        "Reproduced chlorination of 4-methoxybenzylamine (82%, reported 85%) "
        "and extended to a benzylic sulfonamide substrate (yield 74%). "
        "Good functional group tolerance confirmed.",
    ),

    # Paper 3 — Total Synthesis of (+)-Garsubellin A
    (
        "10.1002/anie.202109193", 3, None, 1,
        "Enantioselective Diels-Alder step (Scheme 2, Step 3): ee 91% (reported 93%), "
        "yield 76% (reported 78%). CBS catalyst must be prepared fresh; "
        "stored catalyst dropped ee to ~70%.\n\n" + NMR,
    ),
    (
        "10.1002/anie.202109193", 2, None, 2,
        "Late-stage oxidative dearomatisation (Step 14) gave only 55% yield (reported 82%) "
        "with PhI(OAc)2. Switching to Koser's reagent improved to 68%. "
        "Step is highly concentration-dependent; 0.05 M better than 0.1 M.",
    ),

    # Paper 4 — Total Synthesis of (+)-Heilonine
    (
        "10.1021/jacs.3c13492", 5, None, 0,
        "Convergent coupling step (Scheme 4) reproduced in 71% yield (reported 74%). "
        "Extended to ent-heilonine using the antipodal chiral ligand: 68% yield, ee >98% by chiral HPLC. "
        "Genuine extension to a new enantiomeric series.\n\n" + TLC,
    ),
    (
        "10.1021/jacs.3c13492", 3, None, 3,
        "Intramolecular aza-Michael addition (Step 8) reproduced cleanly. "
        "Yield 83% (reported 85%), dr >95:5. "
        "Tolerates Cs2CO3 or K2CO3 interchangeably with no significant yield loss.",
    ),
    (
        "10.1021/jacs.3c13492", 1, "extension_only", 5,
        "Attempted the N-oxide cyclisation on a homologated substrate (one extra methylene). "
        "Only trace product; 7-membered ring closure did not proceed under these conditions. "
        "Did not test the original substrate from the paper.",
    ),

    # Paper 5 — Visible Light Radical Coupling
    (
        "10.1039/D1CS00311A", 3, None, 4,
        "Reproduced Giese-type acyl radical addition (section 3.2) using Ir(ppy)3 (2 mol%), 450 nm. "
        "Yield 73% (reported 75%). No photoreactor needed; 40W LED strip sufficient. "
        "Freeze-pump-thaw degassing (3 cycles) essential.",
    ),
    (
        "10.1039/D1CS00311A", 4, None, 2,
        "Applied radical decarboxylative coupling (section 4.1) to a protected glutamic acid derivative. "
        "Yield 61% (parent substrate 78%), likely due to Boc steric bulk. "
        "Scaled to 5 mmol without re-optimisation (54% at scale).",
    ),
]

# ── Comments ──────────────────────────────────────────────────────────────────
# (doi, review_local_idx, commenter_user_idx, comment, reply_or_None, replier_user_idx_or_None)

COMMENTS = [
    (
        "10.1021/acs.joc.4c02690", 1, 2,
        "Did you try varying the Lewis acid? We found Sc(OTf)3 gave 68% at the same temperature.",
        "Thanks — we only tried BF3 and TiCl4. Will test Sc(OTf)3 in the next run.", 4,
    ),
    (
        "10.1016/j.isci.2023.106255", 0, 5,
        "Did you pre-dry the Cu(OTf)2? We saw a significant difference between activated and commercial material.",
        None, None,
    ),
    (
        "10.1002/anie.202109193", 0, 3,
        "Matches our experience. CBS aged noticeably within a few hours at rt even under N2.",
        "We now store it at -20 C with molecular sieves; shelf life extended to ~1 week.", 0,
    ),
    (
        "10.1021/jacs.3c13492", 1, 5,
        "Good to see the base insensitivity confirmed. We accidentally used DBU once and still got 79%.",
        None, None,
    ),
    (
        "10.1039/D1CS00311A", 0, 1,
        "What LED setup did you use? Comparing a 34W Kessil vs. a simple strip for this reaction type.",
        "We used a Radleys Lighthouse (40W blue insert). The Kessil should work similarly; keep the flask cooled.", 3,
    ),
]


# ── Run ───────────────────────────────────────────────────────────────────────

with Session(engine) as db:
    now = datetime.now(timezone.utc)

    # Widen observation column to TEXT so inline images fit
    db.execute(text("ALTER TABLE ratings ALTER COLUMN reproducibility_observation TYPE TEXT"))
    db.commit()

    # Insert users (skip existing)
    for orcid, name, nickname, career in USERS:
        exists = db.execute(text("SELECT 1 FROM users WHERE orcid_id = :id"), {"id": orcid}).first()
        if not exists:
            db.execute(
                text("""
                    INSERT INTO users (orcid_id, name, nickname, career_stage,
                                      career_stage_set, pledge_accepted, verified_at, is_demo)
                    VALUES (:orcid, :name, :nick, :career, true, false, :now, true)
                """),
                {"orcid": orcid, "name": name, "nick": nickname, "career": career, "now": now},
            )

    # Insert reviews, track (doi, local_idx) -> rating_id for comments
    doi_count = {}
    rating_id_map = {}

    for doi, star, ctx, user_idx, obs in REVIEWS:
        orcid = USERS[user_idx][0]
        local_idx = doi_count.get(doi, 0)
        doi_count[doi] = local_idx + 1
        created_at = now - timedelta(days=random.randint(10, 150))

        row = db.execute(
            text("""
                INSERT INTO ratings
                    (doi, orcid_id, scoring_mode, nd_star, nd_failure_context,
                     reproducibility_observation, ai_flagged, is_demo, created_at)
                VALUES
                    (:doi, :orcid, 'new_design', :star, :ctx, :obs, false, true, :created)
                RETURNING id
            """),
            {"doi": doi, "orcid": orcid, "star": star, "ctx": ctx, "obs": obs, "created": created_at},
        ).fetchone()
        rating_id_map[(doi, local_idx)] = row[0]

    # Insert comments and optional replies
    for doi, local_idx, commenter_idx, comment, reply, replier_idx in COMMENTS:
        rating_id = rating_id_map.get((doi, local_idx))
        if not rating_id:
            continue
        commenter = USERS[commenter_idx][0]
        c_created = now - timedelta(days=random.randint(2, 40))

        cid = db.execute(
            text("""
                INSERT INTO comments (doi, rating_id, orcid_id, content, ai_flagged, created_at, parent_id)
                VALUES (:doi, :rid, :orcid, :body, false, :created, null)
                RETURNING id
            """),
            {"doi": doi, "rid": rating_id, "orcid": commenter, "body": comment, "created": c_created},
        ).fetchone()[0]

        if reply and replier_idx is not None:
            replier = USERS[replier_idx][0]
            db.execute(
                text("""
                    INSERT INTO comments (doi, rating_id, orcid_id, content, ai_flagged, created_at, parent_id)
                    VALUES (:doi, :rid, :orcid, :body, false, :created, :parent)
                """),
                {
                    "doi": doi, "rid": rating_id, "orcid": replier, "body": reply,
                    "created": c_created + timedelta(hours=random.randint(3, 72)),
                    "parent": cid,
                },
            )

    db.commit()
    print(f"Done: {len(REVIEWS)} reviews and {len(COMMENTS)} comment threads inserted.")
