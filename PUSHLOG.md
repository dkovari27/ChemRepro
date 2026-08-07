# ChemRepro Push Log
<!-- Append one entry per push, most recent first. Update before every git push. -->

---

## 2026-08-07 | Push 4 | (hash TBD)
**Files pushed (7):**
- `app/routers/feedback.py` — `_voter_id` now returns None for anonymous and guest (local:) users; `toggle_vote` returns 401 for unauthenticated; `add_suggestion` redirects to login if unauthenticated; `can_vote` flag passed to template
- `app/routers/admin.py` — `GET /admin/name-votes`, `POST /admin/name-votes/{id}/delete`, `POST /admin/name-suggestions/{id}/delete`, `POST /admin/name-suggestions/add`; suggestions serialised to plain dicts before template render
- `app/routers/auth.py` — `_safe_next()` helper (open-redirect guard); `choose_login` saves `next` query param to session as `login_next`; ORCID and LinkedIn callbacks thread `login_next` through post-login redirect and profile-setup flow
- `app/templates/_name_suggestions.html` — locked (static, unclickable) chips for anonymous users; Sign in CTA replaces suggest form; voteFor JS only included when `can_vote` is true; removed "Multiple votes are allowed" text
- `app/templates/admin_name_votes.html` — new admin page: list suggestions by vote count, show voter IDs with timestamps, Remove vote button, Delete suggestion button, Add name form
- `CLAUDE.md` — added pre-push review protocol (bug search, severity report, approval required before push)
- `TASKS.md` — removed completed Push 2 parked entry

**What changed:**
- Name voting now requires a real login (ORCID or LinkedIn); anonymous and guest accounts see read-only chips and a Sign In button
- Admin can manage name suggestions and individual votes at /admin/name-votes
- After being blocked by the voting gate, signing in returns the user to /feedback (not /)

**Deferred:**
- Nothing new

---

## 2026-08-07 | Push 2 | `ef7e9e8`
**Files pushed (5):**
- `app/models/user.py` — `linkedin_id` (String 255, unique, nullable) and `orcid_real` (String 50, unique, nullable) fields on User model
- `app/routers/auth.py` — LinkedIn login; `/auth/link/linkedin` and `/auth/link/orcid` routes; ORCID and LinkedIn callbacks modified for linking; `/auth/dev-link/{orcid_idx}/{linkedin_idx}` (production-guarded); session keys now popped at top of each callback (bug fix: stale key on denied OAuth)
- `app/templates/base.html` — DEV panel (is_local guarded, amber button, 5 fake users + Link DanK shortcut + sign out); LinkedIn badge fix ("LinkedIn ✓" for linkedin: users)
- `app/templates/base_v1.html` — LinkedIn badge fix (classic design)
- `app/templates/profile_settings.html` — full P2 version: linked accounts card (ORCID-primary shows LinkedIn link; LinkedIn-primary shows ORCID link; linked state shows provider + indicator); flash messages for linked/link_error; provider label in identity section; guest accounts excluded from linked accounts card; nickname placeholder adapts to provider

**What changed:**
- Account linking: ORCID-primary users can link a LinkedIn account from Settings; LinkedIn-primary users can link their ORCID; each callback detects and rejects conflicts (already-linked, already-primary-account); DEV panel shortcut `/auth/dev-link/3/4` for local testing without real OAuth
- Bug fixes in this push: missing LinkedIn-primary conflict check in LinkedIn callback; nav badge showing wrong provider for LinkedIn users; session key leak when OAuth is denied mid-link-flow; nickname placeholder wrong for LinkedIn users; linked accounts card visible to guest accounts

**Deferred (not in this push):**
- Nothing new; all prior deferred items remain in TASKS.md

---

## 2026-08-07 | Push 3 | `0775295`
**Files pushed (6):**
- `app/main.py` — migration for `linkedin_post_status` column (SQLite + PostgreSQL)
- `app/models/rating.py` — `linkedin_post_status` field (NULL = active draft, 'posted', 'archived')
- `app/routers/admin.py` — `POST /admin/reviews/{id}/linkedin-post-status` endpoint (posted/archived/restore); active drafts query now excludes posted/archived; added `linkedin_posted` and `linkedin_archived` queries
- `app/routers/papers.py` — added `/paper/{doi}/comment/{id}/edit` route alias (was only at `/design-archive/standard/paper/...`; save button was silently 404ing)
- `app/templates/admin_dashboard.html` — Posted/Archive checkboxes in card header; auto page-reload on status change; Posted/Archived columns with author + date chips, clickable to restore; uniform dark text color on both columns
- `TASKS.md` — added email system/domain address note

**What changed:**
- LinkedIn post status: tick Posted or Archive on any draft card; card fades and page reloads; review appears in the relevant column below with author name and date; clicking a column entry restores the draft
- Comment edit save button: was calling a non-existent URL on paper_nd.html and paper_classic.html; fixed by adding the correct route alias
- Email: switched from Gmail SMTP (blocked by Railway) to Resend HTTP API; domain chemrepro.org verified on Resend; emails now send from noreply@chemrepro.org

**Deferred (not in this push):**
- Push 2: account linking (user.py, auth.py, base.html, profile_settings.html)

---

## 2026-08-05 | Push 1 | `56d365a`
**Branch:** main
**Files pushed (10):**
- `app/models/rating.py` — added `linkedin_post_draft` column
- `app/main.py` — migration for `linkedin_post_draft` (SQLite + PostgreSQL); also includes safe nullable migrations for `linkedin_id` and `orcid_real` on users table (Push 2 prerequisite, non-breaking)
- `app/routers/admin.py` — LinkedIn post drafts section: query for reviews with/without draft, `POST /admin/reviews/{id}/generate-linkedin-post` endpoint
- `app/routers/papers.py` — background task call to `generate_linkedin_post_for_rating` on non-misconduct review submit
- `app/routers/profile.py` — `_nickname_taken()`, `_suggest_nicknames()` helpers; `GET /profile/nickname-check` JSON endpoint; removed duplicate `register_globals()` call
- `app/services/linkedin_post.py` — new file; Haiku (`claude-haiku-4-5-20251001`) LinkedIn post generator; `generate_linkedin_post_for_rating()` background task entry point
- `app/templates/admin_dashboard.html` — two-column LinkedIn post draft card (original review left with images/stars/DOI, draft right with Copy/Regenerate buttons)
- `app/templates/login_choose.html` — guest login button under `{% if is_local %}` guard
- `app/templates/profile_settings.html` — P1-only version (linked accounts card stripped for clean push)
- `app/templates/profile_setup.html` — live nickname check JS block added

**What changed:**
- Nickname uniqueness: live debounced availability check (400ms), green "Available" indicator, red "Taken" with clickable suggestion chips; both profile setup and settings pages
- LinkedIn post draft generator: Haiku writes a ~150-200 word post on review submit; admin dashboard shows two-column card to review and copy
- Guest login button visible locally (no template yet, 404 on click; deferred)

**Key decisions:**
- Mock scoring ON locally (`MOCK_SCORING=true`) so Haiku does not fire during dev; costs ~$0.002/post in production
- Haiku model: `claude-haiku-4-5-20251001`; prompt explicitly forbids em dashes
- `profile_settings.html` pushed as P1-only (linked accounts card absent); full P2 version restored locally after push

**Deferred (not in this push):**
- Account linking ORCID ↔ LinkedIn (Push 2): `user.py`, `auth.py`, `base.html`, full `profile_settings.html`
