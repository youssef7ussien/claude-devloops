/* palette.js: "go to" (Ctrl+K or `/`; FR-022, research R-10). Names of views, loops, milestones,
   trials, calls, and files (`api/index`) match as the developer types; from three characters,
   after a 250 ms pause, the contents of files, conversations, and events are searched too: by the
   server (`api/search`), or, in an export, here over the embedded corpus (`d:search-corpus`) with
   the same rules as serve.py `search_corpus`. A result opens at its route: a file at its line, a
   call at its record, an event at its row. */
(function (DL) {
  'use strict';

  var MIN = 3, LIMIT = 40, NAMES = 50, PAUSE = 250;

  /* --- matching (pure; tested under node) ----------------------------------------------------- */

  /* How well `q` (lower case) matches an item: inside its label (best at its start), inside its
     detail, or as the label's characters in order (more for runs); 0 when it does not match. */
  function score(item, q) {
    if (!q) return 1;
    var label = String(item.label || '').toLowerCase(), detail = String(item.detail || '').toLowerCase();
    var at = label.indexOf(q);
    if (at === 0) return 100;
    if (at > 0) return 80;
    if (detail.indexOf(q) >= 0) return 60;
    var k = 0, s = 0, last = -2;
    for (var i = 0; i < q.length; i++) {
      k = label.indexOf(q[i], k);
      if (k < 0) return 0;
      s += k === last + 1 ? 3 : 1;
      last = k;
      k += 1;
    }
    return Math.min(s, 50);
  }

  /* The index items matching `query`, best first (ties keep their order), at most NAMES. */
  function names(items, query) {
    var q = String(query || '').toLowerCase().trim();
    return (items || []).map(function (it, k) { return { it: it, s: score(it, q), k: k }; })
      .filter(function (x) { return x.s > 0; })
      .sort(function (a, b) { return b.s - a.s || a.k - b.k; })
      .slice(0, NAMES).map(function (x) { return x.it; });
  }

  /* `text` in lower case, character for character: as serve.py `fold_case` (a character whose
     lower case is longer, like `İ`, is kept, so offsets stay those of `text`). */
  function fold(text) {
    var low = text.toLowerCase();
    if (low.length === text.length) return low;
    return text.split('').map(function (c) { var l = c.toLowerCase(); return l.length === 1 ? l : c; }).join('');
  }

  /* The first match of `needle` (folded) in `text`: as serve.py `_hit`. */
  function hitOf(text, needle) {
    var at = fold(text).indexOf(needle);
    if (at < 0) return null;
    var start = text.lastIndexOf('\n', at - 1) + 1, end = text.indexOf('\n', at);
    if (at === 0) start = 0;
    if (end < 0) end = text.length;
    var line = text.slice(start, end), col = at - start, n = needle.length;
    return { line: text.slice(0, at).split('\n').length, before: line.slice(Math.max(0, col - 40), col),
      match: line.slice(col, col + n), after: line.slice(col + n, col + n + 80) };
  }

  /* SearchHits of `query` in `corpus` ([{kind, id, label, route, text}]): as serve.py
     `search_corpus`. */
  function content(corpus, query, limit) {
    var needle = fold(String(query || '')), found = [];
    limit = limit || LIMIT;
    if (needle.length < MIN) return found;
    for (var i = 0; i < (corpus || []).length && found.length < limit; i++) {
      var item = corpus[i], hit = item.text ? hitOf(item.text, needle) : null;
      if (!hit) continue;
      var joiner = item.route.indexOf('?') >= 0 ? '&' : '?';
      var route = item.route + joiner + (item.kind === 'file' ? 'line=' + hit.line : 'at=' + (hit.line - 1));
      found.push({ kind: item.kind, id: item.id, label: item.label, route: route,
        line: hit.line, before: hit.before, match: hit.match, after: hit.after });
    }
    return found;
  }

  DL.search = { score: score, names: names, fold: fold, hitOf: hitOf, content: content,
    embedded: embeddedHits, MIN: MIN };

  /* --- the dialog ------------------------------------------------------------------------------- */

  var dlg = null, input = null, list = null, rows = [], sel = 0, timer = null, seq = 0;
  var ICONS = { view: 'grid', loop: 'loop', milestone: 'flow', trial: 'check', call: 'chat', file: 'file', event: 'list' };

  function go(route) {
    close();
    if (location.hash === route) DL.router.mount(); else location.hash = route;
  }

  function select(k) {
    var opts = rows.filter(function (r) { return r.route; });
    if (!opts.length) return;
    sel = (k + opts.length) % opts.length;
    rows.forEach(function (r) { if (r.li.getAttribute('role') === 'option') r.li.setAttribute('aria-selected', 'false'); });
    opts[sel].li.setAttribute('aria-selected', 'true');
    opts[sel].li.scrollIntoView({ block: 'nearest' });
  }

  function row(icon, label, detail, route, snippet) {
    var li = DL.el('li');
    li.setAttribute('role', 'option');
    li.setAttribute('aria-selected', 'false');
    var name = DL.el('span', 'l', label);
    name.title = label;
    DL.add(li, DL.icon(icon), name);
    if (snippet) {
      var p = DL.el('span', 'p snip'); /* the server sends up to 40 characters before the match */
      DL.add(p, (snippet.before.length >= 40 ? '…' : '') + snippet.before, DL.el('mark', null, snippet.match), snippet.after);
      li.appendChild(p);
    } else if (detail) {
      li.appendChild(DL.el('span', 'p', detail));
    }
    li.addEventListener('mousedown', function (ev) { ev.preventDefault(); go(route); });
    return { li: li, route: route };
  }

  function group(label) {
    var li = DL.el('li', 'group', label);
    li.setAttribute('role', 'presentation');
    return { li: li, route: null };
  }

  function draw(found, hits, pending) {
    rows = [];
    if (found.length) rows.push(group('Go to'));
    found.forEach(function (it) { rows.push(row(ICONS[it.kind] || 'file', it.label, it.detail, it.route)); });
    if (hits && hits.length) {
      rows.push(group('In contents'));
      hits.forEach(function (h) {
        rows.push(row(ICONS[h.kind] || 'file', h.label + (h.kind === 'file' ? ':' + h.line : ''), null, h.route, h));
      });
    }
    if (pending) rows.push(group('Searching contents…'));
    if (!found.length && hits && !hits.length && !pending) rows.push(group('Nothing found'));
    list.textContent = '';
    rows.forEach(function (r) { list.appendChild(r.li); });
    sel = 0;
    select(0);
  }

  /* An export's search: as `content`, over the embedded corpus, where a file item names its
     embedded file (`file: id`) instead of holding a copy of its text (contracts/export.md). A
     file's text is read from its element only when the search reaches it, and not kept, so a
     search that has its results reads no more files. */
  function embeddedText(item) {
    if (item.text != null || !item.file) return item.text;
    var node = document.getElementById('d:files/' + item.file);
    try { return node ? JSON.parse(node.textContent).text : null; } catch (e) { return null; }
  }
  function embeddedHits(corpus, q, limit) {
    var found = [], items = corpus.items || corpus;
    limit = limit || LIMIT;
    for (var i = 0; i < items.length && found.length < limit; i++) {
      var item = items[i], text = embeddedText(item);
      if (!text) continue;
      var hit = content([{ kind: item.kind, id: item.id, label: item.label, route: item.route, text: text }], q, 1);
      if (hit.length) found.push(hit[0]);
    }
    return found;
  }

  function contentHits(q) {
    if (DL.api.source() === 'embedded') {
      return DL.api.get('search-corpus').then(function (corpus) { return embeddedHits(corpus, q); });
    }
    return DL.api.get('search?q=' + encodeURIComponent(q)).then(function (d) { return d.results; });
  }

  function update() {
    var q = input.value, my = ++seq;
    if (timer) clearTimeout(timer);
    DL.api.get('index').then(function (d) {
      if (my !== seq) return;
      var found = names(d.items, q), long = q.trim().length >= MIN;
      draw(found, long ? null : [], long);
      if (!long) return;
      timer = setTimeout(function () {
        contentHits(q.trim()).then(function (hits) { if (my === seq) draw(found, hits, false); },
          function () { if (my === seq) draw(found, [], false); });
      }, PAUSE);
    }, function () {
      if (my === seq) { list.textContent = ''; list.appendChild(group('Could not load the names').li); }
    });
  }

  function init() {
    if (dlg) return true;
    dlg = DL.$('#palette');
    if (!dlg) return false;
    input = DL.$('input', dlg);
    list = DL.$('ul', dlg);
    input.addEventListener('input', update);
    input.addEventListener('keydown', function (ev) {
      if (ev.key === 'ArrowDown') { ev.preventDefault(); select(sel + 1); }
      else if (ev.key === 'ArrowUp') { ev.preventDefault(); select(sel - 1); }
      else if (ev.key === 'Enter') {
        ev.preventDefault();
        var opts = rows.filter(function (r) { return r.route; });
        if (opts[sel]) go(opts[sel].route);
      }
    });
    dlg.addEventListener('click', function (ev) { if (ev.target === dlg) close(); });
    return true;
  }

  function open() {
    if (!init()) return;
    if (!dlg.open) dlg.showModal();
    input.select();
    update();
  }

  function close() {
    if (timer) clearTimeout(timer);
    seq += 1;
    if (dlg && dlg.open) dlg.close();
  }

  /* Ctrl+K anywhere, or `/` outside a text field, opens it. */
  function start() {
    document.addEventListener('keydown', function (ev) {
      var typing = ev.target && ev.target.closest && ev.target.closest('input, textarea, select');
      if ((ev.key === 'k' || ev.key === 'K') && (ev.ctrlKey || ev.metaKey)) { ev.preventDefault(); open(); }
      else if (ev.key === '/' && !typing && !ev.ctrlKey && !ev.metaKey && !ev.altKey &&
        !(DL.viewer && DL.viewer.isOpen())) { ev.preventDefault(); open(); }
    });
  }

  DL.palette = { open: open, close: close, start: start };
})(window.DL = window.DL || {});
