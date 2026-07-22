# ChemRepro — Task Tracker
_Last updated: 16 July 2026_

---

## HOW TO IMPORT AI REVIEWS TO PRODUCTION (OrgSyn / Scraper batches)

1. Prepare a JSON batch file with the scraper agent (e.g. `scripts/orgsyn_reviews_batch2.json`)
2. Open a terminal in the `chemrepro/` directory
3. Set the Railway database URL for this session (get the current URL from Railway > PostgreSQL > Connect):
   ```powershell
   $env:DATABASE_URL = "postgresql://postgres:<password>@acela.proxy.rlwy.net:17700/railway"
   ```
4. Dry run first:
   ```powershell
   python scripts/import_reviews.py scripts/orgsyn_reviews_batch2.json --ai-name OrgSyn --dry-run
   ```
5. Check the output: all 4 columns (Inserted / Skipped / Failed) and verify titles look correct
6. Live import:
   ```powershell
   python scripts/import_reviews.py scripts/orgsyn_reviews_batch2.json --ai-name OrgSyn
   ```

Note: `DATABASE_URL` in `.env` stays as SQLite for local dev; the env var set in step 3 overrides it only for that terminal session.

---

## ACTIVE — by priority

### HIGH

- [x] **B17** — Wire scraped literature data into ChemRepro review cards. Full spec written to `SCRAPER_DATA_SPEC.md`. Key design decisions:
  - **Schema**: add a separate `literature_citations` table (no uniqueness constraint), render as distinct section on paper page
  - **Required fields**: `target_doi`, `citing_doi`, `citing_sentence`, `inferred_outcome`, `confidence_score`, `sentence_id` (dedup key)
  - **Outcome mapping**: `reproduced` / `adapted` / `failed` / `partially_reproduced` → `nd_star` 1-5
  - **Import thresholds**: confidence >= 0.75, sentence 30-500 chars, `target_doi` must resolve
  - **Output format**: JSONL, with `rejected/` file and `scrape_log` per run
  - _Scraper pipeline complete; wiring to DB and paper page covered by this task being done._

- [ ] **B11** — Activate author email notification (`AUTHOR_NOTIFY_ENABLED=true` in Railway `.env`) — disabled pending test that CrossRef/PMC/PubMed lookup works on real chemistry DOIs.
- [ ] **B12** — Wire `notification_email` to SMTP sender: field is saved in Settings but never read. When a followed paper gets a new review/comment, send email to `notification_email` if set.
- [ ] **B14** — LinkedIn OAuth: routes + UI built, button shows "Coming soon". Register app at developer.linkedin.com, set credentials in Railway `.env`, restore button.
- [ ] **C18** — ORCID button colour: revisit once LinkedIn is activated — decide `text-[#A6CE39]` brand green vs neutral grey for both buttons.

- [ ] **C25** — Add AI seed data disclosure to the About page (general, not OrgSyn-only: covers all open-access journals used as seed sources). See draft copy below. Homepage feed label: TBD — under consideration (noted with `?` in plan).

  **Draft copy for About page (section: "Where does the seed data come from?"):**

  > ChemRepro was seeded with AI-generated reviews to give the platform meaningful content from day one. These reviews are automatically extracted from publicly accessible, open-access chemistry publications, including OrgSyn, JACS-Au, and other open-access journals, using a structured pipeline that identifies reproducible experimental procedures and classifies outcomes. All AI-sourced reviews are clearly attributed to a named AI account (e.g. AI-OrgSyn, AI-JACSAU) and are visually distinct from community-contributed reviews. The seed data exists as a starting point: the long-term value of ChemRepro comes from verified synthetic chemists sharing their own first-hand lab experience on top of it. If you ran one of these procedures and have something to add, we invite you to leave your own rating.

  **Homepage feed label (?):** A one-line attribution under the "Recently rated papers" heading, e.g. "Includes AI-sourced seed reviews from open-access publications." Low-visibility, no banner. Under consideration — not yet decided.

### MEDIUM

