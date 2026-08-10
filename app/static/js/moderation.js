/**
 * Layer 1 — client-side content moderation.
 *
 * Uses whole-word matching only (\b boundaries) to avoid false positives
 * on chemistry terms (e.g. "cummene" does NOT match "cum").
 *
 * This is a first line of defence only. The server applies the same check
 * independently (plus an admin-curated custom word list and AI review),
 * so bypassing this script does not bypass moderation.
 */

const _BLOCKED = [
  // Profanity
  'fuck', 'fucker', 'fucking', 'fucks', 'fucked',
  'shit', 'shitting', 'bullshit',
  'cunt', 'cunts',
  'bitch', 'bitches',
  'asshole', 'arsehole',
  'bastard', 'bastards',
  'cock', 'cocks',
  'dick', 'dicks',
  'pussy', 'pussies',
  'whore', 'whores',
  'slut', 'sluts',
  'prick', 'pricks',
  'wanker', 'tosser',
  'twat', 'twats',
  'bollocks',

  // Slurs — racial / ethnic / homophobic / ableist
  'nigga', 'nigger', 'niggers',
  'faggot', 'faggots', 'fag', 'fags',
  'retard', 'retarded', 'retards',
  'spic', 'spics',
  'kike', 'kikes',
  'chink', 'chinks',
  'gook', 'gooks',
  'wetback', 'wetbacks',
  'tranny', 'trannies',
  'dyke', 'dykes',
  'cracker',
];

// Pre-compile patterns once, not on every keystroke
const _PATTERNS = _BLOCKED.map(w => new RegExp(`\\b${w}\\b`, 'i'));

/**
 * Returns the first blocked word found in `text`, or null if clean.
 */
function findBlockedWord(text) {
  for (let i = 0; i < _PATTERNS.length; i++) {
    if (_PATTERNS[i].test(text)) return _BLOCKED[i];
  }
  return null;
}

/**
 * Checks all text inputs and textareas in `form`.
 * Returns { clean: true } or { clean: false, field: Element, word: string }.
 */
function moderateForm(form) {
  const fields = form.querySelectorAll('input[type="text"], input[type="search"], textarea');
  for (const field of fields) {
    const hit = findBlockedWord(field.value);
    if (hit) return { clean: false, field, word: hit };
  }
  return { clean: true };
}

/**
 * Singleton warning modal, built once and reused for every moderated form
 * on the page. Mirrors the look of the "thanks for your review" modal.
 * Supports two variants: 'warn' (amber, warnings 1 and 2 on a paper) and
 * 'block' (red, once the account has been restricted from posting).
 */
const _MODERATION_ICONS = {
  warn: '<path d="M12 9v4"/><path d="M12 17h.01"/><path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0Z"/>',
  block: '<circle cx="12" cy="12" r="10"/><path d="m4.9 4.9 14.2 14.2"/>',
};

function _getModerationModal() {
  let modal = document.getElementById('moderation-warning-modal');
  if (modal) return modal;

  modal = document.createElement('div');
  modal.id = 'moderation-warning-modal';
  modal.className = 'hidden fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm';
  modal.innerHTML = `
    <div class="bg-white rounded-2xl shadow-xl w-full max-w-sm mx-4 p-6 text-center">
      <div class="flex justify-center mb-4">
        <div id="moderation-warning-icon-wrap" class="w-12 h-12 rounded-full bg-amber-100 flex items-center justify-center">
          <svg id="moderation-warning-icon" class="w-6 h-6 text-amber-600" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"></svg>
        </div>
      </div>
      <h2 id="moderation-warning-title" class="text-base font-semibold text-slate-800 mb-1">Please revise your submission</h2>
      <p id="moderation-warning-body" class="text-sm text-slate-500"></p>
      <p id="moderation-warning-extra" class="hidden text-sm text-slate-500 underline underline-offset-2 mb-5"></p>
      <button type="button" data-moderation-close id="moderation-warning-btn"
        class="px-6 py-2 bg-amber-600 text-white rounded-xl text-sm font-medium hover:bg-amber-700 transition-colors">
        Close
      </button>
    </div>
  `;
  document.body.appendChild(modal);

  const close = () => modal.classList.add('hidden');
  modal.querySelector('[data-moderation-close]').addEventListener('click', close);
  modal.addEventListener('click', e => { if (e.target === modal) close(); });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && !modal.classList.contains('hidden')) close();
  });

  return modal;
}

/**
 * @param {Object} opts
 * @param {'warn'|'block'} [opts.variant='warn']
 * @param {string} opts.title
 * @param {string} opts.body
 * @param {string} [opts.extraHtml] - Extra underlined line under the body.
 *   Rendered as HTML (not escaped) so it can carry a mailto: link; only ever
 *   called with copy we author below, never with user-supplied text.
 */
function showModerationModal({ variant = 'warn', title, body, extraHtml = '' }) {
  const modal = _getModerationModal();
  const isBlock = variant === 'block';

  const iconWrap = modal.querySelector('#moderation-warning-icon-wrap');
  iconWrap.className = `w-12 h-12 rounded-full flex items-center justify-center ${isBlock ? 'bg-red-100' : 'bg-amber-100'}`;
  const icon = modal.querySelector('#moderation-warning-icon');
  icon.className = `w-6 h-6 ${isBlock ? 'text-red-600' : 'text-amber-600'}`;
  icon.innerHTML = isBlock ? _MODERATION_ICONS.block : _MODERATION_ICONS.warn;

  modal.querySelector('#moderation-warning-title').textContent = title;

  const bodyEl = modal.querySelector('#moderation-warning-body');
  bodyEl.textContent = body;
  bodyEl.className = `text-sm text-slate-500 ${extraHtml ? 'mb-1' : 'mb-5'}`;

  const extraEl = modal.querySelector('#moderation-warning-extra');
  if (extraHtml) {
    extraEl.innerHTML = extraHtml;
    extraEl.className = 'text-sm text-slate-500 underline underline-offset-2 mb-5';
  } else {
    extraEl.className = 'hidden';
    extraEl.innerHTML = '';
  }

  const btn = modal.querySelector('#moderation-warning-btn');
  btn.className = `px-6 py-2 text-white rounded-xl text-sm font-medium transition-colors ${isBlock ? 'bg-red-600 hover:bg-red-700' : 'bg-amber-600 hover:bg-amber-700'}`;

  modal.classList.remove('hidden');
}

