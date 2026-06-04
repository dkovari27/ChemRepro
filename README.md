# ChemRepro

Community reproducibility ratings for synthetic chemistry papers.

Verified chemists rate whether published reactions actually work — and whether they extend to new substrates.

## What it does

- Look up any chemistry paper by DOI
- Submit a structured reproducibility review (outcome, observations, scope extension)
- See aggregated scores and community reviews
- Filter and sort reviews by outcome, scope, rating, or date

## Running locally

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open `http://localhost:8000`. Use the dev login buttons to test as a fake user.

## Configuration

Copy `.env.example` to `.env` and fill in the values:

```
DATABASE_URL=sqlite:///./chemrepro.db   # SQLite for local dev
SECRET_KEY=your-secret-key-here
ORCID_ENV=sandbox                       # sandbox | production
ORCID_CLIENT_ID=
ORCID_CLIENT_SECRET=
ORCID_REDIRECT_URI=http://localhost:8000/auth/callback
```

## Editing the review form prompts

Open `app/prompts.py` — all placeholder texts in the review form are there, clearly labelled. Edit and save; the server picks up changes on restart.

## Deploying to Railway

1. Push to GitHub
2. Connect the repo in Railway → New Project → Deploy from GitHub
3. Add a PostgreSQL plugin (Railway sets `DATABASE_URL` automatically)
4. Set environment variables: `SECRET_KEY`, `ORCID_ENV=production`, `ORCID_REDIRECT_URI`

## Design demo pages (dev only, blocked in production)

| URL | What it shows |
|-----|--------------|
| `/design-demo` | Scoring display: Option A vs Option D |
| `/design-demo/scoring` | Score label formats: Option 2+3 vs Option 5 |
| `/design-demo/scoring-ab` | **Form comparison: Version A (single score) vs Version B (classic 2-score)** |

## Scoring systems

Two scoring modes are available per paper (toggle on the form):

| Mode | How it works |
|---|---|
| **Single score** | Outcome selection maps to 1–5, averaged across all reviews |
| **Classic (2 scores)** | Outcome selection + separate 1–5 reproducibility star rating |

## Tech stack

FastAPI · SQLAlchemy · SQLite (dev) / PostgreSQL (prod) · Jinja2 · Tailwind CSS