- [x] **C23** — Homepage pagination: `?page=N` on `nd_index`; 10 per page; prev/next controls + "X-Y of Z" counter in `index_nd.html`.
- [x] **C24** — Abstract truncation on paper page: CSS `line-clamp-3` on the abstract block in `paper_nd.html`, with a JS "Show more / Show less" toggle button; only show button when rendered height exceeds the clamp threshold.
- [x] **G9** — Citation resolver: `scripts/resolve_citations.py` (Haiku detect, CrossRef search, Sonnet pick); flags formatted bibliographic citations via admin email (Approve / Resolve manually / Dismiss buttons). Text is NEVER changed automatically. Run locally with `--railway` flag.
  - **Category A** (active): detects formatted bibliographic citations like "J. Org. Chem. 2022, 87, 1234".
  - **Category B** (disabled): detected author-name phrases like "Smith et al.", "Njardarson and co-workers". Disabled because it produced false positives (e.g. resolving an author's name to the reviewed paper's own DOI). The code is preserved in `resolve_citations.py` comments; may be re-enabled with a narrower prompt and manual-review-only flow.
  - **Runtime (current)**: uses Claude Code CLI (`claude -p`) via Pro subscription. No API key needed. Must be run locally — not wired into Railway background tasks.
  - **Future option**: switch to Anthropic API (`anthropic.Anthropic(api_key=...)`) to allow running on Railway automatically after each submission. Would require `ANTHROPIC_API_KEY` in Railway env and a `resolve_rating_bg` background task in `papers.py`. Cost estimate: ~$0.001 per review that contains a formatted citation.
- [ ] **B4** — Chemistry keyword/condition tags on rating form (Yield discrepancy, Purity issue, Safety concern...) — design not settled.
- [ ] **C10** — Logo polish (current logo is placeholder).

### POST-LAUNCH

- [ ] **D16** — Resubscription: offer one-click opt-in banner after first login following a global opt-out.
- [ ] **D18** — Granular email subscription preferences in Profile Settings (per notification category, stored as JSON or bitmask on User).
- [ ] **D17** — MCP server: wrap `/api/v1/` as MCP server exposing `get_paper_score(doi)`, `list_recent_ratings(limit)`, `get_paper_ratings(doi)`.
- [ ] **D1** — Browser extension (Chrome + Firefox — parked)
- [ ] **D2** — Design review (do when feature set is stable)
- [ ] **D3** — Partnership outreach: organic-chemistry.org, orgsyn.org (priority: database cross-reference), organicchemistrydata.org
- [ ] **D4** — Swiss non-profit legal setup
- [ ] **D4b** — Donation capability once non-profit bank account exists
- [ ] **D5** — ORCID OAuth on production domain (register HTTPS redirect URI on orcid.org)
- [ ] **D6** — Personal reaction collection / "My Library" page
- [ ] **D8** — Zotero / Mendeley plugin
- [ ] **D10** — Terms of Service page (required before public launch)
- [ ] **D12** — Registration pledge page: one-time ethics click-through after first login. 6 lab-ethics statements with individual "I agree"; stored as `pledge_accepted` on User. Reference: `chemrepro/Sage Bionetworks Sign-in.mhtml`.
- [ ] **D13** — Switch from Gmail SMTP to transactional email (Resend / SendGrid / Brevo) with custom domain.
- [ ] **D14** — Review and edit author notification email body before activating `AUTHOR_NOTIFY_ENABLED`.
- [ ] **D15** — Review extraction agent: after 3+ reviews, Claude summarises conditions, outcomes, and what failed; displayed as structured summary on paper page.

---

## MIGRATION PLAN: Railway → Own server + managed DB

