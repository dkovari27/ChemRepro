import os, re
from sqlalchemy import create_engine, text

url = re.sub(r"^postgres(ql)?://", "postgresql+psycopg://", os.environ["DATABASE_URL"])
engine = create_engine(url)

with engine.connect() as conn:
    result = conn.execute(text("""
        UPDATE ratings
        SET career_stage_snapshot = 'PhD student'
        WHERE orcid_id = '0000-0001-8593-9380'
          AND doi NOT IN ('10.1021/acs.oprd.4c00165', '10.1016/j.isci.2023.106255')
    """))
    conn.commit()
    print(f"Updated {result.rowcount} row(s).")
