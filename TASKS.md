# ChemRepro Tasks

## Memory & Logging Protocol
Two files keep project state persistent across sessions:
- **PROJECT_STATE.md** — always-current feature status, environment variables, scripts reference. Load at session start.
- **PUSHLOG.md** — append-only push record. Update before every git push.

**Rule:** Before ending any session, update PROJECT_STATE.md if anything changed. Before any push, add an entry to PUSHLOG.md.

This replaces the scattered memory files for project-specific state. The `.claude/memory/` files remain for personal feedback and cross-project decisions.

---

## Parked

### Push 2: Account Linking (ORCID ↔ LinkedIn)
Files ready locally, not yet pushed to GitHub.
- `app/models/user.py` — `linkedin_id` and `orcid_real` model fields (DB columns already exist from Push 1 migration)
- `app/routers/auth.py` — `/auth/link/linkedin`, `/auth/link/orcid` routes + modified OAuth callbacks; `/auth/dev-link/` already has production guard (`ORCID_ENV == production` → 403)
- `app/templates/base.html` — DEV panel (is_local guarded, invisible on Railway)
- `app/templates/profile_settings.html` — Linked accounts card in Settings

Prerequisites confirmed:
- LinkedIn OAuth credentials on Railway
- Orphaned LinkedIn ChemRepro account deleted via admin
- User has one ORCID-primary account; wants to attach LinkedIn to it

To deploy: review files locally, then push when ready.

---

## Future / Planned
See PROJECT_STATE.md "Planned / Deferred" section for the full list.
Notable items:
- Homepage pagination (currently shows only 10 reviews)
- Abstract expand/collapse (>3 rows)
- Personal reaction collection ("My Library")
- Scraper health check (daily email alert on failure)
- Non-profit legal entity (Switzerland)

### Email system: domain addresses
Now that Resend is in place and chemrepro.org is verified, set up proper domain email addresses:
- `admin@chemrepro.org` or `d.kovari@chemrepro.org` for receiving admin notifications
- Currently admin emails land in GMAIL_ADDRESS (the old Gmail account)
- Resend supports inbound email routing or forwarding — decide whether to use that or just change the TO address
- Also: GMAIL_ADDRESS / GMAIL_APP_PASSWORD on Railway are now only used as the recipient address, not for sending; could rename/clean up
