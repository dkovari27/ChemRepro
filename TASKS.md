# ChemRepro Tasks

## Memory & Logging Protocol
Two files keep project state persistent across sessions:
- **PROJECT_STATE.md** — always-current feature status, environment variables, scripts reference. Load at session start.
- **PUSHLOG.md** — append-only push record. Update before every git push.

**Rule:** Before ending any session, update PROJECT_STATE.md if anything changed. Before any push, add an entry to PUSHLOG.md.

This replaces the scattered memory files for project-specific state. The `.claude/memory/` files remain for personal feedback and cross-project decisions.

---

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
