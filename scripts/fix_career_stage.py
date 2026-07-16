import os, re
from sqlalchemy import create_engine, text

url = re.sub(r"^postgres(ql)?://", "postgresql+psycopg://", os.environ["DATABASE_URL"])
engine = create_engine(url)
EXCLUDE = ("10.1021/acs.oprd.4c00165", "10.1016/j.isci.2023.106255")
ORCID = "0000-0001-8593-9380"

with engine.connect() as conn:
    rows = conn.execute(text(
        "SELECT id, doi, career_stage_snapshot FROM ratings WHERE orcid_id = :orcid ORDER BY id"
    ), {"orcid": ORCID}).fetchall()
    print(f"Total reviews by this user: {len(rows)}")
    for r in rows:
        status = "SKIP" if r.doi in EXCLUDE else "WILL UPDATE"
        print(f"  id={r.id}  {status}  stage={r.career_stage_snapshot}  {r.doi}")
