# ChemRepro: Project State
<!-- Updated: 2026-08-17. Update this file at the end of every session or before every push. -->

## Stack
- FastAPI + Jinja2 + SQLAlchemy ORM
- SQLite locally, PostgreSQL on Railway (production)
- Tailwind CSS, vanilla JS
- Hosted: chemrepro.org (Railway)
- Repo: GitHub (main branch = production)

---

## Feature Status

### Auth & Identity
| Feature | Status | Notes |
|---|---|---|
| ORCID login | LIVE | Sandbox locally, production on Railway |
| LinkedIn login | LIVE | Credentials on Railway; works in production |
| Guest login | LOCAL ONLY | Button shown under `{% if is_local %}` guard; `guest_setup.html` template missing (404 on click) — deferred |
| Account linking (ORCID ↔ LinkedIn) | LIVE (Push 2) | `ef7e9e8`; verified working in production 2026-08-07 |
| Nickname: live uniqueness check | LIVE (Push 1) | Debounced JS fetch to `/profile/nickname-check`, green "Available" indicator, suggestion chips |
| Nickname: server-side check | LIVE (Push 1) | Profile settings POST checks conflict; profile setup POST also checks (auth.py submit_profile_setup) |

### Review System
| Feature | Status | Notes |
|---|---|---|
| Non-misconduct (ND) review form | LIVE | Star ratings, failure context, career stage |
| Classic review form | LIVE | Dual star scores |
| Substantiation request (admin) | LIVE | 14-day deadline, email to reviewer, deadline check on admin page load |
| Review editing | LIVE | Owner + admin can edit AI-submitted reviews |
| AI content moderation | LIVE | Haiku SAFE/FLAG on submit; flags hide review and send inbox message to reviewer |
| Citation resolver | LOCAL SCRIPT | `scripts/resolve_citations.py` — runs Haiku+Sonnet via Claude Code CLI (`claude -p`); no API key needed; scans for unresolved bibliographic citations; sends admin email with approve/dismiss buttons |

### AI Reviewer Pipeline (Scrapers)
| Component | ORCID ID | Status | Notes |
|---|---|---|---|
| JACSAU | `AI-JACSAU` | ACTIVE | AI reviewer for JACS/ACS papers; reviews imported via `scripts/import_reviews.py --ai-name JACSAU` |
| OrgSyn | `AI-OrgSyn` | ACTIVE | AI reviewer for Organic Syntheses papers |
| Import script | `scripts/import_reviews.py` | STABLE | Bulk-imports reviews from JSON; creates AI user profile automatically; runs citation resolver on newly imported reviews; supports `--dry-run` and `--railway` flags |
| Career stage for AI reviewers | "Data curation agent" | LIVE | Set in `AI_CAREER_STAGE` constant in import_reviews.py |

**How to run a scraper import (Railway):**
```
set DATABASE_URL=postgresql://postgres:PASSWORD@acela.proxy.rlwy.net:17700/railway
python scripts/import_reviews.py reviews.json --ai-name JACSAU
python scripts/resolve_citations.py --railway --ai-name JACSAU
```

### Admin Dashboard
| Feature | Status | Notes |
|---|---|---|
| LinkedIn post draft generator | LIVE (Push 1) | Haiku background task on review submit; two-column card (original review left, draft right); Copy + Regenerate buttons |
| LinkedIn post: mock mode | ON | `MOCK_SCORING=true` in local .env; returns "test test test"; disable before real use (~$0.002/post with Haiku) |
| Citation approval | LIVE | HMAC-verified one-click approve/dismiss from email; `/admin/citation-approve` and `/admin/citation-dismiss` |
| Substantiation deadline check | LIVE | Runs on every admin page load; sends `notify_admin` email when deadline passes; nulls deadline after firing |
| **Admin sidebar redesign** | **LIVE (Push 9)** | New `admin_base.html` shell: left sidebar nav (Dashboard/Users/Papers/API Keys/Banned Words/Warnings/Name Votes) replaces the old top-button row on every admin page. Admin pages now go full-width (`base.html`'s `main_class` block override) instead of being squeezed into the site's normal `max-w-5xl` column. |
| **API Keys: own page** | **LIVE (Push 9)** | Moved off the dashboard onto `/admin/api-keys` (`admin_api_keys.html`); dashboard route no longer queries `api_keys`. |
| **Users: own page** | **LIVE (Push 9)** | Moved off the dashboard onto `/admin/users` (`admin_users.html`, incl. edit modal + Ban/Delete actions); dashboard route no longer queries `all_users`/`recent_users` (the latter was dead code anyway). |
| **Papers: new browse page** | **LIVE (Push 9)** | `/admin/papers` (`admin_papers.html`): table of every looked-up paper with review/comment counts, live client-side filter, sortable by oldest/most-reviews/most-searches/most-views. `Paper.search_count`/`view_count` columns added (migrated, default 0); incremented in `/search` and all three paper-detail routes. Counts only accrue from 2026-08-11 onward, no historical backfill. |
| **XSS fix: onsubmit-confirm pattern** | **LIVE (Push 9)** | `admin_name_votes.html`'s delete-suggestion form had the same `onsubmit="return confirm('...{{ var }}...')"` injection bug fixed elsewhere in Push 8 (`s.name` interpolated into a JS string); converted to the `data-confirm` pattern. |

### Security Hardening (Push 9)
| Fix | Status | Notes |
|---|---|---|
| Open redirect: pledge page | LIVE (Push 9) | `pledge.py`'s `_safe_next()` restricts `?next=` to relative paths; also rejects `/\host` (browsers normalise a leading backslash to `//`, which would otherwise bypass the `//host` check). |
| Dev-login sandbox lockdown | LIVE (Push 9) | `auth.py`'s `/dev-login/{i}` and dev-link route now require `ORCID_ENV == "sandbox"` exactly (was: blocked only when `== "production"`), matching the fail-closed convention already used everywhere else (`main.py`, `papers.py`, `is_local`). |
| Admin auth consolidation: /admin/feedback | LIVE (Push 9) | Was `if ORCID_ENV == "production": 403`, i.e. no auth check at all locally and hard-blocked for the admin in production. Now uses the shared `_require_admin()` like every other admin route. |
| Stored XSS: author notification email | LIVE (Push 9) | `author_notify.py` now HTML-escapes paper title and review URL before building the notification email body. |
| Image upload validation | LIVE (Push 9) | `images.py` verifies uploaded bytes actually match the declared MIME type (rejects spoofed `Content-Type`), guards against Pillow decompression bombs, adds `X-Content-Type-Options: nosniff` on image serving. |
| Tracking pixel in reviews | LIVE (Push 9) | `design.py`'s markdown image-src allowlist restricted to `/images/` (ChemRepro's own upload path); external `https://` image embeds, which let a review silently phone home to a third party on view, are no longer allowed. |
| Report target-id parsing | LIVE (Push 9) | `reports.py` catches a non-numeric `target_id` and returns 422 instead of an unhandled 500. |
| LinkedIn draft anti-hallucination rule | LIVE (Push 9) | Prompt now explicitly forbids stating any chemical detail/condition/scope claim not present in `observation_excerpt` or paper metadata; added as checklist item 12. |
| Moderation content-label wiring | LIVE (Push 9) | `data-content-label` added to every review/comment/reply/name form so the client-side moderation warning modal says "review"/"comment"/etc. instead of the generic "submission" fallback; Classic paper's comment-reply form also gained `data-moderate` (previously fell through to a native full-page submit instead of the in-place AJAX flow every sibling form uses). |

