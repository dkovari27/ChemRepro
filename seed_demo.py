"""
Run once from the chemrepro/ directory to create a fake demo paper with 7 reviews.
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
]

# 7 reviews spread across outcomes to give a realistic distribution
#  outcome          → Option A score
#  extended         → 5  (×2)
#  repro_ext_failed → 4  (×1)
#  reproduced       → 3  (×2)
#  no_extension     → 2  (×1)
#  no_repro         → 1  (×1)
#  Average = (5+5+4+3+3+2+1)/7 = 23/7 ≈ 3.3
REVIEWS = [
    ("0000-0000-0000-0004", "extended",               "extended",       "Ran substrate 3b on 1 g scale — clean conversion, isolated 88%.",  "Tested 6 aryl halides, all worked.",      "Switched to Pd(OAc)₂ — identical yield."),
    ("0000-0000-0000-0005", "extended",               "extended",       "Reproduced Table 2, entries 1–4. Then extended to alkyl chlorides.", "Three new substrates gave >70%.",         None),
    ("0000-0000-0000-0001", "repro_extension_failed",  "medium",         "Reproduced the key substrate (compound 7) cleanly.",               "Tried heteroaromatic extension — failed.",None),
    ("0000-0000-0000-0006", "reproduced",             None,             "Compound 4a reproduced on 200 mg scale. Exact yield match.",       None,                                      None),
    ("0000-0000-0000-0007", "reproduced",             None,             "Ran the reaction at half scale — worked but yield slightly lower.", None,                                      None),
    ("0000-0000-0000-0002", "no_extension",           "minor",          None,                                                               "Attempted 3 analogues — none worked.",    "Used MeCN instead of DMF."),
    ("0000-0000-0000-0003", "no_repro",               None,             "Could not reproduce compound 5g even after 4 attempts.",           None,                                      None),
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
    # Clean up any previous demo data
    db.query(Rating).filter(Rating.doi == DEMO_DOI).delete()
    if db.get(Paper, DEMO_DOI):
        db.delete(db.get(Paper, DEMO_DOI))
    db.commit()

    # Create fake paper
    paper = Paper(
        doi=DEMO_DOI,
        title="Palladium-Catalysed Enantioselective C–H Functionalisation of Unactivated Methylene Groups",
        authors='["Lena Hartmann", "Markus Vogel", "Sofía Romero-García", "Takeshi Yamamoto", "Peter Baran"]',
        journal="Journal of the American Chemical Society",
        year=2024,
        fetched_at=datetime.now(timezone.utc),
    )
    db.add(paper)

    # Ensure all fake users exist
    for orcid, name in FAKE_USERS:
        if not db.get(User, orcid):
            db.add(User(orcid_id=orcid, name=name, verified_at=datetime.now(timezone.utc)))

    # Create reviews with staggered timestamps
    for i, (orcid, outcome, scope_level, repro_obs, scope_obs, mod_details) in enumerate(REVIEWS):
        rating = Rating(
            doi=DEMO_DOI,
            orcid_id=orcid,
            outcome=outcome,
            reproducibility_score=REPRO_SCORES.get(outcome),
            reproducibility_observation=repro_obs,
            scope_level=scope_level,
            scope_observation=scope_obs,
            modification_details=mod_details,
            created_at=datetime.now(timezone.utc) - timedelta(days=i * 3),
        )
        db.add(rating)

    db.commit()
    print(f"Demo paper created: /paper/{DEMO_DOI}")
    print(f"Reviews: {len(REVIEWS)}")
except Exception as e:
    db.rollback()
    raise
finally:
    db.close()
