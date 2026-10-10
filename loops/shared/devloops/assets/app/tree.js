/* tree.js: the Files view's tree, shared with the trial view's folder section (FR-018b).
   `DL.tree.build(refs, root)` (pure) groups FileRefs into folders below `root`;
   `DL.tree.draw(nodes, opts)` draws the server's trees (`api/files`) or a built one: folders that
   fold, with their counts and badges; files with their icon, kind, and size, opening in the
   viewer with `opts.list()` (default: every file drawn) for previous and next. Each file link
   carries its place in the tree (`data-tree`: the folder names above it, from the top), which
   the Files view's folder filter matches (FR-020f). */
(function (DL) {
  'use strict';

  /* `{name, children: [folder | {name, file}], count, size}`: each ref's path below `root`
     ("a/b" or "a/b/"; refs outside it keep their whole path) split into folders, folders first,
     then files, each by name. */
  function build(refs, root) {
    var base = String(root || '').replace(/\/+$/, ''), top = folder(base.split('/').pop() || '');
    (refs || []).forEach(function (ref) {
      var rel = base && ref.path.indexOf(base + '/') === 0 ? ref.path.slice(base.length + 1) : ref.path;
      var parts = rel.split('/'), at = top;
      parts.slice(0, -1).forEach(function (p) {
        if (!at.dirs[p]) at.dirs[p] = folder(p);
        at = at.dirs[p];
      });
      at.files.push({ name: parts[parts.length - 1], file: ref });
    });
    return finish(top);
  }
  /* `dirs` has no prototype, so a folder named "constructor" or "__proto__" is a folder. */
  function folder(name) { return { name: name, dirs: Object.create(null), files: [] }; }
  function byName(a, b) { return a.name < b.name ? -1 : a.name > b.name ? 1 : 0; }
  function finish(f) {
    var dirs = Object.keys(f.dirs).map(function (k) { return finish(f.dirs[k]); }).sort(byName);
    var files = f.files.slice().sort(byName), count = files.length, size = 0;
    files.forEach(function (x) { size += x.file.size || 0; });
    dirs.forEach(function (d) { count += d.count; size += d.size; });
    return { name: f.name, children: dirs.concat(files), count: count, size: size };
  }

  function dirNode(node, at, files) {
    var li = DL.el('li', 'd'), det = DL.el('details', 'dir'), sum = DL.el('summary'), span = DL.el('span', 'node');
    var ul = DL.el('ul'), count = 0, here = at ? at + '/' + node.name : node.name;
    det.open = !!node.open;
    (node.children || []).forEach(function (child) {
      var made = child.file ? fileNode(child.file, here, files) : dirNode(child, here, files);
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

  function fileNode(ref, at, files) {
    var li = DL.el('li', 'f'), name = ref.path.split('/').pop();
    if (ref.missing) {
      var miss = DL.add(DL.el('span', 'node file missing'), DL.icon('file', 'k'), DL.el('span', 'nm', name),
        DL.el('span', 'meta', 'missing'));
      miss.dataset.path = ref.path;
      miss.dataset.tree = at;
      miss.dataset.kind = 'missing';
      return { li: DL.add(li, miss), count: 1 };
    }
    files.push(ref);
    var a = DL.link(DL.router.href('file', { id: ref.id }), null, 'node file');
    a.dataset.path = ref.path;
    a.dataset.tree = at;
    a.dataset.kind = ref.kind === 'jsonl' ? 'json' : ref.kind;
    a.dataset.id = ref.id;
    a.title = ref.path + (ref.meta ? ' · ' + ref.meta : '');
    DL.add(a, DL.icon(ref.icon || 'file', 'k ' + ref.kind), DL.el('span', 'nm', name), DL.el('span', 'meta', DL.fmt.bytes(ref.size)));
    return { li: DL.add(li, a), count: 1 };
  }

  /* `{el, files, byId}`: `nodes` (a list of top folders, or one folder whose children are drawn
     at the top) as a `div.explorer`; a click on a file opens it in the viewer. */
  function draw(nodes, opts) {
    opts = opts || {};
    var files = [], byId = {}, el = DL.el('div', 'explorer'), ul = DL.el('ul');
    var top = Array.isArray(nodes) ? nodes : null;
    if (top) top.forEach(function (t) { ul.appendChild(dirNode(t, '', files).li); });
    else (nodes.children || []).forEach(function (child) {
      ul.appendChild((child.file ? fileNode(child.file, nodes.name, files) : dirNode(child, nodes.name, files)).li);
    });
    files.forEach(function (f) { byId[f.id] = f; });
    el.appendChild(ul);
    el.addEventListener('click', function (ev) {
      var a = ev.target.closest('a.file');
      if (!a || ev.button || ev.metaKey || ev.ctrlKey || ev.shiftKey) return;
      ev.preventDefault();
      DL.viewer.open(byId[a.dataset.id], { list: opts.list ? opts.list() : files, opener: a });
    });
    return { el: el, files: files, byId: byId };
  }

  DL.tree = { build: build, draw: draw };
})(window.DL = window.DL || {});
