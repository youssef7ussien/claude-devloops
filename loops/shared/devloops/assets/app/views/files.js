/* views/files.js: `#/files` — the workspace's files as a tree (each loop, then run/ and the
   workspace's own files), filtered by path and by kind, walked with the arrow keys; a file opens
   in the viewer. `#/file/<id>` is the same explorer with that file open (`?line=<n>` at that
   line); `?q=<text>` starts filtered; `?dir=<path>` shows one folder only (FR-020f), with a chip
   that drops it. The tree itself is drawn by tree.js (shared with the trial view). */
(function (DL) {
  'use strict';

  var KINDS = [['markdown', 'Markdown'], ['json', 'JSON'], ['code', 'Code'], ['log', 'Logs'], ['text', 'Text'], ['image', 'Images']];

  /* FR-020f: whether a file is inside folder `dir`, by its workspace path or by its place in the
     tree (the folder names above it, from the top folder), whole names only: a loop's inputs
     that live outside its folder stay in it, and so do the workspace's own files. */
  function inDir(path, treePath, dir) {
    dir = String(dir || '').replace(/\/+$/, '');
    if (!dir) return true;
    return [path, treePath].some(function (p) {
      p = String(p || '');
      return p === dir || p.indexOf(dir + '/') === 0;
    });
  }

  function explorer(d, el, query, openId, refresh) {
    var drawn = DL.tree.draw(d.trees, { list: visibleFiles }), tree = drawn.el, files = drawn.files, byId = drawn.byId;
    var dir = String((query && query.dir) || '').replace(/\/+$/, '');

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
          (!kinds.length || kinds.indexOf(f.dataset.kind) >= 0) && inDir(f.dataset.path, f.dataset.tree, dir);
        li.classList.toggle('hidden-by-filter', !ok);
      });
      var n = DL.$$('li.f:not(.hidden-by-filter)', tree).length;
      DL.$$('li.d', tree).reverse().forEach(function (li) {
        var m = DL.$$('li.f:not(.hidden-by-filter)', li).length;
        li.classList.toggle('hidden-by-filter', !m);
        /* the text and kind filters open every folder with a match; the folder filter opens the
           folders down to the one holding every shown file */
        if (m && ((q || kinds.length) || (dir && m === n))) DL.$('details', li).open = true;
      });
      shown.textContent = DL.fmt.plural(n, 'file');
      if (none) none.hidden = !!n || !dir;
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
    var folder = null, none = null;
    if (dir) {
      folder = DL.el('span', 'chip folder-chip');
      folder.setAttribute('aria-pressed', 'true');
      var x = DL.el('button', 'x', '×');
      x.type = 'button';
      x.setAttribute('aria-label', 'Show every folder');
      x.title = 'Show every folder';
      x.addEventListener('click', function () { DL.router.go('files'); });
      DL.add(folder, DL.icon('folder'), 'Folder: ', DL.el('code', null, dir), x);
      none = DL.el('p', 'muted', 'No files in ' + dir + '.');
    }
    DL.add(bar, folder, input, chips, DL.el('span', 'spacer'), shown,
      DL.btn('Expand all', { cls: 'ghost', on: all(true) }), DL.btn('Collapse all', { cls: 'ghost', on: all(false) }));

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

    DL.add(el, DL.head('Files', null, DL.fmt.plural(d.count, 'file') + ' in this workspace'), bar, none, tree);
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

  DL.filesView = { inDir: inDir };

  /* Closing the viewer opened by `#/file/<id>` goes back to the explorer's own address. */
  DL.bus.on('viewer-closed', function () {
    var r = DL.router.current;
    if (r && r.view === 'file') DL.router.go('files');
  });
})(window.DL = window.DL || {});
