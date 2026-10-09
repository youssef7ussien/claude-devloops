/* router.js: one address per view and item (research R-4), and each view's life.

   A view is registered once: `DL.router.register(name, {title(params, data), data(params, query)
   -> [api paths], render(data, params, el, query, refresh)})`; `refresh` is true when the same
   address is drawn again after a change, so what the address asks for (a filter, a file to open)
   is applied the first time only and the reader's own changes stay. Mounting a route asks for the view's paths only,
   renders into a new element, and swaps it in once its data arrived, so the old view stays until
   then. When the workspace changes (DL.bus 'changed'), only the mounted view is loaded again,
   keeping the reader's place: open sections, typed filters, pressed chips, scroll, and focus. */
(function (DL) {
  'use strict';

  /* name, pattern, parameter names: the route table (a new view is one line) */
  var ROUTES = [
    ['overview', /^$/, []],
    ['run', /^run$/, []],
    ['loop', /^loop\/([^/]+)$/, ['loop']],
    ['plan', /^loop\/([^/]+)\/plan$/, ['loop']],
    ['trial', /^loop\/([^/]+)\/m\/([^/]+)\/t\/([^/]+)$/, ['loop', 'milestone', 'key']],
    ['calls', /^calls$/, []],
    ['call', /^call\/([^/]+)\/([^/]+)$/, ['loop', 'seq']],
    ['files', /^files$/, []],
    ['file', /^file\/([^/]+)$/, ['id']],
    ['questions', /^questions$/, []],
    ['events', /^events$/, []]
  ];
  var BY_NAME = {};
  ROUTES.forEach(function (r) { BY_NAME[r[0]] = r; });

  function decode(s) { try { return decodeURIComponent(s); } catch (e) { return s; } }

  function parseQuery(q) {
    var out = {};
    (q || '').split('&').forEach(function (pair) {
      if (!pair) return;
      var at = pair.indexOf('=');
      var k = decode((at < 0 ? pair : pair.slice(0, at)).replace(/\+/g, ' '));
      out[k] = at < 0 ? '' : decode(pair.slice(at + 1).replace(/\+/g, ' '));
    });
    return out;
  }

  /* `#/loop/backend-dev?x=1` -> {view: 'loop', params: {loop: 'backend-dev'}, query: {x: '1'}};
     an unknown address is the overview (`unknown: true`). */
  function parse(hash) {
    var h = String(hash || '').replace(/^#/, '').replace(/^\//, '');
    var at = h.indexOf('?'), path = at < 0 ? h : h.slice(0, at), query = parseQuery(at < 0 ? '' : h.slice(at + 1));
    path = path.replace(/\/+$/, '');
    for (var i = 0; i < ROUTES.length; i++) {
      var m = ROUTES[i][1].exec(path);
      if (!m) continue;
      var params = {};
      ROUTES[i][2].forEach(function (name, k) { params[name] = decode(m[k + 1]); });
      return { view: ROUTES[i][0], params: params, query: query };
    }
    return { view: 'overview', params: {}, query: query, unknown: true };
  }

  /* The address of a view: href('trial', {loop, milestone, key}) -> '#/loop/…/m/…/t/…'. */
  function href(view, params, query) {
    var r = BY_NAME[view];
    if (!r) return '#/';
    var i = 0, src = r[1].source.replace(/^\^|\$$/g, '').replace(/\\\//g, '/');
    var path = src.replace(/\(\[\^\/\]\+\)/g, function () {
      return encodeURIComponent(String((params || {})[r[2][i++]]));
    });
    var q = Object.keys(query || {}).filter(function (k) { return query[k] != null && query[k] !== ''; })
      .map(function (k) { return encodeURIComponent(k) + '=' + encodeURIComponent(query[k]); }).join('&');
    return '#/' + path + (q ? '?' + q : '');
  }

  /* --- views -------------------------------------------------------------------------------- */
  var views = {};
  var R = {
    ROUTES: ROUTES, parse: parse, href: href,
    current: null,  /* the mounted route */
    host: null,
    seq: 0
  };

  R.register = function (name, def) { views[name] = def; };
  R.registered = function (name) { return !!views[name]; };

  /* The data of `route`'s view: `{route, def, data: [answers in the order of def.data()]}`.
     Served, the answers must come from one workspace version: when they differ, the cache is
     dropped and the paths asked once more (spec Edge Cases). */
  R.load = function (route) {
    var def = views[route.view];
    if (!def) return Promise.resolve({ route: route, def: null, data: [] });
    var paths = def.data ? def.data(route.params, route.query) : [];
    function all() { return Promise.all(paths.map(function (p) { return DL.api.get(p); })); }
    return all().then(function (data) {
      if (DL.api.source() !== 'api') return data;
      var seen = {};
      paths.forEach(function (p) { var v = DL.api.versionOf(p); if (v) seen[v] = 1; });
      if (Object.keys(seen).length < 2) return data;
      DL.api.invalidate();
      return all();
    }).then(function (data) { return { route: route, def: def, data: data, paths: paths }; });
  };

  /* --- the reader's place in a view (from dashboard.js keep/restore) ----------------------- */
  function detailsKey(d) {
    if (d.id) return '#' + d.id;
    if (d.dataset && d.dataset.key) return 'k:' + d.dataset.key;
    var k = [], x = d;
    while (x) {
      var s = DL.$(':scope>summary', x), n = s && DL.$('.nm', s);
      k.unshift((n || s) ? (n || s).textContent.trim().slice(0, 80) : '?');
      x = x.parentElement && x.parentElement.closest('details');
    }
    return k.join('/');
  }
  function keep(v) {
    var st = { open: {}, inputs: [], chips: [], scroll: window.scrollY, focus: null };
    DL.$$('details', v).forEach(function (d) { st.open[detailsKey(d)] = d.open; });
    DL.$$('input[type="search"], input[data-keep]', v).forEach(function (i) { st.inputs.push(i.value); });
    DL.$$('[data-chip]', v).forEach(function (b) {
      if (b.getAttribute('aria-pressed') === 'true') st.chips.push(b.dataset.chip);
    });
    var ae = document.activeElement;
    if (ae && ae.matches && ae.matches('input') && v.contains(ae)) {
      st.focus = [DL.$$('input', v).indexOf(ae), ae.selectionStart, ae.selectionEnd];
    }
    return st;
  }
  function restore(v, st) {
    DL.$$('details', v).forEach(function (d) { var k = detailsKey(d); if (k in st.open) d.open = st.open[k]; });
    DL.$$('input[type="search"], input[data-keep]', v).forEach(function (i, k) {
      if (st.inputs[k]) { i.value = st.inputs[k]; i.dispatchEvent(new Event('input')); }
    });
    DL.$$('[data-chip]', v).forEach(function (b) {
      if (st.chips.indexOf(b.dataset.chip) >= 0 && b.getAttribute('aria-pressed') !== 'true') b.click();
    });
    if (st.focus) {
      var fi = DL.$$('input', v)[st.focus[0]];
      if (fi) { fi.focus(); try { fi.setSelectionRange(st.focus[1], st.focus[2]); } catch (e) { /* not a text input */ } }
    }
    window.scrollTo(0, st.scroll);
  }

  /* --- showing a view ----------------------------------------------------------------------- */
  function message(cls, text, retry) {
    var box = DL.el('div', 'view ' + cls);
    DL.add(box, DL.el('p', null, text));
    if (retry) box.appendChild(DL.btn('Try again', { on: retry }));
    return box;
  }

  function swap(node, refresh) {
    var old = R.host.firstElementChild;
    var st = refresh && old ? keep(old) : null;
    if (old) R.host.replaceChild(node, old); else R.host.appendChild(node);
    if (st) restore(node, st); else window.scrollTo(0, 0);
    DL.tips(node);
  }

  /* Renders a loaded view (tests replace it to watch what a refresh asks for). */
  R._show = function (loaded, refresh) {
    var route = loaded.route, def = loaded.def;
    if (!def) {
      swap(message('empty', 'This view is not available in this version of the dashboard.'), refresh);
      DL.bus.emit('route', { route: route, title: 'Not available' });
      return;
    }
    var el = DL.el('section', 'view view-' + route.view);
    def.render(loaded.data, route.params, el, route.query, !!refresh);
    swap(el, refresh);
    var title = def.title ? def.title(route.params, loaded.data) : route.view;
    DL.bus.emit('route', { route: route, title: title });
  };

  function fail(route, refresh, err) {
    if (refresh) return; /* keep what is shown; the top bar says Offline */
    if (err && err.status === 404) {
      swap(message('empty', 'Not found: ' + (err.message || 'this item is not in the workspace') + '.'), false);
    } else {
      swap(message('error', 'Could not load this view: ' + (err && err.message || err) + '.',
        function () { R.mount(route); }), false);
    }
    DL.bus.emit('route', { route: route, title: 'Error' });
  }

  /* Mount `route` (default: the address's). `refresh`: the same route again after a change. */
  R.mount = function (route, refresh) {
    route = route || parse(location.hash);
    var my = ++R.seq;
    R.current = route;
    if (!refresh && R.host && !R.host.firstElementChild) R.host.appendChild(message('loading', 'Loading…'));
    return R.load(route).then(function (loaded) {
      if (my === R.seq) R._show(loaded, refresh);
    }, function (err) {
      if (my === R.seq) fail(route, refresh, err);
    });
  };

  /* After the workspace changed: the mounted view only, in place. */
  R.refresh = function () {
    if (R.current) return R.mount(R.current, true);
    return Promise.resolve();
  };

  R.go = function (view, params, query) { location.hash = href(view, params, query); };

  R.start = function (host) {
    R.host = host;
    window.addEventListener('hashchange', function () { R.mount(); });
    DL.bus.on('changed', R.refresh);
    return R.mount();
  };

  DL.router = R;
})(window.DL = window.DL || {});