/**
 * Navigates to `url` after a successful moderated submit. Several of these
 * endpoints redirect back to the same page with only a #anchor added (e.g.
 * newly posted comments/replies land on "#review-123"). Per the HTML nav
 * spec, assigning that to location.href is treated as a same-document
 * fragment scroll, not a reload, so the freshly posted content would never
 * actually appear. Force a real reload whenever the path+query is unchanged.
 */
function _navigateAfterSubmit(url) {
  const target = new URL(url, window.location.href);
  const samePage = target.href.split('#')[0] === window.location.href.split('#')[0];
  if (samePage) {
    window.location.hash = target.hash;
    window.location.reload();
  } else {
    window.location.href = target.href;
  }
}

/**
 * Builds the showModerationModal() options for a moderation rejection.
 * `detail` is the structured object app.utils.moderation.enforce_moderation()
 * sends: { code: 'prohibited_language', warning_count } or
 * { code: 'submission_blocked' }. `label` is "review" / "comment" / "reply".
 */
function _moderationOptsFor(detail, label) {
  if (detail.code === 'submission_blocked') {
    return {
      variant: 'block',
      title: 'Your account has been restricted',
      body: 'Your account has been restricted from posting anywhere on ChemRepro due to repeated content violations.',
      extraHtml: 'If you want your account to be unblocked, please contact the admin at ' +
        '<a href="mailto:chemrepro@gmail.com">chemrepro@gmail.com</a>.',
    };
  }
  if (detail.code === 'prohibited_language') {
    const isSecondWarning = detail.warning_count >= 2;
    return {
      variant: 'warn',
      title: isSecondWarning ? 'Please revise your submission: 2nd warning' : 'Please revise your submission',
      body: `Please modify your ${label} according to the website guidelines!`,
      extraHtml: isSecondWarning
        ? 'One more violation on this paper will restrict your account from posting anywhere on ChemRepro.'
        : '',
    };
  }
  return {
    variant: 'warn',
    title: 'Please revise your submission',
    body: detail.message || `Something was missing or incorrect in your ${label}. Please check and try again.`,
  };
}

/**
 * Submits `form` via fetch instead of a native navigation, so a rejection
 * shows an in-place popup (text the user typed is preserved) instead of a
 * full-page error. On success, follows the server's redirect client-side so
 * existing post-submit behavior (e.g. the "thanks for your review" modal)
 * keeps working unchanged.
 */
async function submitModerated(form) {
  const submitBtn = form.querySelector('[type="submit"]');
  const label = form.dataset.contentLabel || 'submission';
  if (submitBtn) submitBtn.disabled = true;

  try {
    const resp = await fetch(form.action, {
      method: (form.method || 'POST').toUpperCase(),
      body: new FormData(form),
      headers: { 'Accept': 'application/json' },
    });

    if (resp.ok) {
      _navigateAfterSubmit(resp.url);
      return;
    }

    if (resp.status >= 400 && resp.status < 500) {
      let detail = { message: '' };
      try {
        const data = await resp.json();
        // FastAPI's own validation errors (e.g. a missing field) send
        // `detail` as a list of error objects, not a string or object.
        // Our own HTTPException(detail=...) calls send either a plain
        // string or the structured moderation object; only use those.
        if (typeof data.detail === 'string') detail = { message: data.detail };
        else if (data.detail && typeof data.detail === 'object' && !Array.isArray(data.detail)) detail = data.detail;
      } catch (_) { /* non-JSON error body, fall through to generic message */ }

      showModerationModal(_moderationOptsFor(detail, label));
      if (submitBtn) submitBtn.disabled = false;
      return;
    }

    // Unexpected server error: fall back to a normal navigation so the
    // user isn't stuck with no feedback at all.
    form.submit();
  } catch (_) {
    // Network error: fall back to a normal navigation.
    form.submit();
  }
}

/**
 * Attach moderation to every form on the page that has data-moderate.
 * Client-side word list gives instant field highlighting only, it must never
 * short-circuit the submit. The client and server word lists overlap almost
 * entirely, so if a client-side hit stopped the request here, a repeat
 * offender's 2nd/3rd attempt would never reach the server, the warning count
 * would never advance, and the account could never actually get blocked.
 * The server is the sole source of truth for warning/block escalation;
 * every submit always goes through submitModerated() below.
 * Call once after DOMContentLoaded.
 */
function attachModerationToForms() {
  const forms = document.querySelectorAll('form[data-moderate]');
  forms.forEach(form => {
    form.addEventListener('submit', e => {
      e.preventDefault();

      const result = moderateForm(form);
      if (!result.clean) {
        // Highlight the offending field only; still fall through to the
        // real server round-trip below so the warning gets logged.
        result.field.classList.add('ring-2', 'ring-red-400', 'border-red-400');
        result.field.addEventListener('input', () => {
          result.field.classList.remove('ring-2', 'ring-red-400', 'border-red-400');
        }, { once: true });
      }

      submitModerated(form);
    });
  });
}

document.addEventListener('DOMContentLoaded', attachModerationToForms);
