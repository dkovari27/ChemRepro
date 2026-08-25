# ChemRepro Tasks

## Memory & Logging Protocol
Two files keep project state persistent across sessions:
- **PROJECT_STATE.md** — always-current feature status, environment variables, scripts reference. Load at session start.
- **PUSHLOG.md** — append-only push record. Update before every git push.

**Rule:** Before ending any session, update PROJECT_STATE.md if anything changed. Before any push, add an entry to PUSHLOG.md.

This replaces the scattered memory files for project-specific state. The `.claude/memory/` files remain for personal feedback and cross-project decisions.

---

---

## HIGH PRIORITY

### [ACTION REQUIRED] AI-curated review paper access: verify with Nicola before any grant application
Before submitting any grant or funding application that references the AI-curated reviews (JACSAU, OrgSyn pipeline), confirm with Nicola that the source papers were accessible to him through the university system. This matters for academic integrity and IP: if a grant reviewer asks "how did you access these papers?", the answer must be "through a licensed institutional subscription", not "we scraped them or used a personal account". Do this check before any public grant filing, conference submission, or any document that formally cites this review corpus.

### Feedback form: required contact info for non-logged-in submitters
BUILT (Push 11): non-logged-in users are now required to provide name and email before submitting. Logged-in users (ORCID or LinkedIn) skip those fields. Both fields are stored on the `Feedback` model (`submitter_name`, `submitter_email`). Device tracking (`client_device`: "mobile" or "desktop") is also captured on every feedback submission and on every review submission; backend-only, never displayed publicly.

### SEO and LinkedIn discoverability: improve ranking
**Google:** page titles, meta descriptions, sitemap.xml, structured data (ScholarlyArticle/Review JSON-LD on paper pages), canonical tags across the three URL variants (/paper/, /classic/paper/, /nd/paper/), and registering on Google Search Console. Priority order: page titles and meta descriptions first (high impact, low effort), then sitemap.xml, then structured data, then canonical tags.

**LinkedIn:** beyond individual posts, consider: (1) a dedicated ChemRepro LinkedIn company page so the platform has a searchable presence; (2) using the LinkedIn post URL tracking (now built) to build a content calendar/archive; (3) tagging relevant journals, authors, and institutions in posts where appropriate (increases reach significantly on LinkedIn); (4) using consistent hashtags (#ChemRepro #OrganicChemistry #Reproducibility) to build topic authority over time.

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

### Email system: domain addresses
Now that Resend is in place and chemrepro.org is verified, set up proper domain email addresses:
- `admin@chemrepro.org` or `d.kovari@chemrepro.org` for receiving admin notifications
- Currently admin emails land in GMAIL_ADDRESS (the old Gmail account)
- Resend supports inbound email routing or forwarding — decide whether to use that or just change the TO address
- Also: GMAIL_ADDRESS / GMAIL_APP_PASSWORD on Railway are now only used as the recipient address, not for sending; could rename/clean up
