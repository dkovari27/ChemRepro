# ChemRepro — Task Tracker
_Last updated: 15 July 2026_

---

## ACTIVE — by priority

### 🔴 CRITICAL

- [x] **A6** — Automated daily backup to Google Drive. Script: `scripts/backup_to_gdrive.py`. Runs via GitHub Actions (`.github/workflows/backup.yml`) at 03:00 UTC daily. Keeps last 14 backups, prunes older ones automatically. Drive folder: `ChemRepro - Backup` (chemrepro@gmail.com). **Before pushing: add two GitHub secrets** — `DATABASE_URL` (Railway public URL) and `GDRIVE_TOKEN_JSON` (contents of `Backup/token.json`). Local credentials in `Backup/` are gitignored and must not be committed.

### 🟠 HIGH

- [x] **B16** — Literature scraper for implicit reproducibility data: crawl open-access chemistry papers (PubMed Central, Europe PMC, ChemRxiv, RSC Gold open-access) and detect sentences that follow patterns like "according to the procedure of X et al.", "following the method reported by", "adapted from", "as described in ref. X" — i.e. cases where an author explicitly states they replicated or adapted a published reaction. Scraper is built and running (as of 8 July 2026).

- [ ] **B17** — Wire scraped literature data into ChemRepro review cards. Full spec written to `SCRAPER_DATA_SPEC.md`. Key design decisions:
  - **Schema conflict**: `ratings` table has UNIQUE on `(doi, orcid_id, scoring_mode)` so a single system user can only produce one mined entry per paper. Recommendation: add a separate `literature_citations` table (no uniqueness constraint) and render as a distinct section on the paper page.
  - **Required scraper output fields**: `target_doi`, `citing_doi`, `citing_sentence`, `inferred_outcome`, `confidence_score`, `sentence_id` (dedup key), plus recommended metadata (`citing_authors`, journal, year, context sentence).
  - **Outcome-to-star mapping**: the import script will translate scraper outcomes (`reproduced`, `adapted`, `failed`, `partially_reproduced`) into `nd_star` 1-5 values for display.
  - **Quality thresholds for import**: confidence >= 0.75, sentence 30-500 chars, `target_doi` must resolve.
  - **Output format**: JSONL (newline-delimited JSON), with separate `rejected/` file for below-threshold rows and a `scrape_log` file per run.

- [x] **B18** — Career stage immutability: `career_stage_snapshot` column added to `ratings` table; snapshotted at submission time in `nd_submit_rating`; template shows snapshot (falls back to live user stage for old reviews). Nickname field in `profile_settings.html` is read-only once set; server-side lock in `profile.py` prevents bypass. Nickname changes require contacting chemrepro@gmail.com.

- [x] **B19** — "Report a bug" link below the "Submit rating" button on every paper page (`paper_nd.html`). Always visible (for logged-in and logged-out users). Routes to `/feedback?doi={doi}`; feedback page detects `doi` param and shows "Report a bug" heading with the DOI highlighted in amber, textarea pre-filled with `[DOI: ...]`.

- [x] **B20** — Thank-you toast: after review submission, redirect goes to `/paper/{doi}?submitted=1`; `nd_paper_page` passes `show_thanks=True`; paper template shows a green fixed-position toast with "Thank you for your contribution to open science!" that auto-dismisses after 4.5 s or on click.

- [ ] **B21** — Manual pre-publication review queue for misconduct/fraud allegations (referenced in ToS §3c): reviews flagged as misconduct allegations must be held pending admin approval before appearing publicly. Add a `pending_review` state to the rating, an admin queue page, and an approval/rejection flow with email notification to the submitter.

- [ ] **B22** — Escalated report path for defamatory content (ToS §4b): a distinct "report as defamatory" option separate from the general report button, routing to a 48–72 hour interim-hide queue. Admin receives high-priority alert; content submitter is notified and invited to substantiate.

