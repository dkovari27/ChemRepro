'use strict';
(function () {

var STEP_KEY = 'crTourStep';
var DONE_KEY = 'crTourDone';

var STEPS = [
  {
    page: 'home',
    selector: 'input[name="doi"]',
    stepNum: 'Step 1 of 4',
    title: 'Find any chemistry paper',
    body: 'Paste a DOI — the unique ID printed on every published paper — into this box, then click <strong>Look up paper</strong>.'
        + '<br><br>Need one to try?&nbsp; <code>10.1021/jacs.0c01154</code>',
    nextLabel: "I’ll search now →",
    nextAction: 'dismiss',
  },
  {
    page: 'paper',
    selector: '#tour-rate-box',
    stepNum: 'Step 2 of 4',
    title: 'Rate this paper',
    body: 'If you have tried this reaction in the lab, record what happened here. '
        + 'Choose an outcome (did it work? did it fail?), add your observations, and submit. '
        + 'Your review appears under your chosen display name.',
    nextLabel: 'Next →',
    nextAction: 'advance',
  },
  {
    page: 'paper',
    selector: '#save-wrap',
    stepNum: 'Step 3 of 4',
    title: 'Save to your Collection',
    body: 'Click this button to save the paper to one of your named collections. '
        + 'You can also add private notes that only you can see.',
    nextLabel: 'Next →',
    nextAction: 'advance',
  },
  {
    page: 'paper',
    selector: '#reviews-section',
    stepNum: 'Step 4 of 4',
    title: 'Connect with other chemists',
    body: 'Click the <strong>···</strong> menu on any review card to follow that person, '
        + 'send a private message, or report a problem. '
        + 'You can also like reviews and add your own comments.',
    nextLabel: 'Finish tour ✔',
    nextAction: 'finish',
  },
];

function getStep() { return parseInt(localStorage.getItem(STEP_KEY) || '-1', 10); }
function setStep(n) { localStorage.setItem(STEP_KEY, String(n)); }
function isDone() { return localStorage.getItem(DONE_KEY) === '1'; }
function markDone() { localStorage.setItem(DONE_KEY, '1'); localStorage.removeItem(STEP_KEY); }

function currentPage() {
  var p = window.location.pathname;
  if (p === '/') return 'home';
  if (p.startsWith('/paper/') || p.startsWith('/classic/paper/')) return 'paper';
  return 'other';
}

function injectStyles() {
  if (document.getElementById('cr-tour-style')) return;
  var s = document.createElement('style');
  s.id = 'cr-tour-style';
  s.textContent = [
    '#cr-tour-spotlight{position:fixed;border-radius:12px;box-shadow:0 0 0 9999px rgba(0,0,0,0.52);pointer-events:none;z-index:8000;transition:top .25s,left .25s,width .25s,height .25s}',
    '#cr-tour-tip{position:fixed;z-index:9000;background:#fff;border-radius:14px;padding:18px 20px 14px;width:300px;box-shadow:0 8px 32px rgba(0,0,0,0.18),0 0 0 1px rgba(0,0,0,0.06);font-family:inherit}',
    '#cr-tour-tip code{background:#f1f5f9;padding:2px 6px;border-radius:4px;font-size:11px;font-family:monospace}',
    '#cr-tour-step-label{font-size:10px;color:#64748b;font-weight:700;text-transform:uppercase;letter-spacing:.07em;margin-bottom:5px}',
    '#cr-tour-title{font-size:15px;font-weight:700;color:#0f172a;margin-bottom:7px}',
    '#cr-tour-body{font-size:13px;color:#475569;line-height:1.55;margin-bottom:14px}',
    '#cr-tour-actions{display:flex;justify-content:space-between;align-items:center}',
    '#cr-tour-skip{font-size:12px;color:#94a3b8;border:none;background:none;cursor:pointer;padding:0;transition:color .15s}',
    '#cr-tour-skip:hover{color:#64748b}',
    '#cr-tour-next{font-size:13px;font-weight:600;color:#fff;background:#1e40af;border:none;border-radius:8px;padding:8px 16px;cursor:pointer;transition:background .15s}',
    '#cr-tour-next:hover{background:#1e3a8a}',
  ].join('');
  document.head.appendChild(s);
}

var _spotlight = null;
var _tip = null;
var _resizeHandler = null;

function ensureElements() {
  if (!_spotlight) {
    _spotlight = document.createElement('div');
    _spotlight.id = 'cr-tour-spotlight';
    document.body.appendChild(_spotlight);
  }
  if (!_tip) {
    _tip = document.createElement('div');
    _tip.id = 'cr-tour-tip';
    _tip.innerHTML =
      '<div id="cr-tour-step-label"></div>' +
      '<div id="cr-tour-title"></div>' +
      '<div id="cr-tour-body"></div>' +
      '<div id="cr-tour-actions">' +
        '<button id="cr-tour-skip">Skip tour</button>' +
        '<button id="cr-tour-next">Next</button>' +
      '</div>';
    document.body.appendChild(_tip);
    document.getElementById('cr-tour-skip').addEventListener('click', function () { markDone(); hide(); });
    document.getElementById('cr-tour-next').addEventListener('click', onNext);
  }
}

function hide() {
  if (_spotlight) _spotlight.style.display = 'none';
  if (_tip) _tip.style.display = 'none';
}

function positionAround(target) {
  var PAD = 10;
  var TIP_W = 300;
  var TIP_H = 240;
  var rect = target.getBoundingClientRect();

  _spotlight.style.display = 'block';
  _spotlight.style.top = (rect.top - PAD) + 'px';
  _spotlight.style.left = (rect.left - PAD) + 'px';
  _spotlight.style.width = (rect.width + PAD * 2) + 'px';
  _spotlight.style.height = (rect.height + PAD * 2) + 'px';

  var belowSpace = window.innerHeight - rect.bottom - PAD * 2;
  var tipTop = belowSpace >= TIP_H
    ? rect.bottom + PAD * 2
    : Math.max(8, rect.top - TIP_H - PAD * 2);

  var tipLeft = rect.left;
  if (tipLeft + TIP_W > window.innerWidth - 16) tipLeft = window.innerWidth - TIP_W - 16;
  if (tipLeft < 16) tipLeft = 16;

  _tip.style.display = 'block';
  _tip.style.top = tipTop + 'px';
  _tip.style.left = tipLeft + 'px';
}

function showStep(idx) {
  var step = STEPS[idx];
  if (!step) return;
  if (step.page !== currentPage()) return;

  var target = document.querySelector(step.selector);
  if (!target) return;

  injectStyles();
  ensureElements();

  document.getElementById('cr-tour-step-label').textContent = step.stepNum;
  document.getElementById('cr-tour-title').textContent = step.title;
  document.getElementById('cr-tour-body').innerHTML = step.body;
  document.getElementById('cr-tour-next').textContent = step.nextLabel;

  target.scrollIntoView({ behavior: 'smooth', block: 'center' });

  setTimeout(function () { positionAround(target); }, 380);

  if (_resizeHandler) window.removeEventListener('resize', _resizeHandler);
  _resizeHandler = function () { positionAround(target); };
  window.addEventListener('resize', _resizeHandler, { passive: true });
}

function onNext() {
  var idx = getStep();
  var step = STEPS[idx];
  if (!step) return;

  if (step.nextAction === 'finish') { markDone(); hide(); return; }

  if (step.nextAction === 'dismiss') {
    setStep(idx + 1);
    hide();
    return;
  }

  // advance on same page
  var next = idx + 1;
  setStep(next);
  if (STEPS[next] && STEPS[next].page === currentPage()) {
    showStep(next);
  } else {
    hide();
  }
}

window.startTour = function () {
  markDone(); // reset
  localStorage.removeItem(DONE_KEY);
  setStep(0);
  setTimeout(function () { showStep(0); }, 300);
};

function init() {
  if (isDone()) return;
  var idx = getStep();
  if (idx < 0) return;
  setTimeout(function () { showStep(idx); }, 500);
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}

})();
