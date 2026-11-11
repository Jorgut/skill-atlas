/* Skill Atlas — motion.js
 *
 * Progressive enhancement only. The three pages are plain, readable HTML; this
 * file adds:
 *   - scroll reveals for section headings and cards/figures/links
 *   - terminal presentation: types the existing command line, then streams the
 *     existing output (nothing is invented, the final text is byte-identical)
 *   - sticky-header depth once the page is scrolled
 *
 * No dependencies, no trackers, no network requests. Everything is skipped
 * when the visitor prefers reduced motion, and the page stays fully usable
 * when JavaScript is disabled or this file fails to load.
 */
(function () {
  'use strict';

  var root = document.documentElement;
  var reduceMotion = window.matchMedia
    ? window.matchMedia('(prefers-reduced-motion: reduce)')
    : { matches: false };
  var observerSupported = 'IntersectionObserver' in window;

  var REVEAL_SELECTOR = [
    'main section:not(.hero) > h2',
    'main section:not(.hero) > .section-note',
    'main .grid > .card',
    'main figure',
    'main .table-wrap',
    'main .links > a'
  ].join(', ');

  var motionReady = false;
  var reveals = null;
  var revealObserver = null;
  var terminalObserver = null;
  var terminals = [];

  initHeader();

  if (!reduceMotion.matches && observerSupported) {
    enableMotion();
  }

  if (typeof reduceMotion.addEventListener === 'function') {
    reduceMotion.addEventListener('change', onPreferenceChange);
  } else if (typeof reduceMotion.addListener === 'function') {
    reduceMotion.addListener(onPreferenceChange);
  }

  function onPreferenceChange() {
    if (reduceMotion.matches) {
      disableMotion();
    } else if (!motionReady && observerSupported) {
      enableMotion();
    }
  }

  /* --------------------------------------------------------------------- */
  /* Sticky header                                                          */
  /* --------------------------------------------------------------------- */

  function initHeader() {
    var header = document.querySelector('header.site');
    if (!header) return;

    var ticking = false;

    function update() {
      ticking = false;
      header.classList.toggle('is-scrolled', (window.scrollY || window.pageYOffset || 0) > 6);
    }

    function requestUpdate() {
      if (ticking) return;
      ticking = true;
      if (window.requestAnimationFrame) {
        window.requestAnimationFrame(update);
      } else {
        update();
      }
    }

    window.addEventListener('scroll', requestUpdate, { passive: true });
    window.addEventListener('resize', requestUpdate, { passive: true });
    update();
  }

  /* --------------------------------------------------------------------- */
  /* Scroll reveals                                                         */
  /* --------------------------------------------------------------------- */

  function enableMotion() {
    if (motionReady) return;
    try {
      setupReveals();
      setupTerminals();
      motionReady = true;
      root.classList.add('js-ready');
    } catch (error) {
      disableMotion();
    }
  }

  function setupReveals() {
    reveals = document.querySelectorAll(REVEAL_SELECTOR);
    var hidden = [];

    for (var i = 0; i < reveals.length; i++) {
      if (isBelowViewport(reveals[i])) {
        reveals[i].classList.add('reveal');
        hidden.push(reveals[i]);
      }
    }

    if (!hidden.length) return;

    revealObserver = new IntersectionObserver(onRevealEntry, {
      rootMargin: '0px 0px -8% 0px',
      threshold: 0.01
    });

    for (var j = 0; j < hidden.length; j++) {
      revealObserver.observe(hidden[j]);
    }

    document.addEventListener('focusin', onFocusIn);
  }

  function isBelowViewport(element) {
    var rect = element.getBoundingClientRect();
    var viewport = window.innerHeight || document.documentElement.clientHeight;
    return rect.top >= viewport * 0.94;
  }

  function onRevealEntry(entries) {
    for (var i = 0; i < entries.length; i++) {
      if (!entries[i].isIntersecting) continue;
      if (revealObserver) revealObserver.unobserve(entries[i].target);
      reveal(entries[i].target);
    }
  }

  function reveal(element) {
    if (!element.classList.contains('reveal') || element.classList.contains('is-visible')) return;

    element.classList.add('is-visible');

    var cleaned = false;

    function cleanup() {
      if (cleaned) return;
      cleaned = true;
      element.classList.remove('reveal', 'is-visible');
      element.removeEventListener('transitionend', onTransitionEnd);
    }

    function onTransitionEnd(event) {
      if (event.target === element && event.propertyName === 'opacity') cleanup();
    }

    element.addEventListener('transitionend', onTransitionEnd);
    // Safety net: cleanup even if the transition never fires (e.g. the visitor
    // switches to reduced motion mid-reveal).
    window.setTimeout(cleanup, 1100);
  }

  function onFocusIn(event) {
    var element = event.target;
    while (element && element !== document.body) {
      if (element.classList && element.classList.contains('reveal')) {
        if (revealObserver) revealObserver.unobserve(element);
        reveal(element);
        return;
      }
      element = element.parentElement;
    }
  }

  /* --------------------------------------------------------------------- */
  /* Terminal demo                                                          */
  /* --------------------------------------------------------------------- */

  function setupTerminals() {
    if (!observerSupported) return; // No reveal/typing without IntersectionObserver.

    var pres = document.querySelectorAll('.demo pre');
    terminals = [];

    for (var i = 0; i < pres.length; i++) {
      var pre = pres[i];
      var code = pre.querySelector('code');
      if (!code) continue;

      var full = code.textContent;
      var parts = splitDemoText(full);
      if (!parts) continue;

      var position = viewportPosition(pre);
      if (position === 'above') continue; // Never mutate demos the visitor has scrolled past.

      // Reserve the final height before the text changes so typing never shifts
      // the page layout. The demo text does not wrap (overflow-x: auto), so the
      // line count stays the same at every width.
      var height = pre.getBoundingClientRect().height;
      if (height > 0) pre.style.minHeight = Math.ceil(height) + 'px';
      pre.classList.add('term');

      terminals.push({
        pre: pre,
        code: code,
        full: full,
        command: parts.command,
        output: parts.output,
        separator: parts.separator,
        index: terminals.length,
        position: position,
        started: false,
        cancelled: false,
        typed: null,
        caret: null,
        accessible: null,
        timer: 0,
        startTimer: 0
      });
    }

    if (!terminals.length) return;

    terminalObserver = new IntersectionObserver(onTerminalEntry, {
      rootMargin: '0px 0px -6% 0px',
      threshold: 0
    });

    for (var j = 0; j < terminals.length; j++) {
      var term = terminals[j];
      if (term.position === 'visible') {
        scheduleTerminal(term, 480 + term.index * 220);
      } else {
        terminalObserver.observe(term.pre);
      }
    }
  }

  // Splits the existing demo text at the first blank line: command block first,
  // then the output that is revealed line by line. No text is added or changed.
  function splitDemoText(text) {
    if (!text) return null;

    var lines = text.split('\n');
    var blankAt = lines.indexOf('');
    var command;
    var output;
    var separator;

    if (blankAt === -1) {
      command = text;
      output = '';
      separator = '';
    } else {
      command = lines.slice(0, blankAt).join('\n');
      output = lines.slice(blankAt + 1).join('\n');
      separator = '\n\n';
    }

    if (!command) return null;
    return { command: command, output: output, separator: separator };
  }

  function viewportPosition(element) {
    var rect = element.getBoundingClientRect();
    var viewport = window.innerHeight || document.documentElement.clientHeight;
    if (rect.bottom <= 0) return 'above';
    if (rect.top >= viewport * 0.94) return 'below';
    return 'visible';
  }

  function findTerminal(pre) {
    for (var i = 0; i < terminals.length; i++) {
      if (terminals[i].pre === pre) return terminals[i];
    }
    return null;
  }

  function onTerminalEntry(entries) {
    for (var i = 0; i < entries.length; i++) {
      var entry = entries[i];
      if (!entry.isIntersecting) continue;
      var term = findTerminal(entry.target);
      if (terminalObserver) terminalObserver.unobserve(entry.target);
      if (term) scheduleTerminal(term, 200 + term.index * 60);
    }
  }

  function scheduleTerminal(term, delay) {
    if (term.started || term.cancelled) return;
    term.startTimer = window.setTimeout(function () {
      startTerminal(term);
    }, delay);
  }

  function startTerminal(term) {
    if (!motionReady || term.started || term.cancelled || reduceMotion.matches) return;
    term.started = true;

    var code = term.code;

    // Keep the full text available to assistive technology while the visual
    // copy is being typed.
    var accessible = document.createElement('span');
    accessible.className = 'sr-only';
    accessible.textContent = term.full;

    var typed = document.createElement('span');
    typed.className = 'term-typed';

    var caret = document.createElement('span');
    caret.className = 'term-caret';
    caret.setAttribute('aria-hidden', 'true');

    code.setAttribute('aria-hidden', 'true');
    code.textContent = '';
    code.appendChild(typed);
    code.appendChild(caret);
    term.pre.appendChild(accessible);

    term.typed = typed;
    term.caret = caret;
    term.accessible = accessible;

    typeCommand(term);
  }

  function typeCommand(term) {
    var text = term.command;
    var perChar = Math.max(9, Math.min(24, Math.round(1100 / Math.max(1, text.length))));
    var shown = 0;

    function step() {
      if (term.cancelled) return;
      shown += 1;
      term.typed.textContent = text.slice(0, shown);
      if (shown < text.length) {
        term.timer = window.setTimeout(step, perChar);
        return;
      }
      streamOutput(term);
    }

    term.timer = window.setTimeout(step, perChar);
  }

  function streamOutput(term) {
    term.typed.textContent = term.command + term.separator;

    var lines = term.output ? term.output.split('\n') : [];
    var shown = 0;

    function step() {
      if (term.cancelled) return;
      if (shown >= lines.length) {
        finishTerminal(term);
        return;
      }
      term.typed.textContent += lines[shown] + (shown < lines.length - 1 ? '\n' : '');
      shown += 1;
      term.timer = window.setTimeout(step, 70);
    }

    if (!lines.length) {
      finishTerminal(term);
      return;
    }

    term.timer = window.setTimeout(step, 90);
  }

  function finishTerminal(term) {
    if (term.cancelled) return;
    // Final state is exactly the original text.
    term.typed.textContent = term.full;
    if (term.caret && term.caret.parentNode) term.caret.parentNode.removeChild(term.caret);
    term.caret = null;
  }

  /* --------------------------------------------------------------------- */
  /* Reduced motion / teardown                                              */
  /* --------------------------------------------------------------------- */

  function disableMotion() {
    motionReady = false;
    root.classList.remove('js-ready');

    if (revealObserver) {
      revealObserver.disconnect();
      revealObserver = null;
    }
    if (terminalObserver) {
      terminalObserver.disconnect();
      terminalObserver = null;
    }
    document.removeEventListener('focusin', onFocusIn);

    var visible = document.querySelectorAll('.reveal');
    for (var i = 0; i < visible.length; i++) {
      visible[i].classList.remove('reveal', 'is-visible');
    }

    for (var j = 0; j < terminals.length; j++) {
      restoreTerminal(terminals[j]);
    }
    terminals = [];
  }

  function restoreTerminal(term) {
    term.cancelled = true;
    if (term.timer) window.clearTimeout(term.timer);
    if (term.startTimer) window.clearTimeout(term.startTimer);

    term.code.textContent = term.full;
    term.code.removeAttribute('aria-hidden');
    if (term.accessible && term.accessible.parentNode) {
      term.accessible.parentNode.removeChild(term.accessible);
    }
    term.pre.style.minHeight = '';
    term.pre.classList.remove('term');
  }
})();
