/* viewer.js: the file viewer dialog (port of assets/dashboard.js's viewer). One viewer per file
   kind; contents come from DL.api.file(ref), cached per file version. When the workspace changes
   and the open file has a new version, it is loaded again where the reader was (or at its end,
   when the reader was following it). */
(function (DL) {
  'use strict';

  var BIG = 20 * 1024 * 1024;
  var dlg = null, parts = {}, current = null, list = [], options = {}, opener = null;
  /* the files read last, newest last: going back and forth between a few files reads none of
     them again, and a long session does not keep every file it ever opened */
  var CACHE_FILES = 20;
  var cache = new Map(), bigOk = {}, files = [], seq = 0;
  function cached(id) {
    var hit = cache.get(id);
    if (hit) { cache.delete(id); cache.set(id, hit); }
    return hit;
  }
  function remember(id, entry) {
    cache.delete(id);
    cache.set(id, entry);
    while (cache.size > CACHE_FILES) cache.delete(cache.keys().next().value);
  }

  function prefs() {
    if (!DL.prefs) DL.prefs = { wrap: DL.store('wrap') !== '0', ln: DL.store('ln') !== '0' };
    return DL.prefs;
  }
  function code(text, lang, opts) {
    return DL.hl && DL.hl.codeView ? DL.hl.codeView(text, lang, opts) : DL.el('pre', 'code', text);
  }
  function pane(child) { var p = DL.el('div', 'v-pane'); if (child) p.appendChild(child); return p; }
  function nameOf(ref) { return String(ref.path || ref.id || '').split('/').pop(); }

  /* A file the Markdown links to: a listed file whose path is the link or ends with it. */
  function resolve(url) {
    url = String(url || '').replace(/^\.\//, '').split('#')[0];
    if (!url || /^[a-z][a-z0-9+.-]*:/i.test(url)) return null;
    var pool = (options.list || []).concat(files), i;
    for (i = 0; i < pool.length; i++) {
      var p = pool[i] && pool[i].path || '';
      if (p === url || p.slice(-url.length - 1) === '/' + url) return DL.router.href('file', { id: pool[i].id });
    }
    return null;
  }
  function flatten(trees, out) {
    (trees || []).forEach(function (n) {
      if (n.file) out.push(n.file);
      if (n.children) flatten(n.children, out);
    });
    return out;
  }

  /* --- viewers: one entry per kind; add a kind by adding an entry -------------------------------- */
  function jsonTree(text, lines) { return DL.hl && DL.hl.jsonTree ? DL.hl.jsonTree(text, lines) : null; }
  var VIEWERS = {
    /* `lines`: the mode that shows numbered lines, used when a file opens at a line */
    markdown: { modes: ['Rendered', 'Source'], lines: 'Source', render: function (c, m) {
      return m === 'Source' || !DL.md ? code(c.text, 'markdown') : pane(DL.md.render(c.text, { resolve: resolve }));
    } },
    json: { modes: ['Code', 'Tree'], lines: 'Code', render: function (c, m) { return m === 'Tree' && jsonTree(c.text) || code(c.text, 'json'); } },
    jsonl: { modes: ['Records', 'Lines'], lines: 'Lines', render: function (c, m) {
      return m === 'Records' && jsonTree(c.text, true) || code(c.text, 'json');
    } },
    code: { render: function (c) { return code(c.text, c.lang); } },
    log: { render: function (c) { return code(c.text, 'log'); } },
    text: { render: function (c) { return code(c.text, c.lang || 'text'); } },
    image: { modes: ['Fit', 'Actual size'], noText: true, render: function (c, m) {
      var b = DL.el('div', 'img-view' + (m === 'Actual size' ? ' actual' : '')), img = DL.el('img');
      img.src = c.src;
      img.alt = c.name;
      b.appendChild(img);
      return b;
    } },
    binary: { noText: true, render: function (c) {
      var p = pane(DL.el('p', null, 'This file is not text, so it cannot be shown here.'));
      var a = DL.el('a', 'btn', 'Download ' + c.name);
      a.href = c.src;
      a.download = c.name;
      p.appendChild(a);
      return p;
    } }
  };
  VIEWERS.large = VIEWERS.text; /* a large text file, sent whole by the server */

  /* --- the dialog ------------------------------------------------------------------------------ */
  function init() {
    if (dlg) return true;
    dlg = DL.$('#viewer');
    if (!dlg) return false;
    ['v-path', 'v-meta', 'v-tools', 'tabs', 'v-body', 'v-status', 'v-nav'].forEach(function (c) {
      parts[c] = DL.$('.' + c, dlg);
    });
    DL.$('[data-action="close"]', dlg).addEventListener('click', close);
    DL.$$('[data-step]', dlg).forEach(function (b) {
      b.addEventListener('click', function () { step(+b.getAttribute('data-step')); });
    });
    var max = DL.$('[data-action="max"]', dlg);
    function setMax(on) { dlg.classList.toggle('max', on); max.setAttribute('aria-pressed', on); DL.store('max', on ? '1' : '0'); }
    max.addEventListener('click', function () { setMax(!dlg.classList.contains('max')); });
    setMax(DL.store('max') === '1');
    dlg.addEventListener('click', function (ev) { if (ev.target === dlg) close(); });
    dlg.addEventListener('keydown', function (ev) {
      if (ev.target.closest && ev.target.closest('input,textarea')) return;
      if ((ev.key === 'ArrowLeft' && ev.altKey) || ev.key === '[') { ev.preventDefault(); step(-1); }
      else if ((ev.key === 'ArrowRight' && ev.altKey) || ev.key === ']') { ev.preventDefault(); step(1); }
      else if (ev.key === 'f' && !ev.ctrlKey && !ev.metaKey) { ev.preventDefault(); setMax(!dlg.classList.contains('max')); }
    });
    /* `close` fires after close(): give the focus back to what opened the viewer */
    dlg.addEventListener('close', function () {
      if (dlg.open) return;
      var was = current, back = opener;
      current = null;
      opener = null;
      if (back && back.isConnected && back.focus) back.focus();
      DL.bus.emit('viewer-closed', was);
    });
    return true;
  }

  function flash(msg) {
    var s = parts['v-status'];
    s.textContent = msg;
    s.classList.add('on');
    setTimeout(function () { s.classList.remove('on'); }, 1400);
  }
  function copy(text) {
    function fallback() {
      var t = DL.el('textarea');
      t.value = text;
      t.style.position = 'fixed';
      t.style.opacity = '0';
      dlg.appendChild(t);
      t.select();
      try { document.execCommand('copy'); flash('Copied'); } catch (e) { flash('Copy failed'); }
      t.remove();
    }
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(function () { flash('Copied'); }, fallback);
    else fallback();
  }
  function download(c) {
    var a = DL.el('a');
    a.download = c.name || 'file.txt';
    if (c.text != null) {
      a.href = URL.createObjectURL(new Blob([c.text], { type: 'text/plain' }));
      setTimeout(function () { URL.revokeObjectURL(a.href); }, 5000);
    } else a.href = c.src;
    dlg.appendChild(a);
    a.click();
    a.remove();
  }
  function setPath(p) {
    var el = parts['v-path'], segs = String(p).split('/'), name = segs.pop();
    el.textContent = '';
    el.appendChild(document.createTextNode('‎' + (segs.length ? segs.join('/') + '/' : '')));
    el.appendChild(DL.el('b', null, name));
    el.title = p;
  }
  function setMeta(items) {
    var el = parts['v-meta'];
    el.textContent = '';
    items.filter(Boolean).forEach(function (x) { el.appendChild(DL.el('span', null, x)); });
  }
  function index() {
    for (var i = 0; i < list.length; i++) if (list[i].id === current.id) return i;
    return -1;
  }
  function position() {
    var nav = parts['v-nav'], k = index();
    DL.$('[data-step="-1"]', nav).disabled = k <= 0;
    DL.$('[data-step="1"]', nav).disabled = k < 0 || k >= list.length - 1;
    DL.$('.pos', nav).textContent = list.length > 1 && k >= 0 ? (k + 1) + ' / ' + list.length : '';
  }
  function frame(ref, tools) {
    setPath(ref.path || ref.id || '');
    setMeta([ref.kind === 'code' ? ref.lang : ref.kind, ref.size != null ? DL.fmt.bytes(ref.size) : '', ref.meta || '']);
    parts['v-tools'].textContent = '';
    parts.tabs.textContent = '';
    parts.tabs.hidden = true;
    position();
    (tools || []).forEach(function (t) { parts['v-tools'].appendChild(t); });
  }
  function show(node) { var b = parts['v-body']; b.textContent = ''; b.appendChild(node); }
  function loading() { show(pane(DL.el('p', 'muted loading', 'Loading…'))); }
  function failed(text) { show(pane(DL.el('p', 't-err', text))); }
  function step(d) { if (!current) return; var k = index(); if (k >= 0 && list[k + d]) load(list[k + d], {}); }

  function toggles() {
    var p = prefs();
    var w = DL.btn('Wrap', { icon: 'wrap', on: function () {
      p.wrap = !p.wrap;
      DL.store('wrap', p.wrap ? '1' : '0');
      w.setAttribute('aria-pressed', p.wrap);
      DL.$$('.code', parts['v-body']).forEach(function (c) { c.classList.toggle('wrap', p.wrap); });
    } });
    w.setAttribute('aria-pressed', p.wrap);
    var n = DL.btn('Line numbers', { icon: 'hash', on: function () {
      p.ln = !p.ln;
      DL.store('ln', p.ln ? '1' : '0');
      n.setAttribute('aria-pressed', p.ln);
      DL.$$('.v-body>.code', dlg).forEach(function (c) { c.classList.toggle('no-ln', !p.ln); });
    } });
    n.setAttribute('aria-pressed', p.ln);
    return [w, n];
  }
  function modeSwitch(modes, active, on) {
    var s = DL.el('div', 'seg');
    s.setAttribute('role', 'group');
    s.setAttribute('aria-label', 'View');
    modes.forEach(function (m) {
      var b = DL.el('button', null, m);
      b.type = 'button';
      b.setAttribute('aria-pressed', m === active);
      b.addEventListener('click', function () {
        DL.$$('button', s).forEach(function (x) { x.setAttribute('aria-pressed', x === b); });
        on(m);
      });
      s.appendChild(b);
    });
    return s;
  }

  /* After drawing: bring a line, or the first match of a search, into view and mark it. */
  function reveal(line, q) {
    var body = parts['v-body'], t = null;
    if (line) { var ls = DL.$$('.v-body>.code .l, .v-body .code .l', dlg); t = ls[line - 1] || null; }
    if (!t && q) {
      q = String(q).toLowerCase();
      var has = function (n) { return n.textContent.toLowerCase().indexOf(q) >= 0; };
      t = DL.$$('p, li, td, .l, h1, h2, h3, h4', body).filter(has)[0] || null;
    }
    if (!t) return;
    var d = t.closest('details');
    while (d) { d.open = true; d = d.parentElement && d.parentElement.closest('details'); }
    t.classList.add('hit');
    t.scrollIntoView({ block: 'center' });
  }

  /* Draw `ref` with its loaded `data` ({text} | {url} | {not_embedded, size}). */
  function draw(ref, data, after, line) {
    var c = { kind: ref.kind || 'text', lang: ref.lang, path: ref.path || ref.id, name: nameOf(ref),
              text: data.text != null ? data.text : null, src: data.url || null };
    if (data.not_embedded) {
      frame(ref, []);
      var p = pane(DL.el('p', null, 'Too large to embed (' + DL.fmt.bytes(data.size != null ? data.size : ref.size) +
                                    '). Open it on disk: '));
      p.firstChild.appendChild(DL.el('code', null, c.path));
      show(p);
      if (after) after();
      return;
    }
    if (c.kind === 'json' && c.text != null && DL.hl && DL.hl.pretty) c.text = DL.hl.pretty(c.text);
    var v = VIEWERS[c.kind] || VIEWERS.text, mode = v.modes ? (DL.store('mode-' + c.kind) || v.modes[0]) : null;
    if (v.modes && v.modes.indexOf(mode) < 0) mode = v.modes[0];
    if (line && v.lines) mode = v.lines; /* opened at a line: show the lines (not kept as the choice) */
    var codeTools = [], tools = [];
    function render(m) {
      show(v.render(c, m) || code(c.text || '', 'text'));
      var plain = !!DL.$('.v-body>.code', dlg);
      codeTools.forEach(function (t) { t.hidden = !plain; });
    }
    if (v.modes) tools.push(modeSwitch(v.modes, mode, function (m) { DL.store('mode-' + c.kind, m); mode = m; render(m); }));
    tools.push(DL.el('span', 'spacer'));
    if (!v.noText) { codeTools = toggles(); tools = tools.concat(codeTools); }
    if (c.text != null) tools.push(DL.btn('Copy', { icon: 'copy', on: function () { copy(c.text); } }));
    if (c.text != null || c.src) tools.push(DL.btn('Download', { icon: 'download', on: function () { download(c); } }));
    frame(ref, tools);
    render(mode);
    if (after) after();
  }

  /* Load and show `ref`; `after` runs once it is drawn. */
  function load(ref, opts, after) {
    current = ref;
    opts = opts || {};
    var my = ++seq, body = parts['v-body'];
    function done() {
      body.scrollTop = 0;
      if (opts.line || opts.query) setTimeout(function () { reveal(opts.line, opts.query); }, 0);
      if (after) after();
    }
    if (ref.missing) { frame(ref, []); show(pane(DL.el('p', 't-err', 'Missing: ' + (ref.path || ref.id)))); return; }
    if (ref.inline) { draw(ref, ref.inline, done, opts.line); return; } /* data in hand: an image from a conversation */
    if (ref.panel) { /* a built node (DL.viewer.panel) */
      frame(ref, ref.tools ? ref.tools() : []);
      show(ref.panel());
      done();
      return;
    }
    var hit = cached(ref.id);
    if (hit && hit.v === (ref.version || '')) { draw(ref, hit.data, done, opts.line); return; }
    if (ref.size > BIG && !bigOk[ref.id] && ref.kind !== 'image' && ref.kind !== 'binary') {
      /* a very large file: loading it all can stall the page, so ask first */
      frame(ref, []);
      var p = pane(DL.el('p', null, 'This file is ' + DL.fmt.bytes(ref.size) + '. Showing it all may slow this page down.'));
      p.appendChild(DL.btn('Show it', { on: function () { bigOk[ref.id] = 1; load(ref, opts, after); } }));
      p.appendChild(DL.btn('Download', { on: function () {
        DL.api.file(ref).then(function (data) { download({ name: nameOf(ref), text: data.text != null ? data.text : null, src: data.url }); });
      } }));
      show(p);
      return;
    }
    frame(ref, []);
    loading();
    DL.api.file(ref).then(function (data) {
      remember(ref.id, { v: ref.version || '', data: data });
      if (my === seq && current && current.id === ref.id) draw(ref, data, done, opts.line);
    }, function (err) {
      if (my === seq && current && current.id === ref.id) failed('Could not load ' + (ref.path || ref.id) + ': ' + (err && err.message || err));
    });
  }

  /* --- the API --------------------------------------------------------------------------------- */
  function open(ref, opts) {
    if (!ref || !init()) return;
    options = opts || {};
    list = options.list && options.list.length ? options.list : [ref];
    if (!dlg.open) {
      opener = options.opener || document.activeElement;
      dlg.showModal();
    }
    load(ref, options);
    parts['v-body'].focus();
    if (DL.api && DL.api.get) {
      DL.api.get('files').then(function (j) { files = flatten(j && j.trees, []); }, function () {});
    }
  }
  function close() { if (dlg && dlg.open) dlg.close(); }

  /* A longer list for what is shown (the trial view's changes once all its calls are read):
     taken only while the item shown is in it. */
  function relist(items) {
    if (!dlg || !dlg.open || !current) return;
    if (!(items || []).some(function (x) { return x.id === current.id; })) return;
    list = options.list = items;
    position();
  }

  /* A built node in the viewer's frame, with its keys and previous/next (FR-018d): `title` is
     shown as the path, `node` as the body. `opts.list` steps through items like
     `{id, path, meta, panel: () => node, tools: () => [elements]}`, `opts.item` is the one shown
     (default: the node itself as one item); `opts.opener` gets the focus back. */
  function panel(title, node, opts) {
    opts = opts || {};
    var item = opts.item || { id: 'panel:' + title, path: title, meta: opts.meta, panel: function () { return node; } };
    open(item, opts);
  }

  /* A link to a file that opens it in the viewer (with `list` to step through), or a "missing"
     label for a file that cannot be read. Its address is the file's route, so it opens in a new
     tab too. */
  function link(ref, text, list) {
    if (!ref || ref.missing || !ref.id) {
      var m = DL.el('span', 'missing', text || (ref && ref.path) || 'missing');
      m.title = 'Missing: ' + ((ref && ref.path) || '');
      return m;
    }
    var a = DL.link(DL.router.href('file', { id: ref.id }), text || nameOf(ref));
    a.title = ref.path || '';
    a.addEventListener('click', function (ev) {
      if (ev.button || ev.metaKey || ev.ctrlKey || ev.shiftKey) return;
      ev.preventDefault();
      open(ref, { list: list, opener: a });
    });
    return a;
  }

  /* The workspace changed: reload the open file if its version did. */
  DL.bus.on('changed', function () {
    if (!dlg || !dlg.open || !current || !DL.api) return;
    var id = current.id;
    DL.api.get('files').then(function (j) {
      files = flatten(j && j.trees, []);
      var now = files.filter(function (f) { return f.id === id; })[0];
      if (!now || !current || current.id !== id || now.version === current.version) return;
      list = list.map(function (f) { return f.id === id ? now : f; });
      var body = parts['v-body'], top = body.scrollTop;
      var end = top + body.clientHeight >= body.scrollHeight - 24;
      cache.delete(id);
      load(now, {}, function () { body.scrollTop = end ? body.scrollHeight : top; });
    }, function () {});
  });

  DL.viewer = {
    open: open,
    panel: panel,
    relist: relist,
    close: close,
    link: link,
    isOpen: function () { return !!(dlg && dlg.open); },
    current: function () { return current; },
    VIEWERS: VIEWERS
  };
})(window.DL = window.DL || {});
