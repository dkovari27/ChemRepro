# ChemRepro Web App — Session Guide

## Session start checklist
1. Read **PROJECT_STATE.md** — current status of every feature, environment variables, scripts
2. Read **TASKS.md** — parked and planned work
3. If the task touches the scraper pipeline or shared data fields, read **INTERFACE_CHANGELOG.md**

## Before ending a session
1. Update **PROJECT_STATE.md** if any feature status changed
2. Commit outstanding changes with a meaningful message

## Before every push to GitHub
1. **Run a full bug and problem search** across all changed files: read each file, trace every flow end-to-end, check for edge cases, session leaks, missing guards, template/router mismatches, and anything that could break in production.
2. **Report findings to Daniel** grouped by severity (high / medium / low). Do not proceed until he responds.
   - If there are **high or medium** issues: propose fixes, get approval, apply them, then re-run the search before pushing.
   - If there are **only low or no** issues: summarise briefly and ask for push approval.
3. Add an entry to **PUSHLOG.md** (date, commit hash, files, what changed, key decisions, what was deferred).
4. Never push automatically — always wait for explicit "push" instruction from Daniel.

## Cross-project protocol
The scraper (`ChemRepro-Paper_scraper/`) and this web app share a data contract.
Before touching any of these, read `INTERFACE_CHANGELOG.md` and add an entry if you change anything:
- `app/models/rating.py` (any field the importer writes)
- `app/models/user.py` (bot user fields)
- `scripts/import_reviews.py` (import field names, confidence thresholds)
- `scripts/resolve_citations.py`
- `SCRAPER_DATA_SPEC.md`

## Hard rules (always apply)
- Never use em dashes (— / &mdash;). Use comma, semicolon, or colon.
- Never push to GitHub automatically.
- DEV-only features: wrap templates in `{% if is_local %}`, wrap routes in `if settings.ORCID_ENV == "production": raise HTTPException(403)`.
- Reviewer nicknames (AI-JACSAU, AI-OrgSyn, etc.) must be confirmed by Daniel before use.

## Key people and contacts
- Daniel Kovari — owner, medicinal chemist, Basel / SpiroChem
- chemrepro@gmail.com — admin contact
- dani.kovari@gmail.com — personal

## Architecture at a glance
- FastAPI + Jinja2 + SQLAlchemy ORM
- SQLite locally (chemrepro.db), PostgreSQL on Railway (production)
- Tailwind CSS, vanilla JS
- Hosted: chemrepro.org (Railway, auto-deploys from main)
- `ORCID_ENV=sandbox` → local dev; `ORCID_ENV=production` → Railway
- `is_local` Jinja global = True when ORCID_ENV == "sandbox"
