# ChemRepro Push Log
<!-- Append one entry per push, most recent first. Update before every git push. -->

---

## 2026-08-17 | Push 9 | `b8a1879`
**Files changed (26):**

*Admin dashboard redesign:*
- `app/templates/admin_base.html` — new: shared shell for every admin page (left sidebar nav, full-width layout)
- `app/templates/admin_users.html` — new: `/admin/users`, split out of the dashboard (table, edit modal, Ban/Delete)
- `app/templates/admin_papers.html` — new: `/admin/papers`, browse every looked-up paper with review/comment/search/view counts, client-side filter, sortable columns
- `app/templates/admin_api_keys.html` — new: `/admin/api-keys`, split out of the dashboard
- `app/templates/admin_dashboard.html` — now extends `admin_base.html`; Users and API Keys sections (and their modal/JS) removed
- `app/templates/admin_banned_words.html`, `admin_submission_warnings.html` — converted to the `admin_base.html` shell, back-link header removed (sidebar nav replaces it)
- `app/templates/admin_name_votes.html` — converted to the `admin_base.html` shell; XSS fix: delete-suggestion form's `onsubmit="return confirm('...{{ s.name }}...')"` (name interpolated into a JS string) switched to the `data-confirm` pattern
- `app/templates/base.html` — `<main>` width is now an overridable `{% block main_class %}` so admin pages can opt out of the site-wide `max-w-5xl` centering
- `app/models/paper.py`, `app/main.py` — `search_count`/`view_count` columns on `Paper` (SQLite + Postgres migration)
- `app/routers/papers.py` — increments `search_count` in `/search`, `view_count` via a shared `_bump_view_count()` in all three paper-detail routes
- `app/routers/admin.py` — `GET /admin/users`, `GET /admin/papers` (with `?sort=`), `GET /admin/api-keys`; dashboard route no longer queries `all_users`/`recent_users`/`api_keys`
- `TASKS.md` — added banned-words alphabetical-order note (future work)