**Target stack:**
- App: Hetzner CAX11 VPS (€4/month, 2 vCPU ARM, 4 GB RAM, Falkenstein)
- DB: Neon managed PostgreSQL (free tier: 0.5 GB; $19/month if outgrown)
- Web server / TLS: Caddy (automatic Let's Encrypt, two-line config)
- Container runtime: Docker + Docker Compose
- Backups: extend existing GitHub Actions script (A6) to also dump the `/images/` directory
- Domain: register `chemrepro.org` at Cloudflare Registrar (~$10/year)
- **Total: ~€4/month vs €5/month now, with full control**

**Track A (interim, optional):** Add custom domain to Railway only — no server move. DNS CNAME to Railway, update `SITE_URL`, register ORCID OAuth production redirect URI. ~2 hours. Zero penalty if you later move to Track B; DNS just gets pointed elsewhere.

**Track B (full migration):**

1. Register domain at Cloudflare. Point A record to Hetzner IP once server is up.
2. Provision Hetzner CAX11. Install Docker + Docker Compose + Caddy.
3. Create Neon project, copy connection string.
4. Migrate DB:
   - `pg_dump "postgresql://...railway..." > chemrepro_backup.sql`
   - `psql "postgresql://...neon..." < chemrepro_backup.sql`
5. Copy app to server (git pull or rsync). Write `docker-compose.yml` with `app` service + Caddy.
6. Set all env vars: `DATABASE_URL` (Neon), `SITE_URL`, `ANTHROPIC_API_KEY`, `SMTP_*`, `ADMIN_SECRET_TOKEN`, `HMAC_SECRET`.
7. Register ORCID OAuth production redirect URI: `https://chemrepro.org/auth/orcid/callback`.
8. Update DNS A record. Keep Railway running 24-48 h in parallel for propagation.
9. Shut down Railway once traffic confirms new server is healthy.

**Image storage note:** Images are already stored in the `uploaded_images` table as `LargeBinary` in PostgreSQL (not on the filesystem). The `pg_dump` in step 4 includes them automatically. No separate image migration needed.

---

- [ ] **I1** — Migrate image storage from DB (`LargeBinary`) to Cloudflare R2 when image volume grows. Images are already stored in the `uploaded_images` table as raw bytes (Option A already in place — no filesystem involved, covered by `pg_dump`). Migration to R2 (Option C) when ready:
  - Script reads every row from `uploaded_images`, uploads to R2 with the same UUID as the object key
  - Serve endpoint switches from DB read to R2 redirect or direct URL
  - Stored Markdown references (`![](/images/<uuid>)`) do not need to change
  - Estimated effort: 2-3 hours when the time comes; no urgency until image volume is meaningful

---

## CURRENT STANDING (16 July 2026) — content moderation suite

- **B21 Misconduct queue**: reviews containing fraud/fabrication/plagiarism keywords auto-held as `pending_admin_review=True`. Admin sees dedicated "Pending Review Queue" on dashboard with Approve/Reject buttons. Reviewer receives inbox message while under review. On approve: review published + notification. On reject: review deleted + notification.
- **B22 Defamatory report path**: "Report as defamatory" checkbox in the report modal. On submit: content immediately hidden (`ai_flagged=True`), URGENT admin email, inbox message to content author. Admin resolves via existing Restore/Delete in the AI Flagged section. Defamatory reports show red DEFAMATORY badge in Open Reports table.
- **B23 Author right of reply**: backend routes + model built and ready (`/paper/{doi}/ratings/{id}/author-reply`, `AuthorReply` model). UI removed: author identity cannot be verified reliably via CrossRef (ORCID linkage inconsistent). Parked until a better verification strategy is decided.
- **B24 Admin substantiation tool**: "Subst." button per review row in admin dashboard. On click: review immediately hidden (`ai_flagged=True`), formal inbox message sent to reviewer with 14-day deadline. Admin restores via existing Restore button if satisfied with evidence. Overdue check runs on dashboard load: auto-emails admin when deadline passes with no action.
- **B25 Railway env vars**: `SITE_URL` and `ANTHROPIC_API_KEY` must be set in Railway Variables tab before deploying.
- **B26 Admin notification emails**: `notify_admin()` utility sends `[ChemRepro]`-prefixed email to `chemrepro@gmail.com` for: new reviews, new comments, AI-flagged content, standard reports, defamatory reports (URGENT), misconduct queue events. Gated by `ADMIN_NOTIFY_ENABLED` env var. Feedback already had its own sender.

## CURRENT STANDING (16 July 2026) — AI moderation

- **AI moderation pipeline** live: Claude Haiku checks every new review in background; client-side blocklist (`moderation.js`) as Layer 1. Flagged reviews: `ai_flagged=True` — hidden from public, excluded from star aggregates, author receives inbox message + notification bell. Author sees their own flagged review with amber warning banner and "Edit and resubmit" button. On edit: flag cleared, review reappears, re-moderation runs automatically.
- **AI scraper profiles**: `AI-[scraper]` pseudo-accounts (e.g. AI-OrgSyn) auto-created by `scripts/import_reviews.py --ai-name OrgSyn`. Admin can edit their reviews on paper page and admin dashboard.
- **Bulk review import**: `python scripts/import_reviews.py --file reviews.json --ai-name OrgSyn [--dry-run]`. Schema in `scripts/import_reviews_example.json`.
- **Admin user edit modal** on admin dashboard: name, nickname, career stage editable for any user; AI badge shown for AI-prefix accounts.

---

## CURRENT STANDING (8 July 2026)

- **ChemRepro rating mode** fully implemented: `/` homepage, `/paper/{doi}` paper page, `nd_star` (1-5) + `nd_failure_context` (original_tested / extension_only), star filter + context filter, failure_context badge on 1-star reviews
- Standard mode filter fixed: `scoring_mode != "classic"` changed to `scoring_mode == "standard"` so ND reviews are isolated from standard averages
- API key management: all `/api/v1/` routes gated behind `X-API-Key` header; admin can generate/revoke keys; raw key shown once after generation

---

## CURRENT STANDING (2 July 2026)

- Image paste / inline contenteditable on all text inputs sitewide
- Message thread renders markdown; images supported in DMs
- Classic view comments/replies stay in classic view after posting (A5 fixed)
- API v1 `avg_reproducibility` returns real outcome-based score 1-5 (F5 fixed)
- `render_md` filter registered globally via `register_globals()`
- No em dashes in any user-visible text
- LinkedIn button shows "Coming soon" on all pages until credentials configured
- Admin access: `GET /admin/login/{ADMIN_SECRET_TOKEN}`

---

## ARCHIVE

### Block A — Legal / Infrastructure
- [x] **A1** — Fix feedback email delivery (switched SMTP 465 to 587 STARTTLS)
- [x] **A2** — Add full postal address to `privacy.html`
- [x] **A3** — Railway DPA signed (DocuSign envelope 56122F5D)
- [x] **A4** — Server-side content moderation (`_is_clean()` regex blocklist; covers comments, ratings, messages)
- [x] **A5** — Classic view comment/reply routing: added `/classic/paper/{doi}/comment` and `/classic/paper/{doi}/comment/{parent_id}/reply` routes; updated form actions in `paper_classic.html`
- [x] **A6** — Automated daily backup to Google Drive. Script: `scripts/backup_to_gdrive.py`. Runs via GitHub Actions at 03:00 UTC daily. Keeps last 14 backups. Drive folder: `ChemRepro - Backup` (chemrepro@gmail.com).

### Block B — New Features
- [x] **B1** — Markdown comments with live preview
- [x] **B2** — Article alert subscriptions (Follow a paper; in-app notifications on new review/comment)
- [x] **B3** — Author email notification on new review (CrossRef + Europe PMC + PubMed; HMAC opt-out)
- [x] **B5** — Comment threading (likes + 1-level replies)
- [x] **B6** — Private in-mail messaging between users
- [x] **B7** — About page
- [x] **B8** — Social sharing popup (WhatsApp, Email, LinkedIn, Copy)
- [x] **B9** — User follow system; reviewer name dropdowns (Follow / Message / Report)
- [x] **B10** — New design (ND) rating mode; v1 archived
- [x] **B13** — Report mechanism with admin resolution
- [x] **B15** — Image upload/paste in all text inputs
- [x] **B16** — Literature scraper for implicit reproducibility data: phrase detection pipeline crawling open-access chemistry papers for "according to the procedure of", "following the method reported by", etc.
- [x] **B18** — Career stage immutability: `career_stage_snapshot` column snapshotted at submission; nickname locked after first set.
- [x] **B19** — "Report a bug" link below Submit button on every paper page.
- [x] **B20** — Thank-you toast after review submission (green, 4.5 s auto-dismiss).

### Block C — UX Polish
- [x] **C1** — Footer cleanup
- [x] **C2** — Em dash sweep (privacy page, author notification email, all templates)
- [x] **C3** — Textarea sizing (rows increased to 6)
- [x] **C4** — Spellcheck on all textareas
- [x] **C5** — Homepage sort order (by latest rating date)
- [x] **C6** — Remove API link from nav
- [x] **C7** — Scoring explainer via hover tooltip
- [x] **C8** — Mobile: Classic tooltip overflow fix
- [x] **C11** — Like notification icon: 3/4-filled flask SVG (amber)
- [x] **C12** — Like button changed from heart to flask
- [x] **C13** — Feedback nav link restored
- [x] **C14** — Classic view card: "2 ratings" with correct pluralisation
- [x] **C15** — Standard view card: star before avg_score
- [x] **C16** — Nickname shown in nav after login
- [x] **C17** — Nickname field on first-login profile-setup page
- [x] **C19** — Image paste in message modal and inbox thread; content renders via `render_md`
- [x] **C20** — Migration script `scripts/fix_abstract_prefix.py` strips leading "Abstract" prefix from existing rows.
- [x] **C21** — Onboarding product tour: 5-step spotlight walkthrough, vanilla JS + box-shadow spotlight.

### Block D — Post-Launch (completed)
- [x] **D9** — Official website email address: `chemrepro@gmail.com`; App Password configured.
- [x] **D11** — Admin dashboard at `/admin/` (secret-token login, no public surface).

### Block E — Feedback & Naming
- [x] **E1** — Tester feedback form
- [x] **E2** — Name-the-platform widget on feedback page

### Block F — Code Cleanup
- [x] **F1** — Remove dead `/design/{ver}` route
- [x] **F2** — Delete unused `search_results.html`
- [x] **F3** — Gate `/demo/colors` in production
- [x] **F4** — Extract `_BLOCKED_RE` to `app/utils/moderation.py`
- [x] **F5** — API v1 `avg_reproducibility` now uses outcome-based CASE expression; `render_md` moved to `app/utils/design.py` and registered via `register_globals()`.
- [x] **F8** — Fix `Rating` model default `"v2"` to `"standard"`

### Block H — Content Moderation Suite (16 July 2026)
- [x] **B21** — Manual pre-publication queue for misconduct/fraud allegations: regex detection of fraud/fabrication/plagiarism keywords, `pending_admin_review=True` flag, admin "Pending Review Queue" with Approve/Reject, inbox message to reviewer.
- [x] **B22** — Defamatory report path: "Report as defamatory" checkbox, immediate content hide, URGENT admin email, inbox notice to content author. DEFAMATORY badge on report row.
- [ ] **B23** — Author right-of-reply: backend model + routes built; UI removed pending author-identity verification strategy. Decision: CrossRef ORCID check is too unreliable; keep parked until a better approach is decided.
- [x] **B24** — Admin substantiation request: "Subst." button in admin dashboard hides review immediately, sends 14-day deadline inbox message, overdue check on dashboard load emails admin reminder.
- [x] **B25** — Railway env vars documented: `SITE_URL` and `ANTHROPIC_API_KEY` in Railway Variables tab.
- [x] **B26** — Admin notification emails: `notify_admin()` in `app/utils/email.py`, `ADMIN_NOTIFY_ENABLED` config flag, hooked into new reviews, comments, AI flags, reports, misconduct events.

### Block G — AI Moderation + Scraper Integration (July 2026)
- [x] **G1** — Bulk review import script (`scripts/import_reviews.py`): `--ai-name OrgSyn` flag auto-creates an `AI-OrgSyn` pseudo-user (career stage "Data curation agent"), imports reviews from JSON. `--dry-run` flag for preview. Schema example in `scripts/import_reviews_example.json`.
- [x] **G2** — Admin edit of AI-sourced reviews: `_editable_rating_or_404` helper allows admin to edit any `AI-*` review (star, failure context, observation text) on the paper page and admin dashboard. Regular user reviews remain delete-only.
- [x] **G3** — AI content moderation pipeline: Claude Haiku background task (`moderate_rating_bg`) checks every new review; client-side word blocklist in `app/static/js/moderation.js` (Layer 1). Both run independently — server never relies on client.
- [x] **G4** — Flagged reviews excluded from star rating aggregates: `_get_nd_paper_scores` and all public review queries filter `ai_flagged == False`.
- [x] **G5** — Auto inbox message + notification bell on flagging: `_send_flag_message` sends an admin inbox message with direct edit link (`/paper/{doi}/ratings/{id}/edit`) and fires a `type="flagged"` notification (red triangle icon, links to inbox).
- [x] **G6** — Empty observation popup: intercepts submit when obs text is blank; modal shows "No observation text provided" with "Go back" / "Submit anyway". Uses hidden `<input type="submit">` so COI checkbox and client-side moderation both fire correctly on re-submit.
- [x] **G7** — Flagged review edit cycle: author sees their own hidden review on paper page in an amber warning banner with "Edit and resubmit" link. On save, flag is cleared, review reappears in the public list, and moderation re-runs in background. If still problematic, re-flags and sends another inbox message.
- [x] **G8** — Admin user edit modal on admin dashboard: editable name, nickname, career stage for any user. AI accounts show an indigo "AI" chip badge.

---

## Notes

- **SITE_URL**: set `SITE_URL=https://chemrepro-test.up.railway.app` in Railway env vars so flagging inbox messages link to the correct domain.
- **ANTHROPIC_API_KEY**: must be set in Railway env vars for AI moderation to run on production (currently in local `.env`).
- **ADMIN_SECRET_TOKEN**: set a real secret in Railway `.env` before public launch.
- **v1 templates** are read-only snapshots. Do not edit.
- **LinkedIn**: gate review submission behind ORCID; LinkedIn for comments/follows only (connection count not available via API).
- **B3 author emails**: CrossRef + Europe PMC + PubMed in order. Silently skips preprints and non-indexed papers — expected.

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