- [ ] **B23** — Right-of-reply UI (ToS §4d, Privacy §3): an "Author response" field on the paper page, visible only to verified authors (ORCID iD matched against the paper's author list from CrossRef). Response displayed as a distinct card alongside the review it replies to.

- [ ] **B24** — Admin substantiation request tool (ToS §4c): admin can send a substantiation request to a reviewer from the review's admin page, with a configurable countdown (default 21 days). If no response is received, the review is automatically hidden and the admin is notified to make a final decision.

- [ ] **B11** — Activate author email notification (`AUTHOR_NOTIFY_ENABLED=true` in Railway `.env`) — disabled pending test that CrossRef/PMC/PubMed lookup works on real chemistry DOIs
- [ ] **B12** — Wire `notification_email` to SMTP sender — field is saved in Settings but never read; when a followed paper gets a new review/comment, send an email to `notification_email` if set
- [ ] **B14** — LinkedIn OAuth: routes + UI fully built, button shows "Coming soon". Before release: register app at developer.linkedin.com, set `LINKEDIN_CLIENT_ID` + `LINKEDIN_CLIENT_SECRET` + `LINKEDIN_REDIRECT_URI` in Railway `.env`, then restore button to active link.
- [ ] **C18** — ORCID button resting text is `text-slate-700` on all pages; LinkedIn "Coming soon" version is grey. Revisit once LinkedIn is activated: decide whether ORCID should use brand green `text-[#A6CE39]` or both stay neutral.

### 🟡 MEDIUM

- [ ] **C22** — Tour step review: (1) Is step 2 (community feed + rating explanation) necessary, or does it slow the flow? (2) Should step 2 better demonstrate the hover-over breakdown tooltip, e.g. by pre-opening it programmatically during the tour? (3) Is step 3 (score card on the paper page) redundant given step 2 already explains scoring? Consider merging or cutting.

- [ ] **B4/C9/D7** — Chemistry keyword/condition tags on rating form (Yield discrepancy, Purity issue, Safety concern…) — deferred, design not settled
- [ ] **C10** — Logo polish (current logo is placeholder)
- [x] **C20** — Migration script `scripts/fix_abstract_prefix.py` strips leading "Abstract" prefix from existing rows. Run locally or against Railway with `DATABASE_URL=... python scripts/fix_abstract_prefix.py`.

### 🔵 POST-LAUNCH

- [ ] **D16** — Resubscription: if a user who globally unsubscribed from ChemRepro emails later registers or logs in, offer a one-click opt back in (clear `global_opted_out` flag on their email hash). UI: show a dismissible banner on first login after opt-out, or a toggle in Profile Settings.

- [ ] **D18** — Granular email subscription preferences in Profile Settings. When a user enters their notification email, let them choose which types of emails they want to receive rather than all-or-nothing. Proposed categories: (1) new review on a paper I follow, (2) new comment on my review, (3) reply to my comment, (4) someone follows me, (5) author notification (paper I authored got reviewed), (6) ChemRepro platform announcements. Store as a JSON or bitmask field on the User model. UI: a checklist shown directly below the notification email field in settings, each category with a short label and a toggle/checkbox. Default: all on.

- [ ] **D17** — MCP server for ChemRepro API: wrap `/api/v1/` as an MCP server (separate Railway service or same app at `/mcp`) exposing named tools: `get_paper_score(doi)`, `list_recent_ratings(limit)`, `get_paper_ratings(doi)`. Requires: `fastapi-mcp` or custom MCP JSON-RPC handler, API key forwarding from the MCP client config, OpenAPI spec integration. Makes the dataset natively callable from Claude Desktop, Claude Code, and any MCP-compatible AI agent without the user writing HTTP calls.

- [ ] **D1** — Browser extension (Chrome + Firefox — parked)
- [ ] **D2** — Sketchit design review (do when feature set is stable)
- [ ] **D3** — Partnership outreach
  - organic-chemistry.org
  - orgsyn.org — priority: propose database cross-reference partnership
  - organicchemistrydata.org
- [ ] **D4** — Swiss non-profit legal setup
- [ ] **D4b** — Once non-profit entity is established and has a company bank account, add donation capability to the site (e.g. Stripe donate button or IBAN on About/Support page)
- [ ] **D5** — ORCID on production domain (register HTTPS redirect URI on orcid.org)
- [ ] **D6** — Personal reaction collection / "My Library" page
- [ ] **D8** — Zotero, Mendeley plugin
- [ ] **D10** — Terms of Service page (required before public launch; see privacy.html as style reference)
- [ ] **D14** — Review and edit the author notification email (body text, subject, sender name) before activating `AUTHOR_NOTIFY_ENABLED=true` in Railway. Currently placeholder wording. Check tone, legality (GDPR consent wording), and that opt-out links work end-to-end.
- [ ] **D15** — Review extraction agent: after a paper accumulates several reviews, an AI agent (Claude) reads all reviews, extracts: attempted conditions, substrate photos (if attached), what worked / what failed, and writes a short structured summary displayed on the paper page. Fire as a background task when review count hits a threshold (e.g. 3+).
- [ ] **D13** — Switch from Gmail SMTP to a transactional email service (Resend, SendGrid, or Brevo) with a custom domain (e.g. noreply@chemrepro.io) — eliminates spam-folder delivery risk. Gmail SMTP works today but new sender accounts have no reputation. Requires: buy domain, set up DNS (SPF/DKIM/DMARC), register with chosen provider, replace `smtp.gmail.com` calls in `app/utils/email.py` with provider SDK or relay config.
- [ ] **D12** — Registration pledge page: one-time ethics click-through shown after first login, before a user can submit a review. Inspired by Sage Bionetworks Synapse pledge (reference saved at `chemrepro/Sage Bionetworks Sign-in.mhtml`). 6 lab-ethics statements, each requiring individual "I agree" click; stored as `pledge_accepted` bool on User model. See memory `project_chemrepro_pledge.md` for proposed pledge wording.

---

## CURRENT STANDING (8 July 2026)

- **ChemRepro rating mode** fully implemented: `/` homepage, `/paper/{doi}` paper page, `nd_star` (1–5) + `nd_failure_context` (original_tested / extension_only), star filter + context filter, failure_context badge on 1-star reviews
- Standard mode filter fixed: `scoring_mode != "classic"` changed to `scoring_mode == "standard"` so ND reviews are isolated from standard averages
- API key management: all `/api/v1/` routes gated behind `X-API-Key` header; admin can generate/revoke keys; raw key shown once after generation; about page documents API access

---

## CURRENT STANDING (2 July 2026)

- Image paste / inline contenteditable on all text inputs sitewide (reviews, comments, replies, edit pages, message modal, inbox thread)
- Message thread renders markdown; images supported in DMs
- Classic view comments/replies stay in classic view after posting (A5 fixed)
- API v1 `avg_reproducibility` returns real outcome-based score 1–5 (F5 fixed)
- `render_md` filter registered globally via `register_globals()` — available in all routers
- No em dashes in any user-visible text (templates + author notification email)
- LinkedIn button shows "Coming soon" on all pages until credentials configured
- Admin access: `GET /admin/login/{ADMIN_SECRET_TOKEN}` — set real token in Railway `.env` before launch

---

## ARCHIVE

### Block A — Legal / Infrastructure
- [x] **A1** — Fix feedback email delivery (switched SMTP 465 → 587 STARTTLS)
- [x] **A2** — Add full postal address to `privacy.html`
- [x] **A3** — Railway DPA signed (DocuSign envelope 56122F5D)
- [x] **A4** — Server-side content moderation (`_is_clean()` regex blocklist; covers comments, ratings, messages)
- [x] **A5** — Classic view comment/reply routing: added `/classic/paper/{doi}/comment` and `/classic/paper/{doi}/comment/{parent_id}/reply` routes; updated form actions in `paper_classic.html`

### Block B — New Features
- [x] **B1** — Markdown comments with live preview
- [x] **B2** — Article alert subscriptions (Follow a paper; in-app notifications on new review/comment)
- [x] **B3** — Author email notification on new review (CrossRef → Europe PMC → PubMed; HMAC opt-out)
- [x] **B5** — Comment threading (likes + 1-level replies)
- [x] **B6** — Private in-mail messaging between users
- [x] **B7** — About page
- [x] **B8** — Social sharing popup (WhatsApp, Email, LinkedIn, Copy)
- [x] **B9** — User follow system; reviewer name dropdowns (Follow / Message / Report)
- [x] **B10** — v2 design; v1 archived
- [x] **B13** — Report mechanism with admin resolution
- [x] **B15** — Image upload/paste in all text inputs. Contenteditable replaces textarea for inline image rendering; `initDivFromMarkdown` loads pre-filled content on edit pages; JS served from `base.html` globally

### Block C — UX Polish
- [x] **C21** — Onboarding product tour: 5-step spotlight walkthrough shown once after first login, fires via `tour_pending` session flag → demo page. Built with vanilla JS + box-shadow spotlight + click shield.
- [x] **C1** — Footer cleanup
- [x] **C2** — Em dash sweep (privacy page, author notification email, all templates)
- [x] **C3** — Textarea sizing
- [x] **C4** — Spellcheck on all textareas
- [x] **C5** — Homepage sort order (by latest rating)
- [x] **C6** — Remove API link from nav
- [x] **C7** — Scoring explainer via hover tooltip
- [x] **C8** — Mobile: Classic tooltip overflow fix
- [x] **C11** — Like notification icon: 3/4-filled flask SVG (amber)
- [x] **C12** — Like button changed from heart to flask; comment likes same
- [x] **C13** — Feedback nav link restored
- [x] **C14** — Classic view card: "2 ratings" with correct pluralisation
- [x] **C15** — Standard view card: star before avg_score
- [x] **C16** — Nickname shown in nav after login
- [x] **C17** — Nickname field on first-login profile-setup page
- [x] **C19** — Image paste in message modal (paper.html, paper_classic.html) and inbox thread reply; message content renders via `render_md`

### Block D — Post-Launch (completed)
- [x] **D9** — Official website email address: `chemrepro@gmail.com` (sender + inbox); App Password configured in `.env` and Railway
- [x] **D11** — Admin dashboard at `/admin/` (secret-token login, no public surface)

### Block E — Feedback & Naming
- [x] **E1** — Tester feedback form
- [x] **E2** — Name-the-platform widget on feedback page

### Block F — Code Cleanup
- [x] **F1** — Remove dead `/design/{ver}` route
- [x] **F2** — Delete unused `search_results.html`
- [x] **F3** — Gate `/demo/colors` in production
- [x] **F4** — Extract `_BLOCKED_RE` to `app/utils/moderation.py`
- [x] **F5** — API v1 scoring: `avg_reproducibility` now uses outcome-based CASE expression (1–5); was always null for standard-mode papers. `render_md` moved to `app/utils/design.py` and registered via `register_globals()`.
- [x] **F8** — Fix `Rating` model default `"v2"` → `"standard"`

---

## Notes
- **B3 author emails**: CrossRef → Europe PMC → PubMed in order. Silently skips preprints and non-indexed papers — expected.
- **v1 templates** are read-only snapshots. Do not edit.
- **ADMIN_SECRET_TOKEN**: Set a real secret in Railway `.env` before public launch.
- **LinkedIn**: Connection count not available via LinkedIn API. For fake-account mitigation, gate review submission behind ORCID; LinkedIn for comments/follows only.

---

## AFTER TESTING PHASE: Clean up demo data

All seeded demo reviews, comments, and users are tagged with `is_demo = true` in the database.
Run these 5 SQL statements against the Railway PostgreSQL database (in order) to wipe them cleanly:

```sql
DELETE FROM comment_likes
  WHERE comment_id IN (
    SELECT id FROM comments
    WHERE orcid_id IN (SELECT orcid_id FROM users WHERE is_demo = true)
  );

DELETE FROM comments
  WHERE orcid_id IN (SELECT orcid_id FROM users WHERE is_demo = true);

DELETE FROM likes
  WHERE rating_id IN (SELECT id FROM ratings WHERE is_demo = true);

DELETE FROM ratings WHERE is_demo = true;

DELETE FROM users WHERE is_demo = true;
```

You can run these via the Railway database console, or via psql with the public DATABASE_URL.