*Security hardening (found sitting locally, audited and folded in this push — see PROJECT_STATE.md "Security Hardening" table):*
- `app/routers/pledge.py` — open-redirect fix on `?next=`; audit found the original fix incomplete (didn't block `/\host`, which browsers normalise to `//host`), corrected before this push
- `app/routers/auth.py` — dev-login/dev-link routes now require `ORCID_ENV == "sandbox"` exactly, matching the fail-closed convention used elsewhere
- `app/routers/feedback.py` — `/admin/feedback` now uses the shared `_require_admin()` instead of an environment-only check that had no auth at all locally
- `app/routers/reports.py` — non-numeric `target_id` now returns 422 instead of an unhandled 500
- `app/services/author_notify.py` — HTML-escapes title/URL in the outbound author-notification email
- `app/routers/images.py` — verifies uploaded bytes match the declared MIME type, guards against decompression bombs, adds `X-Content-Type-Options: nosniff`
- `app/utils/design.py` — review markdown image-src allowlist restricted to `/images/`, closing an external tracking-pixel hole
- `app/services/linkedin_post.py` — prompt now explicitly forbids stating chemical detail not present in the source data
- `app/templates/edit_rating.html`, `edit_rating_classic.html`, `edit_rating_nd.html`, `guest_setup.html`, `paper.html`, `paper_classic.html`, `paper_classic_v1.html`, `paper_nd.html`, `paper_v1.html` — `data-content-label` added to every review/comment/reply/name form (moderation warning modal says "review"/"comment"/etc. instead of the generic fallback); Classic paper's comment-reply form also gained `data-moderate` (was falling through to a native full-page submit)
- `.gitignore` — added `*.env` and explicit entries for known-sensitive local files (`Public_DB_URL.env`, `ADMIN login.txt`, etc.), which the exact-match `.env` entry didn't cover

**What changed (summary):**
- Admin dashboard restructured: Users, Papers, and API Keys each get their own sidebar-linked page instead of one long scrolling dashboard; admin pages are now full-width
- New Papers page tracks per-paper search and view counts (accruing from today, no historical backfill)
- A second, independently-written batch of security fixes was discovered uncommitted in the working tree during this push's audit, reviewed line-by-line, one gap fixed (pledge.py backslash bypass), and folded in

**Key decisions:**
- The security-fix batch had no record in `PROJECT_STATE.md`, `TASKS.md`, or session memory; audited from scratch rather than assumed safe before including

**Deferred:**
- Nothing new; `.pyc` files remain tracked in git despite matching `.gitignore` (pre-existing, harmless; cleanup with `git rm --cached` is a separate low-priority task)

---

## 2026-08-11 | Push 8 | `44d8451`
**Files changed (10):**
- `app/models/banned_term.py` — new: admin-curated banned word/phrase table (term, added_by, created_at)
- `app/models/submission_warning.py` — new: append-only evidence log for the repeated-violation warning system (orcid_id, doi, content_type, matched_term, content_snippet, created_at)
- `app/models/user.py` — added `submission_blocked` column, set once 3 warnings land on the same paper
- `app/templates/admin_banned_words.html` — new: admin UI to add/remove banned terms
- `app/templates/admin_submission_warnings.html` — new: admin UI listing blocked accounts (with unblock) and the last 100 warnings
- `scripts/seed_banned_terms.py` — new: idempotent seed of ~59 profanity slang/misspelling terms into `banned_terms`
- `app/main.py` — migrations for `submission_blocked`/new tables; `wants_json` now also checks `Accept: application/json` (needed for moderation.js's fetch-based submits to get JSON error bodies instead of an HTML error page); bundled: `ORCID_ENV == "production"` → `!= "sandbox"` semantics swap on session cookie/demo-route guards
- `app/routers/admin.py` — banned-words CRUD routes; submission-warnings + unblock routes; bundled: timing-safe admin-login token compare (`hmac.compare_digest`)
- `app/routers/papers.py` — all 14 review/comment/reply submit+edit endpoints now go through the shared `enforce_moderation()` gate instead of the old one-shot `is_clean()` check; bundled: duplicate-rating `IntegrityError` handling, score-parsing `ValueError` handling
- `app/static/js/moderation.js` — fixed escalation bug (client-side word list was short-circuiting the server round-trip on repeat offenses, so warning 2 and the block never fired); singleton warning/block modal
- `app/utils/moderation.py` — `enforce_moderation()`: central 3-warning escalation gate, reads the live `BannedTerm` list; `IntegrityError` guard so a bad-word submit against a bogus/stale `doi` degrades to the caller's normal 404 instead of a Postgres 500
- `app/utils/ai_moderation.py` — Haiku moderation prompt now flags profanity/slurs in any Latin-script language and is fed the live banned-term list
- `app/templates/admin_dashboard.html` — added Warnings nav link; fixed XSS in the user Edit/Delete buttons (`u.name`/`u.nickname`/`u.career_stage` were interpolated into an inline `onclick` JS string; a display name containing `'` could break out and run script in the admin's session, the existing `replace("'", "\'")` "fix" was a no-op since `\'` and `'` are the same Python string, switched to `data-*` attributes read via `.dataset` instead)
- `requirements.txt` — added `Pillow>=11.0.0` (unrelated bundled dependency)

**What changed (summary):**
- Real 3-strike moderation: 1st/2nd bad-word submission on a paper shows a warning modal, the 3rd blocks the account site-wide until an admin unblocks it at `/admin/submission-warnings`
- Admin-curated banned word list at `/admin/banned-words`, no code deploy needed to add a term; seeded with ~59 profanity slang/misspelling terms
- Fixed a real bug where escalation silently never advanced past warning 1
- Fixed an XSS in the admin dashboard's user-management buttons and in both new admin templates (found during this push's audit, not present before)
- `TASKS.md`: added wildcard/fuzzy-matching note (future work) and an admin dashboard style-update note (future work)

---

## 2026-08-10 | Push 7 | `747b657`
**Files changed (5):**
- `app/models/rating.py` — added `linkedin_post_metadata` column (JSON, nullable); stores `{label, closing_id, rhythm_id, word_count, issues}` at generation time
- `app/main.py` — migration for `linkedin_post_metadata` (SQLite TEXT + PostgreSQL JSON)
- `app/services/linkedin_post.py` — full rewrite: 12 corrected outcome templates (5A/5B = major extension, 4A/4B = minor extension, 3A/3B = exact repro, 2A/2B = deviation, 1A/1B = did not work, EF, INC); `_select_template()` now handles all nd_star values 1-5 plus nd_failure_context; C1-C6 closing moves with valence constraint (C5/C6 free on 1A/1B/EF/INC, occasional on 2A-3B, never on 4A-5B); R1 floor for word_target < 110; automatic post validator with one auto-retry; `generate_linkedin_post()` returns `tuple[str, dict]` and does NOT update rotation state; new `update_rotation_on_publish()` called on Posted click only; `is_eligible_for_post()` removed
- `app/routers/admin.py` — removed `_eligible` tuple and star-gate filter from both LinkedIn queries; `generate-linkedin-post` endpoint stores `linkedin_post_metadata`, returns specific error messages for observation_required/unknown_outcome; `linkedin-post-status` endpoint calls `update_rotation_on_publish` when status = "posted"; `or_` import removed
- `app/templates/admin_dashboard.html` — section description updated; template label chip in card header; amber warning banner on 1A/1B cards; red validator issue list when issues remain after auto-retry

**What changed (summary):**
- All reviews now appear in the LinkedIn queue (no star gate); Daniel clicks Generate on any review
- Correct star scale: 5 = major extension, 4 = minor extension, 3 = exact repro, 2 = deviation, 1 = did not work
- Rotation state updates on publish (Posted click), not on generation; wasted generation clicks no longer consume rotation budget
- Automatic validator catches em dashes, URL placement, hashtag count, banned phrases; auto-retries once; if still failing, shows issues on the card
- 1A/1B cards flagged with amber caution banner

**Deferred:**
- Event templates (SR-C, SR-D, AR, MS50): manual-only process
- `tag_history[5]` hashtag rotation (last_hooks and tag_history not yet implemented in code; low-priority)

---

## 2026-08-10 | Push 6 | `ee0c404`
**Files pushed (1):**
- `app/services/linkedin_post.py` — proportional word target: post length now scales with review length (max 60% longer, floor 80, ceiling 180); `_GLOBAL_RULES_TMPL` parameterized with `{word_target}`; `_CHECKLIST` item 1 updated; `_build_prompt` accepts `word_target` kwarg; `generate_linkedin_post` computes target from `obs_word_count`

**What changed:**
- An 80-word review targets ~128-word post instead of 150-200; floor of 80 words applies to very short reviews; ceiling of 180 words applies to long ones; no-observation default is 100 words

**Deferred:**
- Nothing new

---

## 2026-08-10 | Push 5 | `9e31af4`
**Files pushed (4):**
- `app/services/linkedin_post.py` — full rewrite: 10-template system (5A/5B/4A/4B/3A/3B active; 12A/12B/EF/INC dormant); `is_eligible_for_post()` helper (nd_star >= 3, excludes extension_failed/inconclusive); rotation state persisted to `linkedin_rotation_state.json`; single-template prompt injection per spec section 6; closing move (C1-C4) and rhythm (R1/R2/R3) rotation with anti-repeat memory
- `app/routers/papers.py` — removed auto-generation background task (`generate_linkedin_post_for_rating`) from `nd_submit_rating`; removed the import
- `app/routers/admin.py` — added `or_` to sqlalchemy imports; both `reviews_with_draft` and `reviews_without_draft` queries now filter to eligible reviews only (nd_star >= 3, nd_failure_context not extension_failed or inconclusive); `reviews_without_draft` limit raised from 5 to 20
- `app/templates/admin_dashboard.html` — updated description and label text to reflect manual-trigger workflow

**What changed:**
- LinkedIn post generation is now manual only: Daniel clicks "Generate" on an eligible review card in the admin dashboard; no post is generated automatically on review submit
- Only reviews with nd_star >= 3 and no extension_failed/inconclusive failure context appear in the LinkedIn draft queue
- Haiku now uses a condition-linked template (5A/5B for 5-star, 4A/4B for 4-star, 3A/3B for 3-star) with rotating closing moves and rhythm profiles instead of the original fixed generic prompt
- Star rating is never mentioned in any generated post (per spec global rules and Daniel's instruction)

**Deferred:**
- 12A/12B (1-2 star posts): dormant until legal entity, ToS, takedown route, and non-personal contact address are live
- EF/INC templates: excluded from queue per Daniel's instruction; spec text retained for future activation
- Event templates (SR-C, SR-D, AR, MS50): not yet wired up

---

## 2026-08-07 | Push 4 | `5f72fd9`
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
