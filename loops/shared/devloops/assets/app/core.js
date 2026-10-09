/* core.js: DOM helpers, a small event bus, local preferences, the theme, status tables, tooltips,
   and the formatters every view uses. Nothing here touches the page when the file loads, so the
   pure parts (DL.fmt, DL.STATUS) run under node --test. */
(function (DL) {
  'use strict';

  /* --- DOM ------------------------------------------------------------------------------------ */
  var SVG = 'http://www.w3.org/2000/svg';
  DL.$ = function (s, c) { return (c || document).querySelector(s); };
  DL.$$ = function (s, c) { return Array.prototype.slice.call((c || document).querySelectorAll(s)); };
  /* An element; `text` is set with textContent (model-written text never becomes HTML). */
  DL.el = function (tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  };
  /* Append children (elements, strings, or arrays of them; null skipped); returns `parent`. */
  DL.add = function (parent) {
    for (var i = 1; i < arguments.length; i++) {
      var c = arguments[i];
      if (c == null || c === false) continue;
      if (Array.isArray(c)) { c.forEach(function (x) { DL.add(parent, x); }); continue; }
      parent.appendChild(typeof c === 'string' || typeof c === 'number' ? document.createTextNode(String(c)) : c);
    }
    return parent;
  };
  DL.icon = function (name, cls) {
    var s = document.createElementNS(SVG, 'svg');
    s.setAttribute('class', 'ic' + (cls ? ' ' + cls : ''));
    s.setAttribute('aria-hidden', 'true');
    var u = document.createElementNS(SVG, 'use');
    u.setAttribute('href', '#i-' + name);
    s.appendChild(u);
    return s;
  };
  /* A button: opts {cls, icon, iconOnly, key, on, title}. */
  DL.btn = function (label, opts) {
    opts = opts || {};
    var b = DL.el('button', 'btn' + (opts.cls ? ' ' + opts.cls : ''));
    b.type = 'button';
    if (opts.icon) b.appendChild(DL.icon(opts.icon));
    if (label) {
      if (opts.iconOnly) { b.setAttribute('aria-label', label); b.title = label + (opts.key ? ' (' + opts.key + ')' : ''); }
      else b.appendChild(document.createTextNode(label));
    }
    if (opts.title) b.title = opts.title;
    if (opts.on) b.addEventListener('click', opts.on);
    return b;
  };
  /* A link to an app route (`#/…`). */
  DL.link = function (href, text, cls) {
    var a = DL.el('a', cls || null, text);
    a.href = href;
    return a;
  };

  /* --- events: DL.bus.on('changed', fn) ------------------------------------------------------- */
  function Bus() { this.handlers = {}; }
  Bus.prototype.on = function (name, fn) { (this.handlers[name] = this.handlers[name] || []).push(fn); };
  Bus.prototype.off = function (name, fn) {
    var list = this.handlers[name] || [], at = list.indexOf(fn);
    if (at >= 0) list.splice(at, 1);
  };
  Bus.prototype.emit = function (name, value) {
    (this.handlers[name] || []).slice().forEach(function (fn) { fn(value); });
  };
  DL.Bus = Bus;
  DL.bus = new Bus();

  /* --- preferences (per browser; a private window may refuse them) ----------------------------- */
  DL.store = function (k, v) {
    try {
      if (v === undefined) return window.localStorage.getItem('devloops-' + k);
      window.localStorage.setItem('devloops-' + k, v);
    } catch (e) { return null; }
    return null;
  };

  /* --- theme ---------------------------------------------------------------------------------- */
  DL.theme = {
    apply: function (t) {
      var root = document.documentElement;
      if (t) root.setAttribute('data-theme', t); else root.removeAttribute('data-theme');
    },
    init: function () { var t = DL.store('theme'); if (t) DL.theme.apply(t); },
    toggle: function () {
      var root = document.documentElement, t = root.getAttribute('data-theme');
      var dark = t === 'dark' || (!t && window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches);
      var next = dark ? 'light' : 'dark';
      DL.theme.apply(next);
      DL.store('theme', next);
    }
  };

  /* --- status: (label, icon, tone); the icon and label travel with the color ------------------- */
  DL.STATUS = {
    run: {
      'completed': ['Completed', '✓', 'good'],
      'awaiting-approval': ['Awaiting approval', '⏸', 'warning'],
      'planning': ['Planning', '◷', 'neutral'],
      'implementing': ['Implementing', '◷', 'neutral'],
      'stopped-on-failure': ['Stopped on failure', '✕', 'critical'],
      'stopped-on-input-error': ['Stopped on input error', '✕', 'critical'],
      'stopped-on-service-error': ['Stopped on service error', '!', 'serious'],
      'not-started': ['Not started', '–', 'muted']
    },
    trial: {
      'passed': ['Passed', '✓', 'good'],
      'failed': ['Failed', '✕', 'critical'],
      'void': ['Voided (not counted)', '!', 'serious'],
      'in-progress': ['In progress', '◷', 'neutral']
    },
    milestone: {
      'achieved': ['Achieved', '✓', 'good'],
      'failed': ['Failed', '✕', 'critical'],
      'in-progress': ['In progress', '◷', 'neutral'],
      'pending': ['Pending', '–', 'muted']
    },
    orchestrator: {
      'running': ['Running', '◷', 'neutral'],
      'paused': ['Paused', '⏸', 'warning'],
      'completed': ['Completed', '✓', 'good'],
      'stopped': ['Stopped', '✕', 'critical']
    },
    answer: {
      'developer': ['Your answer', '✓', 'good'],
      'accepted': ['Suggestion accepted', '!', 'warning'],
      'suggested': ['Suggested, not accepted yet', '◷', 'neutral'],
      'none': ['Unanswered', '•', 'critical']
    },
    criterion: {
      'passing': ['Passing', '✓', 'good'],
      'failing': ['Failing', '✕', 'critical'],
      'unchecked': ['Not checked', '–', 'muted']
    }
  };
  /* `[label, icon, tone]` of `status` in table `table` (a DL.STATUS key). */
  DL.status = function (status, table) {
    return (DL.STATUS[table] || {})[status] || [status || 'unknown', '•', 'muted'];
  };
  DL.pill = function (status, table) {
    var s = DL.status(status, table), p = DL.el('span', 'pill tone-' + s[2]);
    DL.add(p, DL.el('span', null, s[1]), ' ' + s[0]);
    p.firstChild.setAttribute('aria-hidden', 'true');
    return p;
  };

  /* --- tooltips: any element with data-tip ---------------------------------------------------- */
  DL.tips = function (scope) {
    var tip = DL.$('#tip');
    if (!tip) return;
    function show(n, x, y) {
      tip.textContent = n.getAttribute('data-tip');
      tip.style.display = 'block';
      var w = tip.offsetWidth, h = tip.offsetHeight;
      tip.style.left = Math.min(x + 14, window.innerWidth - w - 8) + 'px';
      tip.style.top = Math.max(8, y - h - 10) + 'px';
    }
    function hide() { tip.style.display = 'none'; }
    DL.$$('[data-tip]', scope).forEach(function (n) {
      if (n._tip) return;
      n._tip = true;
      n.addEventListener('mousemove', function (ev) { show(n, ev.clientX, ev.clientY); });
      n.addEventListener('mouseleave', hide);
      n.addEventListener('focus', function () { var r = n.getBoundingClientRect(); show(n, r.left, r.top); });
      n.addEventListener('blur', hide);
    });
  };

  /* --- formatting (as dashboard.py's money, number, duration) ---------------------------------- */
  function group(n) { return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ','); }
  var fmt = DL.fmt = {
    money: function (v) {
      if (v == null) return '–';
      var neg = v < 0, cents = Math.round(Math.abs(v) * 100);
      return (neg ? '-' : '') + '$' + group(Math.floor(cents / 100)) + '.' + String(cents % 100).padStart(2, '0');
    },
    number: function (v) {
      if (v == null) return '–';
      var steps = [[1e9, 'B'], [1e6, 'M'], [1e3, 'k']];
      for (var i = 0; i < steps.length; i++) {
        if (Math.abs(v) >= steps[i][0]) return (v / steps[i][0]).toFixed(1) + steps[i][1];
      }
      return group(Math.round(v));
    },
    tokens: function (v) { return fmt.number(v); },
    duration: function (s) {
      if (s == null) return '–';
      s = Math.round(s);
      if (s < 60) return s + 's';
      var m = Math.floor(s / 60), r = s % 60;
      if (m < 60) return m + 'm ' + String(r).padStart(2, '0') + 's';
      return Math.floor(m / 60) + 'h ' + String(m % 60).padStart(2, '0') + 'm';
    },
    /* a ratio (0.42) as "42%" */
    percent: function (v) { return v == null ? '–' : Math.round(v * 100) + '%'; },
    /* an ISO time as "2026-10-09 12:34:56 UTC" */
    time: function (iso) {
      if (!iso) return '–';
      var d = new Date(iso);
      if (isNaN(d.getTime())) return String(iso);
      return d.toISOString().slice(0, 19).replace('T', ' ') + ' UTC';
    },
    bytes: function (n) {
      if (n == null) return '–';
      var units = [[1 << 30, 'GB'], [1 << 20, 'MB'], [1 << 10, 'KB']];
      for (var i = 0; i < units.length; i++) {
        if (n >= units[i][0]) return (n / units[i][0]).toFixed(1) + ' ' + units[i][1];
      }
      return n + ' bytes';
    },
    plural: function (n, word) { return n + ' ' + word + (n === 1 ? '' : 's'); }
  };
})(window.DL = window.DL || {});
