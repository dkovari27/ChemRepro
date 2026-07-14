import sqlite3

conn = sqlite3.connect("chemrepro.db")
cur = conn.execute(
    "DELETE FROM ratings WHERE orcid_id = 'local:ab70f09b-8f0f-4e25-8509-f517498c699e' AND scoring_mode = 'new_design'"
)
conn.commit()
print(f"Deleted {cur.rowcount} test ratings.")
conn.close()
