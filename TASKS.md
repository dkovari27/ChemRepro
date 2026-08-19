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

### RESOLVED 2026-08-11: review-edit forms skip the language check
Was: the initial review-submit endpoints called `is_clean()` before saving, but none of the three edit endpoints did. Fixed as part of the 3-warning moderation system rebuild: all submit/edit routes for reviews, comments, and replies (14 call sites total) now go through the shared `enforce_moderation()` gate in `app/utils/moderation.py`, including `edit_rating_submit`, `classic_edit_rating_submit`, and `nd_edit_rating_submit`.

### RESOLVED 2026-08-11: admin-flaggable banned words
Was: the banned-word list was a fixed regex baked into the code. Now: `BannedTerm` DB table + `/admin/banned-words` admin UI (add/delete), read live by `is_clean()`/`enforce_moderation()` on every check, no code deploy needed to add a word. Seeded 2026-08-11 with ~59 profanity slang/misspelling terms via `scripts/seed_banned_terms.py`.

### Content moderation: multi-language coverage (partially resolved)
`_BLOCKED_RE` in `app/utils/moderation.py` (the synchronous, instant regex check) is still English-only. The background Haiku check (`_check_content` in `ai_moderation.py`) has been updated to explicitly flag profanity/slurs in any Latin-script language and now also feeds it the live `get_banned_terms()` list, so async coverage is broad, but a non-English curse word won't get an instant 422/warning, only a delayed AI flag after the fact. Worth eventually giving the synchronous path multi-language coverage too if instant blocking in other languages matters.

### Content moderation: wildcard / fuzzy matching for curse words
Added 2026-08-11: the banned-term matcher (`_custom_terms_re` in `app/utils/moderation.py`) only does literal whole-word matching. It won't catch spaced-out ("f u c k"), symbol-substituted ("f*ck", "sh!t"), or repeated-letter ("fuuuck") variants, only exact strings we've explicitly listed (see `scripts/seed_banned_terms.py` for the current ~59-term seed list). Worth revisiting with a proper fuzzy/wildcard matching approach (e.g. character-normalization before matching, or a Levenshtein-distance check against the base word list) if evasion becomes a real problem in practice.

### Banned words admin page: alphabetical order
`/admin/banned-words` currently lists terms newest-first (`BannedTerm.created_at.desc()` in `admin.py`'s `admin_banned_words` route). Switch to alphabetical (`BannedTerm.term.asc()`, same ordering `get_banned_terms()` already uses internally) so a long list is easy to scan/check for duplicates.

### Admin dashboard: style update
The admin dashboard has grown a lot of sections (reviews, comments, reports, LinkedIn drafts, users, banned words, submission warnings, name votes) with inconsistent card/table styling picked up piecemeal over many pushes. Worth a dedicated pass to unify the visual design once the feature set settles down.

### SEO and Google discoverability
ChemRepro is not easily findable via Google at the moment. Things worth investigating and implementing:
- `<meta name="description">` on every public page (especially paper pages and the homepage); currently absent
- Structured data / JSON-LD: `ScholarlyArticle` or `Review` schema on paper pages so Google can show rich snippets
- `sitemap.xml`: a dynamic endpoint that lists every `/paper/{doi}` URL with `<lastmod>` so Googlebot can crawl efficiently rather than relying on link discovery
- `robots.txt`: ensure admin pages and other non-public routes are excluded, and that public pages are explicitly allowed
- Canonical `<link rel="canonical">` tags on paper pages (three URL variants for the same paper: `/paper/`, `/classic/paper/`, `/nd/paper/`) to avoid duplicate-content dilution
- Page titles: paper pages currently use the full DOI as the tab title, which is meaningless to search engines; should be `{paper title} | ChemRepro`
- Open Graph / Twitter Card tags on paper pages so shares show a meaningful preview
- Internal linking: paper pages don't link to each other or back to the homepage in a way Googlebot can follow efficiently
- Google Search Console: register and verify the domain, submit the sitemap, monitor indexing status

Priority order (rough): page titles and meta descriptions first (high impact, low effort), then sitemap.xml, then structured data, then canonical tags.

### Email system: domain addresses
Now that Resend is in place and chemrepro.org is verified, set up proper domain email addresses:
- `admin@chemrepro.org` or `d.kovari@chemrepro.org` for receiving admin notifications
- Currently admin emails land in GMAIL_ADDRESS (the old Gmail account)
- Resend supports inbound email routing or forwarding — decide whether to use that or just change the TO address
- Also: GMAIL_ADDRESS / GMAIL_APP_PASSWORD on Railway are now only used as the recipient address, not for sending; could rename/clean up
