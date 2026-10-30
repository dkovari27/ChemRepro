"""
Smoke test of the running app code against the LOCAL dev database.

Drives the app through FastAPI's TestClient as local dev user 0 ("Alice"):
library save/notes/move/export, upload limits, the cross-site POST check,
DOI case redirects and sign-out. It saves one paper Alice has not saved,
then unsaves it again, so the dev data is left as it was.

Refuses to run unless ORCID_ENV=sandbox and the database is SQLite.

Run from the project root:
    .venv\\Scripts\\python.exe scripts\\smoke_test.py
"""
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings  # noqa: E402

if settings.ORCID_ENV != "sandbox" or not settings.DATABASE_URL.startswith("sqlite"):
    sys.exit("smoke_test.py runs only against the local SQLite dev database (ORCID_ENV=sandbox).")

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models.paper import Paper  # noqa: E402
from app.models.saved_paper import SavedPaper  # noqa: E402
from app.services import library_storage  # noqa: E402

results = []


def check(name, cond, extra=""):
    results.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if extra else ""))


c = TestClient(app, follow_redirects=False)

# Public pages render
for path in ("/", "/about", "/privacy", "/feedback"):
    r = c.get(path)
    check(f"GET {path} -> 200", r.status_code == 200, r.status_code)

c.get("/auth/dev-login/0")
for path in ("/library", "/profile/my-reviews", "/profile/subscriptions", "/profile/inbox",
             "/profile/notifications", "/profile/settings"):
    r = c.get(path)
    check(f"GET {path} (signed in) -> 200", r.status_code == 200, r.status_code)

# A paper no account has saved yet, with a DOI that has lowercase letters
db = SessionLocal()
saved_any = {d for (d,) in db.query(SavedPaper.doi).all()}
doi = next(d for (d,) in db.query(Paper.doi).all() if d not in saved_any and d != d.upper())
db.close()

r = c.get(f"/paper/{doi}")
check("paper page -> 200", r.status_code == 200, r.status_code)

# Input checks (audit M3 / L2)
r = c.post("/library/save", data={"doi": "10.9999/does-not-exist-xyz"})
check("save unknown DOI -> 404", r.status_code == 404, r.status_code)
r = c.post("/library/save", data={"doi": doi, "collection_id": "abc"})
check("save with bad collection id -> 200", r.status_code == 200, r.status_code)
r = c.post("/library/save", data={"doi": doi, "collection_id": "99999999999"})
check("save with huge collection id -> 200", r.status_code == 200, r.status_code)
r = c.get("/library?collection=99999999999")
check("library ?collection=huge -> redirect", r.status_code == 303, r.status_code)
r = c.get("/library?collection=0")
check("library unsorted -> 200", r.status_code == 200, r.status_code)
r = c.post("/library/entry/99999999999/move", data={"collection_id": ""})
check("move with huge id -> 422", r.status_code == 422, r.status_code)

# Clearing the Save box deletes the first note (audit L1)
c.post("/library/save", data={"doi": doi, "notes": "temp note"})
db = SessionLocal()
had = db.query(SavedPaper).filter(SavedPaper.doi == doi).first().first_note_body
db.close()
c.post("/library/save", data={"doi": doi, "notes": ""})
db = SessionLocal()
sp = db.query(SavedPaper).filter(SavedPaper.doi == doi).first()
entry_id, now = sp.id, sp.first_note_body
db.close()
check("clearing the Save box deletes the note", had == "temp note" and now == "", f"{had!r} -> {now!r}")

# Export file names (audit L3)
r = c.get('/library/export/x"y.bib')
check("export filename sanitised", 'filename="chemrepro-all.bib"' in r.headers.get("content-disposition", ""))
r = c.get("/library/export/0.ris")
check("unsorted export label", "chemrepro-unsorted.ris" in r.headers.get("content-disposition", ""))

# Upload limits (audit M1)
buf = io.BytesIO()
Image.new("RGB", (10, 10), "red").save(buf, "PNG")
r = c.post(f"/library/entry/{entry_id}/files", files={"file": ("a.png", buf.getvalue(), "image/png")})
check("small upload -> 200", r.status_code == 200, r.status_code)
uuid = r.json().get("file", {}).get("uuid") if r.status_code == 200 else None
too_big = b"%PDF-" + b"0" * (library_storage.MAX_FILE_BYTES + 1024 * 1024)
r = c.post(f"/library/entry/{entry_id}/files", files={"file": ("big.pdf", too_big, "application/pdf")})
check("oversized upload -> 413", r.status_code == 413, f"{r.status_code} {r.text[:60]}")
if uuid:
    r = c.post(f"/library/file/{uuid}/delete")
    check("delete uploaded file -> 200", r.status_code == 200, r.status_code)

# Cross-site POST check
r = c.post("/library/save", data={"doi": doi}, headers={"Origin": "https://evil.example"})
check("cross-site POST -> 403", r.status_code == 403, r.status_code)
r = c.post("/library/save", data={"doi": doi}, headers={"Origin": "http://testserver"})
check("same-site POST -> 200", r.status_code == 200, r.status_code)

# DOI case variant redirects to the stored spelling (audit L6)
r = c.get("/paper/" + doi.upper())
check("DOI case variant -> 301", r.status_code == 301 and r.headers.get("location") == f"/paper/{doi}",
      f"{r.status_code} {r.headers.get('location')}")

c.post("/library/unsave", data={"doi": doi})

# Sign-out only by POST (audit L7)
c.get("/auth/logout")
r = c.get("/library")
check("GET /auth/logout does not sign out", r.status_code == 200, r.status_code)
c.post("/auth/logout")
r = c.get("/library")
check("POST /auth/logout signs out", r.status_code == 303, r.status_code)

print(f"\n{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
