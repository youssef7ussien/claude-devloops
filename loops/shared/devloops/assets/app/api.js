/* api.js: where the views' data comes from (contracts/api.md, research R-2, R-3, R-5).

   Served (`data-source="api"`): `get('summary')` fetches `api/summary` next to the page, once per
   workspace version; `follow()` asks for `version` every `data-poll` seconds while the page is
   visible and not paused, and on a change drops the cached answers and emits DL.bus 'changed'.
   Exported (`data-source="embedded"`): the same paths are read from the page's
   `<script type="application/json" id="d:<path>">` elements, each parsed the first time it is
   asked for; nothing polls. */
(function (DL) {
  'use strict';

  var cache = {};     /* path -> promise of the parsed answer */
  var versions = {};  /* path -> the X-Devloops-Version it was answered with */
  var state = { version: null, paused: false, offline: false, busy: false, timer: null };

  function root() { return document.documentElement; }
  function source() { return root().dataset.source === 'embedded' ? 'embedded' : 'api'; }

  function failure(status, message) {
    var err = new Error(message || ('HTTP ' + status));
    err.status = status;
    return err;
  }

  function fetchJson(path) {
    return fetch('api/' + path, { credentials: 'same-origin', cache: 'no-store' }).then(function (r) {
      versions[path] = r.headers.get('X-Devloops-Version');
      return r.text().then(function (text) {
        var body = null;
        try { body = text ? JSON.parse(text) : null; } catch (e) { body = null; }
        if (!r.ok) throw failure(r.status, (body && body.error) || r.statusText);
        if (body === null) throw failure(r.status, 'not JSON');
        return body;
      });
    });
  }

  /* The embedded answer for `path`, parsed now. */
  function embedded(path) {
    var node = document.getElementById('d:' + path);
    if (!node) return Promise.reject(failure(404, 'not in this snapshot: ' + path));
    try { return Promise.resolve(JSON.parse(node.textContent)); }
    catch (e) { return Promise.reject(failure(500, 'unreadable data: ' + path)); }
  }

  /* A promise of the JSON answer for `path` (e.g. 'summary', 'loops/backend-dev'). Answers are
     kept until the workspace changes, or asked for again with `fresh`; a failed request is not
     kept. */
  function get(path, fresh) {
    if (fresh && source() === 'api') delete cache[path];
    if (!cache[path]) {
      var p = source() === 'embedded' ? embedded(path) : fetchJson(path);
      cache[path] = p;
      p.catch(function () { if (cache[path] === p) delete cache[path]; });
    }
    return cache[path];
  }

  function invalidate() { cache = {}; versions = {}; }

  /* A file's content: `{text}` for text, `{url}` for an image or other binary file (a data: URI
     in a snapshot), or `{not_embedded: true, size}` for a file a snapshot leaves out. */
  function file(ref) {
    if (!ref || ref.missing) return Promise.reject(failure(404, 'missing: ' + (ref && ref.path)));
    var path = 'files/' + ref.id;
    if (source() === 'embedded') {
      return get(path).then(function (d) {
        if (d.not_embedded) return { not_embedded: true, size: d.size, path: d.path };
        if (d.base64 != null) return { url: 'data:' + (d.type || 'application/octet-stream') + ';base64,' + d.base64 };
        return { text: d.text };
      });
    }
    var url = 'api/' + path.split('/').map(encodeURIComponent).join('/');
    if (ref.kind === 'image' || ref.kind === 'binary') return Promise.resolve({ url: url });
    return fetch(url, { credentials: 'same-origin', cache: 'no-store' }).then(function (r) {
      if (!r.ok) throw failure(r.status, r.statusText);
      return r.text().then(function (text) { return { text: text }; });
    });
  }

  /* --- following the run (served only) ------------------------------------------------------ */
  function setOffline(off) {
    if (state.offline === off) return;
    state.offline = off;
    DL.bus.emit(off ? 'offline' : 'online');
  }

  function tick() {
    if (state.busy || state.paused || document.hidden) return Promise.resolve();
    state.busy = true;
    return fetch('version', { credentials: 'same-origin', cache: 'no-store' }).then(function (r) {
      if (!r.ok) throw failure(r.status, r.statusText);
      return r.json();
    }).then(function (j) {
      state.busy = false;
      setOffline(false);
      if (j.version !== state.version) {
        state.version = j.version;
        invalidate();
        DL.bus.emit('changed', j.version);
      }
    }, function () {
      state.busy = false;
      setOffline(true);
    });
  }

  function follow() {
    if (source() !== 'api' || state.timer) return;
    state.version = root().dataset.version || null;
    state.paused = DL.store('live-paused') === '1';
    var seconds = Math.max(1, +(root().dataset.poll || 3));
    state.timer = setInterval(tick, seconds * 1000);
    document.addEventListener('visibilitychange', function () { if (!document.hidden) tick(); });
  }

  function setPaused(paused) {
    state.paused = !!paused;
    DL.store('live-paused', paused ? '1' : '0');
    DL.bus.emit('live');
    if (!paused) tick();
  }

  DL.api = {
    source: source,
    get: get,
    file: file,
    invalidate: invalidate,
    versionOf: function (path) { return versions[path] || null; },
    version: function () { return state.version || root().dataset.version || null; },
    follow: follow,
    tick: tick,
    setPaused: setPaused,
    paused: function () { return state.paused; },
    offline: function () { return state.offline; }
  };
})(window.DL = window.DL || {});
