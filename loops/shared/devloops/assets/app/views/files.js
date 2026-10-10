/* views/files.js: `#/files` — the workspace's files as a tree (each loop, then run/ and the
   workspace's own files), filtered by path and by kind, walked with the arrow keys; a file opens
   in the viewer. `#/file/<id>` is the same explorer with that file open (`?line=<n>` at that
   line); `?q=<text>` starts filtered. */
(function (DL) {
  'use strict';

  var KINDS = [['markdown', 'Markdown'], ['json', 'JSON'], ['code', 'Code'], ['log', 'Logs'], ['text', 'Text'], ['image', 'Images']];

  function dirNode(node, files) {
    var li = DL.el('li', 'd'), det = DL.el('details', 'dir'), sum = DL.el('summary'), span = DL.el('span', 'node');
    var ul = DL.el('ul'), count = 0;
    det.open = !!node.open;
    (node.children || []).forEach(function (child) {
      var made = child.file ? fileNode(child.file, files) : dirNode(child, files);
      count += made.count;
      ul.appendChild(made.li);
    });
    var meta = DL.el('span', 'meta');
    if (node.badge && node.badge.status) meta.appendChild(DL.pill(node.badge.status, node.badge.table));
    meta.appendChild(DL.el('span', null, String(count)));
    DL.add(span, DL.icon('chev', 'chev'), DL.icon('folder', 'k'), DL.el('span', 'nm', node.name), meta);
    DL.add(li, DL.add(det, DL.add(sum, span), ul));
    return { li: li, count: count };
  }

  function fileNode(ref, files) {
    var li = DL.el('li', 'f'), name = ref.path.split('/').pop();
    if (ref.missing) {
      var miss = DL.add(DL.el('span', 'node file missing'), DL.icon('file', 'k'), DL.el('span', 'nm', name),
        DL.el('span', 'meta', 'missing'));
      miss.dataset.path = ref.path;
      miss.dataset.kind = 'missing';
      return { li: DL.add(li, miss), count: 1 };
    }
    files.push(ref);
    var a = DL.link(DL.router.href('file', { id: ref.id }), null, 'node file');
    a.dataset.path = ref.path;
    a.dataset.kind = ref.kind === 'jsonl' ? 'json' : ref.kind;
    a.dataset.id = ref.id;
    a.title = ref.path + (ref.meta ? ' · ' + ref.meta : '');
    DL.add(a, DL.icon(ref.icon || 'file', 'k ' + ref.kind), DL.el('span', 'nm', name), DL.el('span', 'meta', DL.fmt.bytes(ref.size)));
    return { li: DL.add(li, a), count: 1 };
  }

  function explorer(d, el, query, openId, refresh) {
    var files = [], byId = {}, tree = DL.el('div', 'explorer'), ul = DL.el('ul');
    d.trees.forEach(function (t) { ul.appendChild(dirNode(t, files).li); });
    files.forEach(function (f) { byId[f.id] = f; });
    tree.appendChild(ul);

    var bar = DL.el('div', 'toolbar'), input = DL.el('input', 'input'), chips = DL.el('div', 'chips'), kinds = [];
    var shown = DL.el('span', 'small muted');
    input.type = 'search';
    input.placeholder = 'Filter by path…';
    input.setAttribute('aria-label', 'Filter files by path');
    if (query && query.q && !refresh) input.value = query.q;
    chips.setAttribute('role', 'group');
    chips.setAttribute('aria-label', 'File types');

    function visibleFiles() {
      return DL.$$('a.file', tree).filter(function (a) { return !a.closest('.hidden-by-filter'); })
        .map(function (a) { return byId[a.dataset.id]; });
    }
    function apply() {
      var q = input.value.toLowerCase().trim();
      DL.$$('li.f', tree).forEach(function (li) {
        var f = li.firstChild, ok = (!q || (f.dataset.path || '').toLowerCase().indexOf(q) >= 0) &&
          (!kinds.length || kinds.indexOf(f.dataset.kind) >= 0);
        li.classList.toggle('hidden-by-filter', !ok);
      });
      DL.$$('li.d', tree).reverse().forEach(function (li) {
        var any = DL.$('li.f:not(.hidden-by-filter)', li);
        li.classList.toggle('hidden-by-filter', !any);
        if ((q || kinds.length) && any) DL.$('details', li).open = true;
      });
      var n = DL.$$('li.f:not(.hidden-by-filter)', tree).length;
      shown.textContent = DL.fmt.plural(n, 'file');
    }
    input.addEventListener('input', apply);
    KINDS.forEach(function (k) {
      var b = DL.el('button', 'chip', k[1]);
      b.type = 'button';
      b.dataset.chip = k[0];
      b.setAttribute('aria-pressed', 'false');
      b.addEventListener('click', function () {
        var at = kinds.indexOf(k[0]);
        if (at < 0) kinds.push(k[0]); else kinds.splice(at, 1);
        b.setAttribute('aria-pressed', String(at < 0));
        apply();
      });
      chips.appendChild(b);
    });
    function all(open) { return function () { DL.$$('details.dir', tree).forEach(function (x) { x.open = open; }); }; }
    DL.add(bar, input, chips, DL.el('span', 'spacer'), shown,
      DL.btn('Expand all', { cls: 'ghost', on: all(true) }), DL.btn('Collapse all', { cls: 'ghost', on: all(false) }));

    tree.addEventListener('click', function (ev) {
      var a = ev.target.closest('a.file');
      if (!a || ev.button || ev.metaKey || ev.ctrlKey || ev.shiftKey) return;
      ev.preventDefault();
      var ref = byId[a.dataset.id];
      DL.viewer.open(ref, { list: visibleFiles(), opener: a });
    });
    /* arrow keys: up and down through what is shown, right opens a folder, left closes it or
       goes to its parent */
    tree.addEventListener('keydown', function (ev) {
      var at = ev.target.closest('summary, a.file');
      if (!at) return;
      var items = DL.$$('summary, a.file', tree).filter(function (x) { return x.offsetParent !== null; });
      var k = items.indexOf(at), det = at.tagName === 'SUMMARY' ? at.parentNode : null;
      if (ev.key === 'ArrowDown' && items[k + 1]) { ev.preventDefault(); items[k + 1].focus(); }
      else if (ev.key === 'ArrowUp' && items[k - 1]) { ev.preventDefault(); items[k - 1].focus(); }
      else if (ev.key === 'ArrowRight' && det) {
        ev.preventDefault();
        if (!det.open) det.open = true; else if (items[k + 1]) items[k + 1].focus();
      } else if (ev.key === 'ArrowLeft') {
        ev.preventDefault();
        if (det && det.open) det.open = false;
        else {
          var up = (det || at).parentNode.closest('details.dir');
          if (up) DL.$(':scope>summary', up).focus();
        }
      }
    });

    DL.add(el, DL.head('Files', null, DL.fmt.plural(d.count, 'file') + ' in this workspace'), bar, tree);
    if (!d.count) el.appendChild(DL.el('p', 'muted', 'No files yet.'));
    apply();

    /* the address's file opens once; on a refresh the viewer keeps whatever file the reader
       stepped to (it reloads it itself when it changed) */
    if (openId) {
      var ref = byId[openId];
      if (!ref) {
        el.insertBefore(DL.el('p', 'callout warn', 'This file is not in the workspace any more.'), bar);
      } else if (!refresh) {
        var line = query && +query.line > 0 ? +query.line : null; /* a search result: at its line */
        setTimeout(function () { DL.viewer.open(ref, { list: files, line: line }); }, 0);
      }
    }
  }

  var def = {
    title: function () { return 'Files'; },
    data: function () { return ['files']; },
    render: function (data, params, el, query, refresh) { explorer(data[0], el, query, params.id, refresh); }
  };
  DL.router.register('files', def);
  DL.router.register('file', def);

  /* Closing the viewer opened by `#/file/<id>` goes back to the explorer's own address. */
  DL.bus.on('viewer-closed', function () {
    var r = DL.router.current;
    if (r && r.view === 'file') DL.router.go('files');
  });
})(window.DL = window.DL || {});
