# ChemRepro

Community reproducibility ratings for synthetic and medicinal chemistry papers.

Verified chemists log in with their ORCID iD and rate whether published reactions actually work, whether they extend to new substrates, and how the attempt compared to what was reported. Reviews are attached to DOIs and aggregated into a community score visible on every paper page.

## Features

- Search or look up any chemistry paper by DOI; metadata is fetched automatically from CrossRef
- Submit a structured ND-star review with free-text observations and optional images
- See aggregated scores and community reviews per paper
- Filter and sort reviews by outcome, rating, or date
- Comment on reviews with threaded replies
- Report problematic content; admin reviews flagged submissions
- Follow reviewers and receive site messages
- Personal library of saved papers: collections, multiple private notes per paper, PDF and screenshot uploads (20 MB per user; set `LIBRARY_DIR` to a persistent volume in production)
- Admin dashboard for managing reviews, comments, reports, banned words, and API keys
- JSON API for programmatic access

## Rating scale (ND stars)

| Stars | Meaning |
|-------|---------|
| 5 | Major extension: substantially broader scope than reported |
| 4 | Minor extension: modest improvement or optimisation |
| 3 | Reproduced: outcome matches the reported result |
| 2 | Deviation: partial reproduction with notable differences |
| 1 | Did not work: reaction failed |
| – | Inconclusive: unresolved outcome, not enough data |

## Running locally

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS / Linux:
source .venv/bin/activate

pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open `http://localhost:8000`. The dev login buttons let you test as a fake user without ORCID.

Set `ORCID_ENV=sandbox` and register a sandbox app at https://sandbox.orcid.org/developer-tools to test real ORCID login locally.

## Configuration

Copy `.env.example` to `.env` and fill in every value.

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | SQLite for local dev; PostgreSQL on production |
| `SECRET_KEY` | Yes | Random hex string, used for session signing |
| `ADMIN_SECRET_TOKEN` | Yes | Random hex string, used for admin login and HMAC-signed email links |
| `ORCID_CLIENT_ID` | Yes | From your ORCID developer app |
| `ORCID_CLIENT_SECRET` | Yes | From your ORCID developer app |
| `ORCID_REDIRECT_URI` | Yes | Must match the redirect URI registered with ORCID |
| `ORCID_ENV` | Yes | `sandbox` for development, `production` for live |
| `RESEND_API_KEY` | Yes | Resend API key for transactional email |
| `FEEDBACK_NOTIFY_EMAIL` | Yes | Address that receives feedback notifications |
| `ANTHROPIC_API_KEY` | No | Enables AI background content moderation (Haiku). Moderation still works without it via regex. |
| `SITE_URL` | No | Base URL used in email links and the same-origin POST check; defaults to `http://localhost:8000` |
| `LIBRARY_DIR` | Production | Folder for library uploads; on Railway a path on a mounted Volume, e.g. `/data/library` (default `library_files`) |
| `MAIL_POSTAL_ADDRESS` | No | Postal address in the footer of author notification emails |

Generate `SECRET_KEY` and `ADMIN_SECRET_TOKEN` with:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

## Deploying to Railway

1. Push to GitHub.
2. In Railway: New Project → Deploy from GitHub → select the repo.
3. Add a PostgreSQL service; Railway sets `DATABASE_URL` automatically.
4. In the web service Variables tab, add all required variables from the table above.
5. Set `ORCID_ENV=production` and register a production ORCID app at https://orcid.org/developer-tools with the Railway callback URL as the redirect URI.
6. Set `ORCID_REDIRECT_URI` to match: `https://your-app.railway.app/auth/callback`.
7. Attach a Volume to the web service (mount path `/data`) and set `LIBRARY_DIR=/data/library`; without it, library uploads are lost on every deploy.

## Content moderation

Reviews and comments pass through two layers before reaching the public:

1. **Regex blocklist** (synchronous): checked on every submit. Matches against a configurable list of banned terms managed at `/admin/banned-words`. Returns a 422 immediately if triggered; three violations on one paper result in an automatic submission ban for that paper.
2. **AI moderation** (asynchronous): runs in the background after a submission is saved. Uses Anthropic Claude Haiku to detect profanity, personal attacks, and defamation across any Latin-script language. Flagged content is queued for admin review and the submitter receives an inbox message. The AI layer fails open; if the API is unavailable the submission is kept and not auto-rejected.

## JSON API

All `/api/v1/` endpoints require a valid `X-API-Key` header. Keys are managed at `/admin/api-keys`. To request access, contact the maintainer.

| Endpoint | Description |
|----------|-------------|
| `GET /api/v1/papers` | List recently added papers with aggregated scores |
| `GET /api/v1/papers/{doi}` | Fetch a single paper by DOI |
| `GET /api/v1/papers/{doi}/ratings` | All approved reviews for a paper |
| `GET /api/v1/papers/{doi}/scores` | Aggregated score summary for a paper |

Example:

```bash
curl -H "X-API-Key: your-key" https://chemrepro.org/api/v1/papers/10.1038/nprot.2017.141
```

## Importing reviews in bulk

The `scripts/import_reviews.py` script lets you add reviews to the database from a JSON file. This is useful for seeding the platform with a corpus of curated reviews without going through the web form.

### JSON schema

```json
[
  {
    "target_doi": "10.1038/nprot.2017.141",
    "nd_star": 4,
    "nd_failure_context": null,
    "reproducibility_observation": "Reproduced Buchwald–Hartwig amination in 89% yield. [[10.1021/jacs.3c01234]] reports a similar scope extension.",
    "images": [
      { "uri": "data:image/png;base64,..." }
    ],
    "reviewer_nickname": "ChemRepro-Staff",
    "citing_author": "Jane Smith",
    "source_doi": "10.1021/acs.jmedchem.2c01646",
    "source_url": "https://doi.org/10.1021/acs.jmedchem.2c01646"
  }
]
```

| Field | Type | Notes |
|-------|------|-------|
| `target_doi` | string | DOI of the paper being reviewed |
| `nd_star` | 1–5 or null | See rating scale above |
| `nd_failure_context` | string or null | Required if `nd_star` is null; one of `"inconclusive"`, `"extension_failed"` |
| `reproducibility_observation` | string | Main review text. Supports `[[DOI]]` inline citations. |
| `images` | array | Optional. Each element: `{"uri": "data:image/png;base64,..."}` |
| `reviewer_nickname` | string | Display name for the review |
| `citing_author` | string | Author of the citing paper (source of the reproduction attempt) |
| `source_doi` | string | DOI of the citing paper |
| `source_url` | string | URL of the citing paper |

### Running the import

Dry run (validates and prints what would be imported without writing to the database):

```bash
.venv\Scripts\python.exe scripts\import_reviews.py reviews.json --dry-run
```

Import to the local SQLite database:

```bash
.venv\Scripts\python.exe scripts\import_reviews.py reviews.json
```

Import to the Railway PostgreSQL database:

```bash
$env:DATABASE_URL="postgresql+psycopg://user:pass@host:5432/dbname"
.venv\Scripts\python.exe scripts\import_reviews.py reviews.json
```

## Tech stack

FastAPI · SQLAlchemy · SQLite (dev) / PostgreSQL (prod) · Jinja2 · Tailwind CSS · Resend (email) · Anthropic (AI moderation) · Railway (hosting)
