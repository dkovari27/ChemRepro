/**
 * Layer 1 — client-side content moderation.
 *
 * Uses whole-word matching only (\b boundaries) to avoid false positives
 * on chemistry terms (e.g. "cummene" does NOT match "cum").
 *
 * This is a first line of defence only. The server applies the same check
 * independently, so bypassing this script does not bypass moderation.
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
 * Attach moderation to every form on the page that has data-moderate="true"
 * or contains a textarea (i.e. user-authored content forms).
 * Call once after DOMContentLoaded.
 */
function attachModerationToForms() {
  const forms = document.querySelectorAll('form[data-moderate]');
  forms.forEach(form => {
    form.addEventListener('submit', e => {
      // Remove any previous error banner
      form.querySelectorAll('.moderation-error').forEach(el => el.remove());

      const result = moderateForm(form);
      if (!result.clean) {
        e.preventDefault();

        // Highlight the offending field
        result.field.classList.add('ring-2', 'ring-red-400', 'border-red-400');
        result.field.addEventListener('input', () => {
          result.field.classList.remove('ring-2', 'ring-red-400', 'border-red-400');
        }, { once: true });

        // Show inline error just above the submit button (or at top of form)
        const banner = document.createElement('p');
        banner.className = 'moderation-error text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2';
        banner.textContent = 'Your text contains language that is not allowed on ChemRepro. Please revise before submitting.';

        const submitBtn = form.querySelector('[type="submit"]');
        submitBtn
          ? submitBtn.before(banner)
          : form.appendChild(banner);

        result.field.focus();
      }
    });
  });
}

document.addEventListener('DOMContentLoaded', attachModerationToForms);
