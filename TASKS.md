# ChemRepro — Task Tracker
_Last updated: 15 June 2026 — Sprint 5 complete_

---

## BLOCK A — Must Fix Before Launch (Legal / Broken)

- [x] **A1** — Fix feedback email delivery (switched SMTP 465 → 587 STARTTLS; added `send_generic_email()` helper)
- [x] **A2** — Add full postal address to `privacy.html` — `Breisacherstrasse 68 / 4057 Basel, Switzerland`
- [x] **A3** — Railway DPA signed (DocuSign envelope 56122F5D; Exhibit B + Effective Date + Title completed)
- [x] **A4** — Server-side content moderation (`_is_clean()` regex blocklist in `papers.py`; checks comment + rating submissions; extended to inbox messages)

---

## BLOCK B — New Features

- [x] **B1** — Markdown comments with live preview
- [x] **B2** — Article alert subscriptions (Follow a paper)
- [x] **B3** — Author email notification on new review
- [ ] **B4/C9/D7** — Chemistry keyword/condition tags on rating form (Yield discrepancy, Purity issue, Safety concern…) — deferred, design not settled
- [x] **B5** — Comment threading (likes on comments + 1-level replies)
- [x] **B6** — Private in-mail messaging between users
  - Content moderation blocklist applied to new messages and replies
- [x] **B7** — About page
- [x] **B8** — Social sharing popup (WhatsApp, Email, LinkedIn, Copy)
- [x] **B9** — User follow system
  - New `UserFollow` model (`app/models/user_follow.py`)
  - `POST /follow/toggle/{orcid_id}` — AJAX toggle; returns `{following: bool}`
  - Commenter names are clickable: dropdown with Follow / Message / Report options (both paper views)
- [x] **B10** — v1/v2 design toggle in nav
  - `GET /design/{ver}` sets session cookie, redirects back
  - `app/utils/design.py`: `design_base()`, `index_tpl()`, `paper_tpl()`, `paper_classic_tpl()` helpers
  - `base_v1.html`, `index_v1.html`, `paper_v1.html`, `paper_classic_v1.html` pulled from `main` branch (exact Railway production state)
  - v1/v2 pill sits alongside Standard/Classic in both navs; all 22 page templates use `design_base(request)`

---

## BLOCK C — UX Polish

- [x] **C1** — Footer cleanup
- [x] **C2** — Privacy page em dash fix
- [x] **C3** — Textarea sizing
- [x] **C4** — Spellcheck on all textareas
- [x] **C5** — Homepage sort order (by latest rating)
- [x] **C6** — Remove API link from nav
- [x] **C7** — Scoring explainer via hover tooltip
- [x] **C8** — Mobile: Classic tooltip overflow (`max-w-[95vw]` on mobile, `sm:min-w-[440px]` on desktop)
- [ ] **C9** — merged into B4/C9/D7 above
- [ ] **C10** — Logo polish (current logo is placeholder)
- [x] **C11** — Like notification icon: changed from ★ to 3/4-filled flask SVG (amber, matches like button)
- [x] **C12** — Like button: 3/4-filled flask (`.flask-liquid` path at y=13); comment like buttons also changed from heart to flask
- [x] **C13** — Feedback nav link restored to top nav
- [x] **C14** — Classic view card: "2×" → "2 ratings" with correct pluralisation; label style matches standard view
- [x] **C15** — Standard view card: ★ star restored before avg_score

---

## BLOCK D — Post-Launch

- [ ] **D1** — Browser extension (Chrome + Firefox — parked)
- [ ] **D2** — Sketchit design review (do when feature set is stable)
- [ ] **D3** — Partnership outreach
  - organic-chemistry.org
  - orgsyn.org — priority: propose database cross-reference partnership
  - organicchemistrydata.org
- [ ] **D4** — Swiss non-profit legal setup
- [ ] **D5** — ORCID on production domain
- [ ] **D6** — Personal reaction collection / "My Library" page
- [ ] **D7** — merged into B4/C9/D7 above
- [ ] **D8** — Zotero plugin

---

## BLOCK E — Feedback & Naming (Beta)

- [x] **E1** — Tester feedback form (scoring preference + free-text comment)
- [x] **E2** — Name-the-platform widget on feedback page
  - `NameSuggestion` + `NameVote` models; suggestions sorted alphabetically
  - `POST /feedback/suggest` stays on page (no redirect to thank-you)
  - `POST /feedback/vote/{id}` — AJAX toggle; live count update
  - Widget shown above feedback form; visible before and after submit

---

## Notes

- **MOCK_SCORING=true** in `.env` — disable before real use (costs ~$1/run with Sonnet).
- **Indeed scraper** disabled (`ENABLE_INDEED=False`) — re-enable or delete once tested.
- **B3 author emails**: CrossRef rarely returns emails; Europe PMC returns them for some OA papers. Most notifications will silently skip — expected behaviour.
- **v1 templates** (`base_v1.html`, `index_v1.html`, `paper_v1.html`, `paper_classic_v1.html`) are snapshots of the `main` branch at the time the impeccable redesign was merged. Do not edit them — they are the reference baseline.
