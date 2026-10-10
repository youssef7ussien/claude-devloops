/* main.js: starts the app once the page is parsed. Binds the shell (theme, menu, workspace
   switcher, Live button), builds the navigation and the status from `summary`, starts following
   the run (served) or says what the snapshot is (an export, contracts/export.md), and mounts the
   address's view. Listed last in scripts.txt. */
(function (DL) {
  'use strict';

  var root, summary = null;
  var NOTICE = 'Contains full Claude Code conversations — review before sharing';

  /* An export's top bar text, from the root's data-* attributes: "Snapshot · <exported-at> ·
     devloops <version>", and "run in progress" when it was exported during a run. */
  function snapshotLabel(ds) {
    var parts = ['Snapshot', DL.fmt.time(ds.exportedAt)];
    if (ds.devloopsVersion) parts.push('devloops ' + ds.devloopsVersion);
    if (ds.running === 'true') parts.push('run in progress');
    return parts.join(' · ');
  }

  function showSnapshot() {
    var label = DL.$('[data-snapshot]'), notice = DL.$('[data-notice]');
    if (label) { label.textContent = snapshotLabel(root.dataset); label.hidden = false; }
    if (notice) { notice.textContent = NOTICE; notice.hidden = false; }
  }

  /* The navigation entry a route belongs to. */
  function navKey(route) {
    var v = route.view;
    if (v === 'loop' || v === 'trial') return 'loop:' + route.params.loop;
    if (v === 'call') return 'calls';
    if (v === 'file') return 'files';
    return v;
  }

  function navLink(key, href, label, icon, extra) {
    var a = DL.el('a');
    a.href = href;
    a.dataset.nav = key;
    DL.add(a, DL.icon(icon), label, extra || null);
    return a;
  }

  function count(n) { return n == null ? null : DL.el('span', 'count', String(n)); }
  /* "6 & 12": the open questions and the planning assumptions. */
  function questionsCount(c) {
    if (c.questions == null) return null;
    var n = count(c.questions + ' & ' + (c.assumptions || 0));
    n.title = DL.fmt.plural(c.questions, 'open question') + ' and ' + DL.fmt.plural(c.assumptions || 0, 'assumption');
    return n;
  }

  function buildNav() {
    var nav = DL.$('.nav'), s = summary || {}, r = DL.router;
    if (!nav) return;
    var groups = [['Run', [navLink('overview', r.href('overview'), 'Overview', 'grid')]]];
    if (s.run) groups[0][1].push(navLink('run', r.href('run'), 'Run', 'flow'));
    var loops = (s.loops || []).map(function (l) {
      var st = DL.status(l.status, 'run'), dot = DL.el('span', 'dot tone-' + st[2]);
      dot.title = st[0];
      return navLink('loop:' + l.loop, r.href('loop', { loop: l.loop }), l.loop, 'loop', dot);
    });
    if (loops.length) groups.push(['Loops', loops]);
    var c = s.counts || {};
    groups.push(['Details', [
      navLink('calls', r.href('calls'), 'Claude calls', 'chat', count(c.calls)),
      navLink('questions', r.href('questions'), 'Questions', 'help', questionsCount(c)),
      navLink('files', r.href('files'), 'Files', 'folder'),  /* no count: the summary does not list the files (SC-001) */
      navLink('events', r.href('events'), 'Events', 'list', count(c.events))
    ]]);
    nav.textContent = '';
    groups.forEach(function (g) {
      DL.add(nav, DL.el('div', 'group', g[0]), g[1]);
    });
    markNav();
  }

  function markNav() {
    var key = DL.router.current ? navKey(DL.router.current) : 'overview';
    DL.$$('.nav a[data-nav]').forEach(function (a) {
      if (a.dataset.nav === key) a.setAttribute('aria-current', 'page');
      else a.removeAttribute('aria-current');
    });
  }

  function buildStatus() {
    var box = DL.$('[data-status]');
    if (box) {
      box.textContent = '';
      if (summary && summary.status) box.appendChild(DL.pill(summary.status, 'run'));
    }
    var gen = DL.$('[data-generated]');
    if (gen) gen.textContent = summary && summary.generated_at ? 'Updated ' + DL.fmt.time(summary.generated_at) : '';
    var sw = DL.$('select[data-action="workspace"]'), names = (summary && summary.workspaces) || [];
    if (sw && DL.api.source() === 'api') {
      sw.closest('.ws-switch').hidden = names.length < 2;
      sw.textContent = '';
      names.forEach(function (name) {
        var o = DL.el('option', null, name);
        o.value = name;
        o.selected = name === root.dataset.workspace;
        sw.appendChild(o);
      });
    }
  }

  /* The summary: the navigation, the status, and the workspaces to switch to. */
  function loadSummary() {
    return DL.api.get('summary').then(function (s) { summary = s; }, function () { /* keep the last one */ })
      .then(function () { buildNav(); buildStatus(); });
  }

  function setLive() {
    var b = DL.$('[data-action="live"]');
    if (!b) return;
    var offline = DL.api.offline(), paused = DL.api.paused();
    b.setAttribute('aria-pressed', String(!paused && !offline));
    b.classList.toggle('offline', offline);
    var label = DL.$('[data-live-label]', b);
    if (label) label.textContent = offline ? 'Offline' : paused ? 'Paused' : 'Live';
  }

  function bindShell() {
    var app = DL.$('.app');
    DL.$$('[data-action="theme"]').forEach(function (b) { b.addEventListener('click', DL.theme.toggle); });
    DL.$$('[data-action="menu"]').forEach(function (b) {
      b.addEventListener('click', function () { app.classList.toggle('nav-open'); });
    });
    if (app) app.addEventListener('click', function (ev) { if (ev.target === app) app.classList.remove('nav-open'); });
    DL.$$('[data-workspace-name]').forEach(function (n) { n.textContent = root.dataset.workspace || ''; });
    var sw = DL.$('select[data-action="workspace"]');
    if (sw) sw.addEventListener('change', function () { location.assign('../' + encodeURIComponent(sw.value) + '/'); });
    var live = DL.$('[data-action="live"]');
    if (DL.api.source() === 'api') {
      if (live) live.addEventListener('click', function () { DL.api.setPaused(!DL.api.paused()); });
      ['live', 'offline', 'online'].forEach(function (name) { DL.bus.on(name, setLive); });
    } else {
      if (live) live.hidden = true;
      showSnapshot();
    }
    if (DL.palette) {
      DL.$$('[data-action="palette"]').forEach(function (b) { b.addEventListener('click', function () { DL.palette.open(); }); });
    } else {
      DL.$$('[data-action="palette"]').forEach(function (b) { b.hidden = true; });
    }
  }

  function start() {
    root = document.documentElement;
    root.classList.add('js');
    DL.theme.init();
    bindShell();
    DL.bus.on('route', function (r) {
      var crumb = DL.$('[data-crumb]');
      if (crumb) crumb.textContent = r.title;
      document.title = 'devloops · ' + (root.dataset.workspace || '') + ' · ' + r.title;
      markNav();
      var app = DL.$('.app');
      if (app) app.classList.remove('nav-open');
    });
    DL.bus.on('changed', loadSummary);
    loadSummary();
    if (DL.palette) DL.palette.start();
    if (DL.now) DL.now.start(DL.$('#now'));
    DL.api.follow();
    setLive();
    if ('scrollRestoration' in history) history.scrollRestoration = 'manual';
    DL.router.start(DL.$('#view'));
  }

  DL.main = { start: start, navKey: navKey, snapshotLabel: snapshotLabel, NOTICE: NOTICE };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
  else start();
})(window.DL = window.DL || {});
