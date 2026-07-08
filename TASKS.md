# ChemRepro — Task Tracker
_Last updated: 8 July 2026_

---

## ACTIVE — by priority

### 🟠 HIGH

- [ ] **B11** — Activate author email notification (`AUTHOR_NOTIFY_ENABLED=true` in Railway `.env`) — disabled pending test that CrossRef/PMC/PubMed lookup works on real chemistry DOIs
- [ ] **B12** — Wire `notification_email` to SMTP sender — field is saved in Settings but never read; when a followed paper gets a new review/comment, send an email to `notification_email` if set
- [ ] **B14** — LinkedIn OAuth: routes + UI fully built, button shows "Coming soon". Before release: register app at developer.linkedin.com, set `LINKEDIN_CLIENT_ID` + `LINKEDIN_CLIENT_SECRET` + `LINKEDIN_REDIRECT_URI` in Railway `.env`, then restore button to active link.
- [ ] **C18** — ORCID button resting text is `text-slate-700` on all pages; LinkedIn "Coming soon" version is grey. Revisit once LinkedIn is activated: decide whether ORCID should use brand green `text-[#A6CE39]` or both stay neutral.

### 🟡 MEDIUM

- [ ] **B4/C9/D7** — Chemistry keyword/condition tags on rating form (Yield discrepancy, Purity issue, Safety concern…) — deferred, design not settled
- [ ] **C10** — Logo polish (current logo is placeholder)
- [x] **C20** — Migration script `scripts/fix_abstract_prefix.py` strips leading "Abstract" prefix from existing rows. Run locally or against Railway with `DATABASE_URL=... python scripts/fix_abstract_prefix.py`.

### 🔵 POST-LAUNCH

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
