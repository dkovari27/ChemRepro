"""
Run once from the chemrepro/ directory to seed the demo paper with Standard and Classic reviews.
Usage: python seed_demo.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from datetime import datetime, timezone, timedelta
from app.database import SessionLocal
from app.models.paper import Paper
from app.models.user import User
from app.models.rating import Rating

DEMO_DOI = "10.0000/chemrepro.demo.2024"

FAKE_USERS = [
    ("0000-0000-0000-0001", "Alice Testuser"),
    ("0000-0000-0000-0002", "Bob Labrat"),
    ("0000-0000-0000-0003", "Carol Benchwork"),
    ("0000-0000-0000-0004", "David Fume"),
    ("0000-0000-0000-0005", "Eva Flask"),
    ("0000-0000-0000-0006", "Frank Yield"),
    ("0000-0000-0000-0007", "Grace Stir"),
    ("0000-0000-0000-0008", "Hans Reaktion"),
    ("0000-0000-0000-0009", "Irene Substrate"),
]

# ── Standard reviews (outcome-based, scoring_mode="standard") ──────────────
# outcome → score: extended=5, repro_ext_failed=4, reproduced=3, no_ext=2, no_repro=1
# Average = (5+5+4+3+3+2+1)/7 ≈ 3.3
STANDARD_REVIEWS = [
    # (orcid, outcome, scope_level, repro_obs, scope_obs, mod_details)
    ("0000-0000-0000-0004", "extended",               "extended", "Ran substrate 3b on 1 g scale — clean conversion, isolated 88%.",   "Tested 6 aryl halides, all worked.",       "Switched to Pd(OAc)₂ — identical yield."),
    ("0000-0000-0000-0005", "extended",               "extended", "Reproduced Table 2, entries 1–4. Then extended to alkyl chlorides.", "Three new substrates gave >70%.",          None),
    ("0000-0000-0000-0001", "repro_extension_failed",  "medium",  "Reproduced the key substrate (compound 7) cleanly.",                "Tried heteroaromatic extension — failed.", None),
    ("0000-0000-0000-0006", "reproduced",              None,      "Compound 4a reproduced on 200 mg scale. Exact yield match.",        None,                                       None),
    ("0000-0000-0000-0007", "reproduced",              None,      "Ran the reaction at half scale — worked but yield slightly lower.", None,                                       None),
    ("0000-0000-0000-0002", "no_extension",            "minor",   None,                                                                "Attempted 3 analogues — none worked.",     "Used MeCN instead of DMF."),
    ("0000-0000-0000-0003", "no_repro",                None,      "Could not reproduce compound 5g even after 4 attempts.",           None,                                       None),
]

# ── Classic reviews (dual star scores, scoring_mode="classic") ─────────────
# repro_score: 1=Failed, 3=Partial, 5=Exact | ext_score: 1=Minor, 3=Medium, 5=Major
CLASSIC_REVIEWS = [
    # (orcid, repro_score, repro_obs, ext_score, ext_obs)
    ("0000-0000-0000-0001", 5, "Clean reproduction of compound 7 at 500 mg scale, 91% yield.",              5, "Extended to 8 aryl bromides with ee >95% throughout."),
    ("0000-0000-0000-0002", 4, "Mostly reproduced — yield 10% lower than reported.",                       3, "Tested 3 heteroaromatic substrates, 2 gave moderate yields."),
    ("0000-0000-0000-0003", 2, "Struggled with moisture sensitivity — partial decomposition observed.",     None, None),
    ("0000-0000-0000-0004", 5, "Exact yield match on entry 3b. Switched to commercial Pd catalyst — fine.", 4, "Alkyl chlorides worked with slightly modified conditions."),
    ("0000-0000-0000-0005", 3, "Reproduced at 50 mg scale but ee was 5% lower than reported.",             2, "Only one of four substrate extensions gave acceptable yield."),
    ("0000-0000-0000-0006", 5, "Reproduced Table 2 completely over two runs. Highly reproducible.",         5, "New substrate class (benzylic C–H) also worked — major scope."),
    ("0000-0000-0000-0007", 1, "Could not reproduce — suspected ligand batch issue.",                       None, None),
    # Extension-only reviews (no reproducibility score)
    ("0000-0000-0000-0008", None, None, 4, "Successfully extended to trifluoromethyl substrates — moderate yields across 5 analogues."),
    ("0000-0000-0000-0009", None, None, 5, "Major scope extension — tested 12 new electrophiles, all gave >80% yield with excellent ee."),
]

REPRO_SCORES = {
    "extended":               5,
    "repro_extension_failed": 4,
    "reproduced":             4,
    "no_extension":           None,
    "no_repro":               1,
}

db = SessionLocal()
try:
    # Clean previous demo data
    db.query(Rating).filter(Rating.doi == DEMO_DOI).delete()
    existing_paper = db.get(Paper, DEMO_DOI)
    if existing_paper:
        db.delete(existing_paper)
    db.commit()

    # Demo paper
    db.add(Paper(
        doi=DEMO_DOI,
        title="Palladium-Catalysed Enantioselective C–H Functionalisation of Unactivated Methylene Groups",
        authors='["Lena Hartmann", "Markus Vogel", "Sofía Romero-García", "Takeshi Yamamoto", "Peter Baran"]',
        journal="Journal of the American Chemical Society",
        year=2024,
        fetched_at=datetime.now(timezone.utc),
    ))

    # Ensure all fake users exist
    for orcid, name in FAKE_USERS:
        if not db.get(User, orcid):
            db.add(User(orcid_id=orcid, name=name, verified_at=datetime.now(timezone.utc)))

    # Standard reviews
    for i, (orcid, outcome, scope_level, repro_obs, scope_obs, mod_details) in enumerate(STANDARD_REVIEWS):
        db.add(Rating(
            doi=DEMO_DOI,
            orcid_id=orcid,
            scoring_mode="standard",
            outcome=outcome,
            reproducibility_score=REPRO_SCORES.get(outcome),
            reproducibility_observation=repro_obs,
            scope_level=scope_level,
            scope_observation=scope_obs,
            modification_details=mod_details,
            created_at=datetime.now(timezone.utc) - timedelta(days=i * 3),
        ))

    # Classic reviews
    for i, (orcid, repro_score, repro_obs, ext_score, ext_obs) in enumerate(CLASSIC_REVIEWS):
        db.add(Rating(
            doi=DEMO_DOI,
            orcid_id=orcid,
            scoring_mode="classic",
            reproducibility_score=repro_score,
            reproducibility_observation=repro_obs,
            generalisability_score=ext_score,
            scope_observation=ext_obs,
            created_at=datetime.now(timezone.utc) - timedelta(days=i * 2 + 1),
        ))

    db.commit()
    print(f"Demo paper: /paper/{DEMO_DOI}")
    print(f"Standard reviews: {len(STANDARD_REVIEWS)}")
    print(f"Classic reviews:  {len(CLASSIC_REVIEWS)}")
except Exception as e:
    db.rollback()
    raise
finally:
    db.close()
