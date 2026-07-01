# ChemRepro — Task Tracker
_Last updated: 1 July 2026_

---

## ACTIVE

### BLOCK B — New Features

- [ ] **B4/C9/D7** — Chemistry keyword/condition tags on rating form (Yield discrepancy, Purity issue, Safety concern…) — deferred, design not settled
- [ ] **B11** — Activate author email notification (`AUTHOR_NOTIFY_ENABLED=true` in Railway `.env`) — disabled pending test that CrossRef/PMC/PubMed lookup works on real chemistry DOIs
- [ ] **B12** — Wire `notification_email` to SMTP sender — field is saved in Settings but never read; when a followed paper gets a new review/comment, send an email to `notification_email` if set (F6 in audit)
- [x] **B13** — Report mechanism: `reports` table, `/report` endpoint, modal with optional reason field, toast confirmation; admin can resolve/delete from dashboard
- [ ] **B14** — LinkedIn login (OAuth 2.0 alongside ORCID) — planned P3
- [ ] **B15** — Image upload/paste in comment boxes — planned P3

### BLOCK C — UX Polish

- [ ] **C10** — Logo polish (current logo is placeholder)
- [x] **C16** — Nickname shown in nav after ORCID login; also applied at guest reconnect and profile setup submit
- [x] **C17** — Nickname field added to first-login profile-setup page

### BLOCK D — Post-Launch

- [ ] **D1** — Browser extension (Chrome + Firefox — parked)
- [ ] **D2** — Sketchit design review (do when feature set is stable)
- [ ] **D3** — Partnership outreach
  - organic-chemistry.org
  - orgsyn.org — priority: propose database cross-reference partnership
  - organicchemistrydata.org
- [ ] **D4** — Swiss non-profit legal setup
- [ ] **D5** — ORCID on production domain (register HTTPS redirect URI on orcid.org)
- [ ] **D6** — Personal reaction collection / "My Library" page
- [ ] **D8** — Zotero, Mendeley plugin
- [ ] **D9** — Create official website email address once platform name is finalised (e.g. hello@[name].com); use for user-facing sender, about page, and contact links
- [ ] **D10** — Terms of Service page (required before public launch; see privacy.html as style reference)
- [x] **D11** — Admin dashboard at `/admin/` (secret-token login URL, no public login surface); god powers: delete any review/comment/user/paper/message, ban users, resolve reports; `ADMIN_SECRET_TOKEN` in `.env`

### BLOCK F — Code Cleanup (found in 2026-06-16 audit)

- [x] **F1** — Remove dead `/design/{ver}` route from `papers.py`
- [x] **F2** — Delete unused `app/templates/search_results.html`
- [x] **F3** — Gate `/demo/colors` with production check
- [x] **F4** — Extract `_BLOCKED_RE` to `app/utils/moderation.py`; removed duplicate from `papers.py` and `messages.py`
- [ ] **F5** — Fix API v1 scoring schema — `api.py` returns `avg_reproducibility` / `avg_generalisability` which are always `None` for Standard-mode papers; update to return outcome-based aggregate
- [x] **F8** — Fix `Rating` model default `"v2"` → `"standard"`

---

## Notes

- **B3 author emails**: CrossRef → Europe PMC → PubMed tried in order. PubMed covers most indexed chemistry journals (JACS, Org Lett, Angew Chem, etc.) via the "Electronic address:" field in affiliation XML. Notifications will still silently skip for preprints or non-indexed papers — expected.
- **v1 templates** (`base_v1.html`, `index_v1.html`, `paper_v1.html`, `paper_classic_v1.html`) are read-only snapshots of the `main` branch at the time v2 was merged. Do not edit.
- **Audit file**: `audit/snapshot_2026-06-16_v2.md` — full route list, schema, and known issues.

---

## ARCHIVE

### BLOCK A — Legal / Broken (all done)

- [x] **A1** — Fix feedback email delivery (switched SMTP 465 → 587 STARTTLS; added `send_generic_email()` helper)
- [x] **A2** — Add full postal address to `privacy.html` — `Breisacherstrasse 68 / 4057 Basel, Switzerland`
- [x] **A3** — Railway DPA signed (DocuSign envelope 56122F5D; Exhibit B + Effective Date + Title completed)
- [x] **A4** — Server-side content moderation (`_is_clean()` regex blocklist in `papers.py`; checks comment + rating submissions; extended to inbox messages)

### BLOCK B — New Features (completed items)

- [x] **B1** — Markdown comments with live preview
- [x] **B2** — Article alert subscriptions (Follow a paper; in-app notifications on new review/comment)
- [x] **B3** — Author email notification on new review (CrossRef → Europe PMC → PubMed fallback chain; HMAC opt-out)
- [x] **B5** — Comment threading (likes on comments + 1-level replies)
- [x] **B6** — Private in-mail messaging between users (moderation blocklist applied)
- [x] **B7** — About page
- [x] **B8** — Social sharing popup (WhatsApp, Email, LinkedIn, Copy)
- [x] **B9** — User follow system; commenter names clickable (Follow / Message / Report dropdown)
- [x] **B10** — v2 design: blue brand (#1e40af), review card 3-col header (name | career stage | date), reviewer name dropdowns with Follow/Message/Report; v1 archived

### BLOCK C — UX Polish (completed items)

- [x] **C1** — Footer cleanup
- [x] **C2** — Privacy page em dash fix
- [x] **C3** — Textarea sizing
- [x] **C4** — Spellcheck on all textareas
- [x] **C5** — Homepage sort order (by latest rating)
- [x] **C6** — Remove API link from nav
- [x] **C7** — Scoring explainer via hover tooltip
- [x] **C8** — Mobile: Classic tooltip overflow (`max-w-[95vw]` on mobile, `sm:min-w-[440px]` on desktop)
- [x] **C11** — Like notification icon: 3/4-filled flask SVG (amber)
- [x] **C12** — Like button: 3/4-filled flask; comment like buttons changed from heart to flask
- [x] **C13** — Feedback nav link restored to top nav
- [x] **C14** — Classic view card: "2×" → "2 ratings" with correct pluralisation
- [x] **C15** — Standard view card: ★ star restored before avg_score

### BLOCK E — Feedback & Naming (all done)

- [x] **E1** — Tester feedback form (scoring preference + free-text comment)
- [x] **E2** — Name-the-platform widget on feedback page (alphabetical pills, AJAX vote toggle, suggest-stays-on-page)
