'use strict';
(function () {

  var STEP_KEY = 'crTourStep';
  var DONE_KEY = 'crTourDone';

  var STEPS = [
    {
      page: 'demo-home',
      selector: 'input[name="doi"]',
      stepNum: 'Step 1 of 7',
      title: 'Find any chemistry paper',
      body: 'Paste a DOI into the search bar and click <strong>Look up paper</strong> '
        + 'to see the community reproducibility record for that paper.',
      nextLabel: 'Next →',
      nextAction: 'advance',
    },
    {
      page: 'demo-home',
      selector: '#tour-community-feed',
      stepNum: 'Step 2 of 7',
      title: 'Review cards',
      body: 'Papers you have personally reviewed appear under <strong>My reviewed papers</strong>. '
        + 'Below that, the community feed shows what other chemists have recently rated. '
        + 'Each card displays a <strong>★ score</strong> and the number of reports. '
        + 'Hover over the score to see the full breakdown, or click on the card to open the paper.',
      nextLabel: 'Next →',
      nextAction: 'navigate',
      navigateTo: '/paper/demo',
    },
    {
      page: 'paper',
      selector: '#tour-score-card',
      stepNum: 'Step 3 of 7',
      title: 'Paper score breakdown',
      body: 'Here you see the aggregated score for this specific paper. '
        + 'Each coloured row shows how many reviewers reported that outcome and its share of the total. '
        + 'On a real paper you can click any row to filter the reviews by that outcome.',
      nextLabel: 'Next →',
      nextAction: 'advance',
    },
    {
      page: 'paper',
      selector: '#tour-rate-box',
      stepNum: 'Step 4 of 7',
      title: 'Rate this paper',
      body: 'If you have tried a procedure of a paper in the lab, record what happened here. '
        + 'Choose an outcome (did it work? did it fail?, etc.), add your observations, '
        + 'add a picture or screenshot of a scheme if you want and submit. '
        + 'Your reviews will appear under your chosen display name.',
      nextLabel: 'Next →',
      nextAction: 'advance',
    },
    {
      page: 'paper',
      selector: '#save-wrap',
      stepNum: 'Step 5 of 7',
      title: 'Save to your collection',
      body: 'Click this button to save the paper to one of your private collection folders. '
        + 'You can also add notes to them.',
      nextLabel: 'Next →',
      nextAction: 'advance',
    },
    {
      page: 'paper',
      selector: '#tour-reviewer-name',
      fallback: '#reviews-section',
      stepNum: 'Step 6 of 7',
      title: 'Connect with other chemists',
      body: 'Click a reviewer\'s name to follow that person, '
        + 'send a private message, or report misconduct.',
      nextLabel: 'Next →',
      nextAction: 'advance',
      zoom: true,
    },
    {
      page: 'paper',
      selector: '#tour-review-actions',
      stepNum: 'Step 7 of 7',
      title: 'Interact with reviews',
      body: 'Use the action bar at the bottom of each review to '
        + '<strong>like</strong> it with the flask icon, post a <strong>comment</strong>, '
        + 'or <strong>share</strong> it with colleagues via WhatsApp, email, or LinkedIn.',
      nextLabel: 'Finish tour ✔',
      nextAction: 'finish',
      preferAbove: true,
    },
  ];

  function getStep() { return parseInt(localStorage.getItem(STEP_KEY) || '-1', 10); }
  function setStep(n) { localStorage.setItem(STEP_KEY, String(n)); }
  function isDone() { return localStorage.getItem(DONE_KEY) === '1'; }
  function markDone() { localStorage.setItem(DONE_KEY, '1'); localStorage.removeItem(STEP_KEY); }

  function currentPage() {
    var p = window.location.pathname;
    if (p === '/demo' || p === '/demo/') return 'demo-home';
    if (p === '/' || p === '/classic' || p === '/classic/') return 'home';
    if (p.startsWith('/paper/') || p.startsWith('/classic/paper/')) return 'paper';
    return 'other';
  }

  function injectStyles() {
    if (document.getElementById('cr-tour-style')) return;
    var s = document.createElement('style');
    s.id = 'cr-tour-style';
    s.textContent = [
      '#cr-tour-shield{position:fixed;inset:0;z-index:7999;pointer-events:all;background:transparent;display:none}',
      '#cr-tour-spotlight{position:fixed;border-radius:12px;box-shadow:0 0 0 9999px rgba(0,0,0,0.52);pointer-events:none;z-index:8000;opacity:1;transition:opacity .25s ease}',
      '#cr-tour-spotlight.zoomed{border-radius:8px;box-shadow:0 0 0 9999px rgba(0,0,0,0.68),0 0 0 3px #1e40af}',
      '#cr-tour-tip{position:fixed;z-index:9000;background:#fff;border-radius:14px;padding:18px 20px 14px;width:300px;box-shadow:0 8px 32px rgba(0,0,0,0.18),0 0 0 1px rgba(0,0,0,0.06);font-family:inherit;opacity:1;transition:opacity .25s ease}',
      '#cr-tour-tip code{background:#f1f5f9;padding:2px 6px;border-radius:4px;font-size:11px;font-family:monospace}',
      '#cr-tour-step-label{font-size:10px;color:#64748b;font-weight:700;text-transform:uppercase;letter-spacing:.07em;margin-bottom:5px}',
      '#cr-tour-title{font-size:15px;font-weight:700;color:#0f172a;margin-bottom:7px}',
      '#cr-tour-body{font-size:13px;color:#475569;line-height:1.55;margin-bottom:8px}',
      '#cr-tour-actions{display:flex;justify-content:space-between;align-items:center}',
      '#cr-tour-skip{font-size:12px;color:#94a3b8;border:none;background:none;cursor:pointer;padding:0;transition:color .15s;position:relative;z-index:9001}',
      '#cr-tour-skip:hover{color:#64748b}',
      '#cr-tour-next{font-size:13px;font-weight:600;color:#fff;background:#1e40af;border:none;border-radius:8px;padding:8px 16px;cursor:pointer;transition:background .15s;position:relative;z-index:9001}',
      '#cr-tour-next:hover{background:#1e3a8a}',
    ].join('');
    document.head.appendChild(s);
  }

  var _shield = null;
  var _spotlight = null;
  var _tip = null;
  var _resizeHandler = null;

  function ensureElements() {
    if (!_shield) {
      _shield = document.createElement('div');
      _shield.id = 'cr-tour-shield';
      document.body.appendChild(_shield);
    }
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
    if (_shield) _shield.style.display = 'none';
    if (_spotlight) _spotlight.style.display = 'none';
    if (_tip) _tip.style.display = 'none';
  }

  function positionAround(target, zoom, preferAbove) {
    var PAD = zoom ? 6 : 10;
    var TIP_W = 300;
    var TIP_H = 300;
    var rect = target.getBoundingClientRect();

    _shield.style.display = 'block';

    _spotlight.style.display = 'block';
    _spotlight.style.top = (rect.top - PAD) + 'px';
    _spotlight.style.left = (rect.left - PAD) + 'px';
    _spotlight.style.width = (rect.width + PAD * 2) + 'px';
    _spotlight.style.height = (rect.height + PAD * 2) + 'px';
    if (zoom) {
      _spotlight.classList.add('zoomed');
    } else {
      _spotlight.classList.remove('zoomed');
    }

    var belowSpace = window.innerHeight - rect.bottom - PAD * 2;
    var aboveSpace = rect.top - PAD * 2;
    var tipTop;
    if (preferAbove) {
      tipTop = aboveSpace >= TIP_H
        ? rect.top - TIP_H - PAD * 2
        : rect.bottom + PAD * 2;
    } else {
      tipTop = belowSpace >= TIP_H
        ? rect.bottom + PAD * 2
        : Math.max(8, rect.top - TIP_H - PAD * 2);
    }
    tipTop = Math.max(8, tipTop);

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
    var zoom = !!step.zoom;
    if (!target && step.fallback) {
      target = document.querySelector(step.fallback);
      zoom = false;
    }
    if (!target) return;

    injectStyles();
    ensureElements();

    document.getElementById('cr-tour-step-label').textContent = step.stepNum;
    document.getElementById('cr-tour-title').textContent = step.title;
    document.getElementById('cr-tour-body').innerHTML = step.body;
    document.getElementById('cr-tour-next').textContent = step.nextLabel;

    var above = !!step.preferAbove;
    var alreadyVisible = _spotlight && _spotlight.style.display === 'block';

    if (_resizeHandler) window.removeEventListener('resize', _resizeHandler);
    _resizeHandler = function () { positionAround(target, zoom, above); };
    window.addEventListener('resize', _resizeHandler, { passive: true });

    function placeAndReveal() {
      // Instant scroll so getBoundingClientRect is accurate on the very next frame
      target.scrollIntoView({ block: 'center' });
      requestAnimationFrame(function () {
        positionAround(target, zoom, above);
        requestAnimationFrame(function () {
          _spotlight.style.opacity = '1';
          _tip.style.opacity = '1';
        });
      });
    }

    // Always start invisible so every appearance fades in cleanly
    _spotlight.style.opacity = '0';
    _tip.style.opacity = '0';

    if (alreadyVisible) {
      setTimeout(placeAndReveal, 280);   // wait for fade-out to finish
    } else {
      requestAnimationFrame(placeAndReveal);
    }
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

    if (step.nextAction === 'navigate') {
      setStep(idx + 1);
      hide();
      window.location.href = step.navigateTo;
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
    localStorage.removeItem(DONE_KEY);
    setStep(0);
    if (currentPage() === 'demo-home') {
      setTimeout(function () { showStep(0); }, 300);
    } else {
      window.location.href = '/demo';
    }
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
