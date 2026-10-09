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
    plural: function (n, word) { return n + ' ' + word + (n === 1 ? '' : 's'); },
    /* a Totals' tokens, spelled out: "input 1.2k · output 300 · cache write 5.0k · cache read 20.0k" */
    tokenParts: function (t) {
      t = t || {};
      return 'input ' + fmt.number(t.input || 0) + ' · output ' + fmt.number(t.output || 0) +
        ' · cache write ' + fmt.number(t.cache_creation || 0) + ' · cache read ' + fmt.number(t.cache_read || 0);
    }
  };

  /* --- view building blocks ------------------------------------------------------------------ */
  /* Text whose `commands` and paths are between backticks: text and <code> nodes. */
  DL.ticks = function (text) {
    var frag = document.createDocumentFragment();
    String(text == null ? '' : text).split('`').forEach(function (part, i) {
      if (part) frag.appendChild(i % 2 ? DL.el('code', null, part) : document.createTextNode(part));
    });
    return frag;
  };
  /* A view's heading: its title, a badge (an element), and a line under it (text or element). */
  DL.head = function (title, badge, sub) {
    var head = DL.el('div', 'view-head'), box = DL.el('div', 'title'), h = DL.el('h2', null, title);
    if (badge) DL.add(h, ' ', badge);
    DL.add(box, h, sub ? DL.add(DL.el('div', 'sub'), sub) : null);
    head.appendChild(box);
    return head;
  };
  /* One figure of a KPI row: value is text or an element; `tip` a tooltip. */
  DL.kpi = function (label, value, sub, tip) {
    var t = DL.el('div', 'tile'), v = DL.el('div', 'tile-value');
    DL.add(v, value);
    if (tip) { v.setAttribute('data-tip', tip); v.tabIndex = 0; }
    DL.add(t, DL.el('div', 'tile-label', label), v, sub ? DL.el('div', 'tile-sub', sub) : null);
    return t;
  };
  DL.kpis = function (tiles, compact, label) {
    var s = DL.el('section', 'kpis' + (compact ? ' compact' : ''));
    if (label) s.setAttribute('aria-label', label);
    return DL.add(s, tiles);
  };
  /* A Totals' token count: the total, its parts in a tooltip, and "partial" when some call did
     not record its usage (the sums are then a lower bound). */
  DL.tokens = function (totals) {
    var t = (totals && totals.tokens) || {}, span = DL.el('span', 'tok', DL.fmt.tokens(t.total || 0));
    span.setAttribute('data-tip', DL.fmt.tokenParts(t) + (totals && totals.partial ? ' · partial: some calls did not record usage' : ''));
    span.tabIndex = 0;
    if (totals && totals.partial) DL.add(span, ' ', DL.el('span', 'partial', 'partial'));
    return span;
  };
  /* A table cell; content is text, an element, or a list of them. */
  DL.td = function (content, cls) { return DL.add(DL.el('td', cls || null), content); };
  /* A bordered table: head `[[label, numeric]]`, rows `<tr>` elements; `opts.empty` is said
     instead when there are no rows, `opts.cls` classes the table. */
  DL.table = function (head, rows, opts) {
    opts = opts || {};
    if (!rows.length && opts.empty) return DL.el('p', 'muted', opts.empty);
    var wrap = DL.el('div', 'table-wrap'), t = DL.el('table', opts.cls || null), tr = DL.el('tr');
    head.forEach(function (h) { tr.appendChild(DL.el('th', h[1] ? 'num' : null, h[0])); });
    DL.add(t, DL.add(DL.el('thead'), tr), DL.add(DL.el('tbody'), rows));
    return DL.add(wrap, t);
  };
  /* A row that opens `href` when selected (click, Enter, or Space). */
  DL.rowLink = function (tr, href) {
    tr.classList.add('row-link');
    tr.tabIndex = 0;
    tr.addEventListener('click', function (ev) { if (!ev.target.closest('a, button')) location.hash = href; });
    tr.addEventListener('keydown', function (ev) {
      if ((ev.key === 'Enter' || ev.key === ' ') && ev.target === tr) { ev.preventDefault(); location.hash = href; }
    });
    return tr;
  };
  /* A filter over `rows`: a search box and, with `chips` ([[value, label]]), chips selecting
     the rows whose `data-<attr>` is that value (at most one pressed). Returns the toolbar. */
  DL.filter = function (rows, opts) {
    opts = opts || {};
    var bar = DL.el('div', 'toolbar'), input = DL.el('input', 'input'), chosen = null;
    input.type = 'search';
    input.placeholder = opts.placeholder || 'Filter…';
    input.setAttribute('aria-label', opts.placeholder || 'Filter');
    function apply() {
      var q = input.value.toLowerCase().trim();
      rows.forEach(function (r) {
        var ok = (!q || r.textContent.toLowerCase().indexOf(q) >= 0) &&
          (chosen === null || r.getAttribute('data-' + opts.attr) === chosen);
        r.classList.toggle('hidden-by-filter', !ok);
      });
    }
    input.addEventListener('input', apply);
    bar.appendChild(input);
    if (opts.chips && opts.chips.length > 1) {
      var group = DL.el('div', 'chips'), buttons = [];
      group.setAttribute('role', 'group');
      group.setAttribute('aria-label', opts.chipsLabel || 'Filter');
      opts.chips.forEach(function (c) {
        var b = DL.el('button', 'chip', c[1]);
        b.type = 'button';
        b.dataset.chip = c[0];
        b.setAttribute('aria-pressed', 'false');
        b.addEventListener('click', function () {
          chosen = chosen === c[0] ? null : c[0];
          buttons.forEach(function (x) { x.setAttribute('aria-pressed', String(x.dataset.chip === chosen)); });
          apply();
        });
        buttons.push(b);
        group.appendChild(b);
      });
      bar.appendChild(group);
    }
    bar.filterInput = input;
    return bar;
  };
})(window.DL = window.DL || {});