### Notifications & Email
| Feature | Status | Notes |
|---|---|---|
| Author notification on review | LIVE but OFF | `AUTHOR_NOTIFY_ENABLED=False` by default; scrapes CrossRef/EuropePMC/PubMed for corresponding author email |
| Admin notify on new review | LIVE | `ADMIN_NOTIFY_ENABLED=True` by default — fires locally if Gmail credentials are in .env; no is_local guard |
| Subscriber alerts | LIVE | Paper and user follow subscriptions send email notifications |

### Profile & Settings
| Feature | Status | Notes |
|---|---|---|
| Settings page | LIVE (Push 2) | Full P2 version: nickname, career stage, notification email, linked accounts card |
| Linked accounts card | LIVE (Push 2) | ORCID-primary: Connect LinkedIn; LinkedIn-primary: Connect ORCID; guest accounts excluded |

### Planned / Deferred
| Feature | Status | Notes |
|---|---|---|
| Account linking | DONE | Push 2, `ef7e9e8`, verified 2026-08-07 |
| Personal reaction collection ("My Library") | PLANNED | |
| Comment threading with likes/replies | PLANNED | 1 level deep |
| Private in-mail messaging | PLANNED | |
| Homepage pagination | PLANNED | Currently shows 10 reviews only |
| Abstract truncation (expand/collapse) | PLANNED | >3 rows |
| Scoring explainer | PLANNED | |
| Keyword tags on papers | PLANNED | |
| Content filter (client + server blocklist) | PLANNED | |
| Scraper health check | PLANNED | Daily morning check + email alert on failure |
| Non-profit legal entity (Switzerland) | PLANNED | Guide at chemrepro/Non-Profit Switzerland Guide (Claude).docx |

---

## Environment Variables (key ones)
| Variable | Local | Railway |
|---|---|---|
| `ORCID_ENV` | `sandbox` | `production` |
| `MOCK_SCORING` | `true` | `false` (set before enabling Haiku features) |
| `ADMIN_NOTIFY_ENABLED` | `True` (default) | `True` — fires real emails; no local guard |
| `AUTHOR_NOTIFY_ENABLED` | `False` (default) | `False` — must explicitly enable |
| `LINKEDIN_CLIENT_ID/SECRET` | set locally | set on Railway |
| `ANTHROPIC_API_KEY` | set locally | set on Railway |
| `RESEND_API_KEY` | not set (emails skip locally) | set on Railway |
| `MAIL_FROM` | default `ChemRepro <noreply@chemrepro.org>` | same |
| `GMAIL_ADDRESS / APP_PASSWORD` | set locally | set on Railway (GMAIL_ADDRESS = admin recipient; APP_PASSWORD no longer used for sending) |

---

## Key Constraints (apply everywhere)
- Never use em dashes (— / &mdash;). Use comma, semicolon, or colon.
- Never push to GitHub automatically. Always wait for explicit user instruction.
- DEV-only features always wrapped in `{% if is_local %}` (template) or `settings.ORCID_ENV == "production"` → 403 (router).

---

## Scripts Reference
| Script | Purpose | Run context |
|---|---|---|
| `scripts/import_reviews.py` | Bulk-import AI or user reviews from JSON | Local or Railway |
| `scripts/resolve_citations.py` | Detect and flag unresolved bibliographic citations | Local (Claude Code CLI required) |
| `scripts/backup_to_gdrive.py` | Database backup to Google Drive | Local/Railway |
| `scripts/clear_my_test_ratings.py` | Remove test reviews by a specific ORCID | Local/Railway |
| `scripts/fix_abstract_prefix.py` | Fix malformed abstract prefixes from CrossRef | One-off |
| `scripts/migrate_standard_to_nd.py` | Migrate old standard reviews to ND format | One-off |
| `seed_demo.py` | Seed demo paper with Standard + Classic reviews | Local only |
