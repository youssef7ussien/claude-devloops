/* views/loop.js: `#/loop/<loop>` — one loop's page, with its plan merged in (FR-020): why it
   stopped and what to do next; while the plan waits, the commands that approve or replan it; its
   totals (one Tokens tile: its parts on hover or focus, the cache-hit rate below; FR-017); its
   outputs with the open questions and assumptions beside them, a button opening the Questions view
   filtered to the loop (FR-020e); its stack and runtime; the "Steps" card (FR-020c: one row per
   step in the order the steps first ran, each planning attempt a row of its own);
   and its milestones in plan order, each with its goal, dependencies, tasks, "Acceptance Criteria"
   as a table (each criterion with its result, what was observed, and its evidence grouped by
   check, FR-020g; a failed one links to the trial), and its trials, with "Expand all" and "Collapse all"
   (FR-020a, FR-020b). Every requirement, task, and criterion id shows what it says on hover and
   focus (FR-020d). `?m=<milestone>` opens that milestone and scrolls to it; `#/loop/<loop>/plan`
   is the same view (the router's alias). */
(function (DL) {
  'use strict';

  /* --- pure helpers (tested under node) ------------------------------------------------------- */

  function baseName(ref) { return String(ref.path || '').split('/').pop(); }

  /* A criterion's evidence grouped by check (FR-020g): the file name before its first dot names
     the check (`C1.body`, `C1.headers` → `C1`), in first-seen order; each file is
     `{ref, label: the name after that dot, image}`. A name without a dot is its own group. */
  function evidenceGroups(refs) {
    var groups = [], by = {};
    (refs || []).forEach(function (ref) {
      var name = baseName(ref), dot = name.indexOf('.');
      var check = dot > 0 ? name.slice(0, dot) : name, label = dot > 0 ? name.slice(dot + 1) : name;
      if (!by[check]) { by[check] = { check: check, files: [] }; groups.push(by[check]); }
      by[check].files.push({ ref: ref, label: label, image: ref.kind === 'image' });
    });
    return groups;
  }

  /* How far the plan got: `{achieved, total}`. */
  function progress(milestones) {
    var list = milestones || [];
    return { achieved: list.filter(function (m) { return m.status === 'achieved'; }).length, total: list.length };
  }

  /* A milestone's retries granted (FR-020j), oldest first: `[{trials, at, reason, accepted}]`. */
  function grantsOf(grants, id) {
    return (grants || []).filter(function (g) { return g.milestone_id === id; })
      .sort(function (a, b) { return String(a.granted_at || '') < String(b.granted_at || '') ? -1 : 1; })
      .map(function (g) {
        return { trials: g.extra_trials, at: g.granted_at || null, reason: g.reason || '',
          accepted: (g.accepted_suggestions || []).length };
      });
  }

  /* Retries granted for milestones the plan no longer has (a replan dropped them, FR-020j):
     `[{milestone, trials, at, reason, accepted}]`, oldest first. */
  function strayGrants(grants, milestones) {
    var known = {}, ids = [];
    (milestones || []).forEach(function (m) { known[m.id] = true; });
    (grants || []).forEach(function (g) { if (!known[g.milestone_id] && ids.indexOf(g.milestone_id) < 0) ids.push(g.milestone_id); });
    var out = [];
    ids.forEach(function (id) { grantsOf(grants, id).forEach(function (g) { out.push(Object.assign({ milestone: id }, g)); }); });
    return out.sort(function (a, b) { return String(a.at || '') < String(b.at || '') ? -1 : 1; });
  }

  /* A milestone's trials with its retries granted among them (FR-020j): each grant just before
     the first trial that started after it, the rest at the end. `[{trial} | {grant}]`. */
  function withGrants(trials, grants) {
    var out = [], left = (grants || []).slice();
    (trials || []).forEach(function (t) {
      while (left.length && left[0].at && t.started_at && left[0].at <= t.started_at) out.push({ grant: left.shift() });
      out.push({ trial: t });
    });
    left.forEach(function (g) { out.push({ grant: g }); });
    return out;
  }

  DL.loopView = { progress: progress, evidenceGroups: evidenceGroups, grantsOf: grantsOf, withGrants: withGrants, strayGrants: strayGrants };

  /* --- the view --------------------------------------------------------------------------------- */

  function kpis(d) {
    var s = d.stats, t = d.totals;
    return DL.kpis([
      DL.kpi('Milestones', s.achieved + ' / ' + s.milestones),
      DL.kpi('First-try', s.achieved ? DL.fmt.percent(s.first_try / s.achieved) : '–'),
      DL.kpi('Trials', String(s.trials)),
      DL.kpi('Calls', String(s.calls)),
      DL.kpi('Cost', DL.fmt.money(t.cost)),
      DL.kpi('Cost per milestone', DL.fmt.money(t.cost_per_achieved), 'per achieved milestone'),
      DL.kpi('Tokens', DL.tokens(t), 'hit rate ' + DL.fmt.percent(t.cache_hit_rate)),
      DL.kpi('Elapsed', DL.fmt.duration(s.seconds))
    ], true, 'Loop totals');
  }

  function toolbar(d) {
    var bar = DL.el('div', 'toolbar outputs gap-top');
    d.outputs.forEach(function (ref) {
      var a = DL.viewer.link(ref, ref.label, d.outputs);
      a.classList.add('btn');
      a.insertBefore(DL.icon(ref.kind === 'json' ? 'json' : 'md'), a.firstChild);
      bar.appendChild(a);
    });
    DL.add(bar, questionsButton(d));  /* null when the plan has no questions or assumptions */
    var r = DL.router;
    DL.add(bar, DL.el('span', 'spacer'),
      DL.add(DL.link(r.href('calls', null, { loop: d.loop }), null, 'btn ghost'), DL.icon('chat'), DL.fmt.plural(d.stats.calls, 'call')),
      DL.add(DL.link(r.href('files', null, { dir: d.loop }), null, 'btn ghost'), DL.icon('folder'), 'Files'));
    return bar;
  }

  function stack(d) {
    if (!d.stack && !d.runtime) return null;
    var st = d.stack || {}, rt = d.runtime || {}, dl = DL.el('dl');
    Object.keys(rt).forEach(function (k) {
      if (rt[k]) DL.add(dl, DL.el('dt', null, k), DL.add(DL.el('dd'), DL.el('code', null, String(rt[k]))));
    });
    DL.add(dl, DL.el('dt', null, 'target'), DL.add(DL.el('dd'), DL.el('code', null, d.target_dir || '–')));
    return DL.add(DL.el('div', 'grid cols-2'),
      DL.add(DL.el('div', 'card'), DL.el('h3', null, 'Stack'), DL.el('p', null, st.summary || '–'),
        DL.el('p', 'muted small', 'Source: ' + (st.source || '–'))),
      DL.add(DL.el('div', 'card'), DL.el('h3', null, 'Runtime'), dl));
  }

  function approval(d) {
    var a = d.approval || {};
    if (a.status === 'waiting') {
      var p = DL.add(DL.el('p', 'callout warn action'), DL.el('strong', null, 'This plan waits for your approval. '),
        'Review it, answer the open questions (an empty answer accepts Claude’s suggestion), then run ');
      a.commands.forEach(function (c, k) { DL.add(p, k ? ' or ' : null, DL.el('code', null, c)); });
      return DL.add(p, '.');
    }
    if (a.status === 'approved') {
      return DL.el('p', 'muted small', 'Plan ' + (a.action === 'replan' ? 'replanned and approved' : 'approved') +
        (a.approved_at ? ' ' + DL.fmt.time(a.approved_at) : '') + '.');
    }
    return null;
  }

  /* "6 open questions · 12 assumptions", beside the outputs, opening the Questions view filtered
     to the loop (FR-020e); a warning edge while the plan waits with questions unanswered. */
  function questionsButton(d) {
    var q = d.questions || {};
    if (!q.open && !q.assumptions) return null;
    var waiting = (d.approval || {}).status === 'waiting' && q.unanswered;
    var a = DL.link(q.route, null, 'btn questions-btn' + (waiting ? ' warn' : ''));
    DL.add(a, DL.icon('help'), DL.fmt.plural(q.open, 'open question'), ' · ', DL.fmt.plural(q.assumptions, 'assumption'));
    if (q.unanswered) a.title = q.unanswered + ' unanswered';
    return a;
  }

  var TRIAL_COLUMNS = [['#', 1], ['Kind'], ['Result'], ['Detail'], ['Duration', 1], ['Cost', 1], ['Tokens', 1]];

  /* "Retry granted: 2 more trials · <when> · <reason>" as a row across the trials table. */
  function grantRow(g) {
    var cell = DL.add(DL.el('td'), DL.icon('history'), DL.el('strong', null, 'Retry granted: '),
      DL.fmt.plural(g.trials, 'more trial'), g.at ? ' · ' + DL.fmt.time(g.at) : null,
      g.reason ? DL.add(DL.el('span', 'muted'), ' · ', g.reason) : null,
      g.accepted ? DL.el('span', 'muted', ' · ' + DL.fmt.plural(g.accepted, 'suggested answer') + ' accepted') : null);
    cell.colSpan = TRIAL_COLUMNS.length;
    return DL.add(DL.el('tr', 'grant'), cell);
  }

  function trialsTable(trials, empty, grants) {
    var rows = withGrants(trials, grants).map(function (x) {
      if (x.grant) return grantRow(x.grant);
      var t = x.trial;
      var detail = t.detail || '', cell = DL.td([], 'small detail');
      if (t.reason) DL.add(cell, DL.el('strong', null, t.reason), detail ? ': ' : '');
      DL.add(cell, detail.length > 600 ? detail.slice(0, 600) + '…' : detail);
      var tr = DL.add(DL.el('tr'), DL.td(String(t.key || t.n), 'num'), DL.td(t.kind || ''), DL.td(DL.pill(t.status, 'trial')), cell,
        DL.td(DL.fmt.duration(t.seconds), 'num'), DL.td(DL.fmt.money(t.totals ? t.totals.cost : null), 'num'),
        DL.td(t.totals ? DL.tokens(t.totals) : '–', 'num'));
      if (t.route) DL.rowLink(tr, t.route);
      return tr;
    });
    return DL.table(TRIAL_COLUMNS, rows, { empty: empty });
  }

  /* --- the Steps card (FR-020c) ----------------------------------------------------------------- */

  var COLUMNS = [['Step'], ['Calls', 1], ['Time', 1], ['Cost', 1], ['Tokens', 1], ['Share']];

  /* One row per step, in the order the rows first ran (the data's order); each planning attempt
     is a row of its own, linking to its call, a failed one marked with why on hover. */
  function stepsCard(d) {
    var rows = d.steps.map(function (s) {
      var t = s.totals || {}, share = DL.el('span', 'share'), fill = DL.el('span');
      if (s.share != null) fill.style.setProperty('width', Math.max(1, Math.round(100 * s.share)) + '%');
      share.appendChild(fill);
      share.setAttribute('aria-hidden', 'true');
      var name = DL.add(DL.el('td'), DL.el('strong', null, s.step),
        s.attempt ? DL.el('span', 'muted small', ' · attempt ' + s.attempt) : null);
      if (s.status && s.status !== 'passed') {
        var flag = DL.el('span', 'flag' + (s.status === 'failed' ? ' bad' : ''), DL.status(s.status, 'trial')[0].toLowerCase());
        var why = [s.reason, s.detail].filter(Boolean).join(': ');
        if (why) { flag.setAttribute('data-tip', why.length > 600 ? why.slice(0, 600) + '…' : why); flag.tabIndex = 0; }
        DL.add(name, ' ', flag);
      }
      var tr = DL.add(DL.el('tr'), name, DL.td(String(s.calls), 'num'), DL.td(DL.fmt.duration(s.seconds), 'num'),
        DL.td(DL.fmt.money(t.cost), 'num'), DL.td(DL.tokens(t), 'num'),
        DL.td([share, DL.el('span', 'small muted', s.share == null ? '–' : DL.fmt.percent(s.share))], 'share-cell'));
      DL.rowLink(tr, s.route || DL.router.href('calls', null, { loop: d.loop, step: s.step }));
      return tr;
    });
    return DL.add(DL.el('section', 'card steps-card'), DL.el('h3', null, 'Steps'),
      DL.table(COLUMNS, rows, { cls: 'steps', empty: 'No Claude call yet.' }));
  }

  /* --- milestones (FR-020a, FR-020b) ----------------------------------------------------------- */

  function mark(status, table) {
    var s = DL.status(status, table), m = DL.el('span', 'state tone-' + s[2], s[1]);
    m.setAttribute('role', 'img');
    m.setAttribute('aria-label', s[0]);
    m.title = s[0];
    return m;
  }

  function refs(ids, d) {
    return ids && ids.length ? DL.add(DL.el('span', 'refs'), DL.refList(ids, d.refs)) : null;
  }

  var CRITERION = { passed: 'passing', failed: 'failing' };

  /* A screenshot as a thumbnail, another file as a small link with its kind's icon; the path and
     size on hover; each opens in the viewer, stepping through `list`. */
  function evidenceFile(f, list, label) {
    var ref = f.ref, a = DL.viewer.link(ref, null, list);
    a.title = (ref.path || '') + (ref.size != null ? ' · ' + DL.fmt.bytes(ref.size) : '');
    a.textContent = '';
    if (f.image && !ref.missing && ref.id) {
      var img = DL.el('img', 'thumb');
      img.alt = baseName(ref);
      a.appendChild(img);
      a.classList.add('ev-thumb');
      DL.api.file(ref).then(function (data) { if (data.url) img.src = data.url; }, function () { img.alt += ' (could not load)'; });
      return a;
    }
    return DL.add(a, DL.icon(ref.icon || 'file', 'k ' + (ref.kind || '')), label || f.label);
  }

  /* The evidence grouped by check (FR-020g): a check with one file is that file alone (a
     screenshot's thumbnail, or the file's full name); a check with several has a short label
     (cut with "…", the whole name on hover), then its files. */
  function evidence(refs) {
    var box = DL.el('div', 'evidence grouped');
    evidenceGroups(refs).forEach(function (g) {
      var group = DL.el('span', 'ev-group');
      if (g.files.length === 1) group.appendChild(evidenceFile(g.files[0], refs, baseName(g.files[0].ref)));
      else {
        var name = DL.el('span', 'ev-check', g.check);
        name.title = g.check;
        group.appendChild(name);
        g.files.forEach(function (f) { group.appendChild(evidenceFile(f, refs)); });
      }
      box.appendChild(group);
    });
    return box;
  }

  /* One row of the criteria table: the criterion with its requirement refs, its result (a
     failed one links to its trial), what was observed, and its evidence. */
  function criterion(d, c) {
    var state = CRITERION[c.result] || 'unchecked';
    var result = c.result ? DL.pill(c.result, 'trial') : DL.el('span', 'muted small', 'Not checked');
    return DL.add(DL.el('tr', 'criterion ' + state),
      DL.td([DL.el('strong', null, c.id), ' ' + c.text + ' ', refs(c.requirement_refs, d)], 'crit'),
      DL.td([result, c.trial_route ? DL.add(DL.el('div', 'small'), DL.link(c.trial_route, 'Why it failed →')) : null], 'res'),
      DL.td(c.observed || '–', 'small observed'),
      DL.td(c.evidence && c.evidence.length ? evidence(c.evidence) : DL.el('span', 'muted small', '–'), 'ev'));
  }

  function task(d, t) {
    return DL.add(DL.el('li'), mark(t.status, 'task'), DL.add(DL.el('div'), DL.el('strong', null, t.id), ' ' + t.title + ' ',
      refs(t.requirement_refs, d), t.description ? DL.el('div', 'muted small', t.description) : null));
  }

  function milestone(d, m, focus, known) {
    var det = DL.el('details', 'ms'), sum = DL.el('summary'), dots = DL.el('span', 'trials');
    det.id = 'ms-' + m.id;
    det.open = focus ? focus === m.id : m.status !== 'achieved';
    dots.setAttribute('role', 'img');
    dots.setAttribute('aria-label', DL.fmt.plural(m.trials.length, 'trial'));
    m.trials.forEach(function (t) {
      var s = DL.status(t.status, 'trial'), i = DL.el('i', 'tone-' + s[2]);
      i.title = 'Trial ' + t.key + ': ' + s[0];
      dots.appendChild(i);
    });
    DL.add(sum, DL.icon('chev', 'chev'),
      DL.add(DL.el('span', 'head'), DL.el('span', 'mid', m.id), DL.el('span', 'mtitle', m.title), DL.pill(m.status, 'milestone')),
      DL.add(DL.el('span', 'meta'), dots, DL.el('span', null, DL.fmt.plural(m.trials.length, 'trial')),
        DL.el('span', null, DL.fmt.money(m.totals.cost)), DL.add(DL.el('span'), DL.tokens(m.totals), ' tokens'),
        DL.el('span', null, DL.fmt.duration(m.seconds))));
    var body = DL.el('div', 'body');
    if (m.goal) body.appendChild(DL.el('p', 'goal', m.goal));
    if (m.depends_on.length) {
      var deps = DL.add(DL.el('p', 'muted small'), 'Depends on ');
      m.depends_on.forEach(function (id, k) {
        DL.add(deps, k ? ', ' : null, known[id] ? DL.link(DL.router.href('loop', { loop: d.loop }, { m: id }), id) : id);
      });
      body.appendChild(deps);
    }
    DL.add(body, DL.el('h4', null, 'Tasks'),
      m.tasks.length ? DL.add(DL.el('ul', 'checklist'), m.tasks.map(function (t) { return task(d, t); }))
        : DL.el('p', 'muted', 'No tasks.'),
      DL.el('h4', null, 'Acceptance Criteria' + (m.criteria_trial ? ' · trial ' + m.criteria_trial : '')),
      DL.table([['Criterion'], ['Result'], ['Observed'], ['Evidence']], m.criteria.map(function (c) { return criterion(d, c); }),
        { cls: 'criteria', empty: 'No acceptance criteria.' }),
      DL.el('h4', null, 'Trials'), trialsTable(m.trials, 'No trials yet.', grantsOf(d.grants, m.id)));
    return DL.add(det, sum, body);
  }

  /* "Expand all" and "Collapse all": open or close every milestone of the view (the router keeps
     what is open while the view refreshes). */
  function foldAll(el) {
    function set(open) { return function () { DL.$$('details.ms', el).forEach(function (m) { m.open = open; }); }; }
    return DL.add(DL.el('div', 'toolbar fold-all'),
      DL.btn('Expand all', { cls: 'ghost', on: set(true) }), DL.btn('Collapse all', { cls: 'ghost', on: set(false) }));
  }

  function progressBar(d) {
    var p = progress(d.milestones);
    if (!p.total) return null;
    var bar = DL.el('div', 'progress'), fill = DL.el('span');
    bar.setAttribute('role', 'img');
    bar.setAttribute('aria-label', p.achieved + ' of ' + p.total + ' milestones achieved');
    fill.style.setProperty('width', Math.round(100 * p.achieved / p.total) + '%');
    bar.appendChild(fill);
    return DL.add(DL.el('span', 'plan-progress'), p.achieved + ' of ' + DL.fmt.plural(p.total, 'milestone') + ' achieved', bar);
  }

  DL.router.register('loop', {
    title: function (params) { return params.loop; },
    data: function (params) { return ['loops/' + params.loop]; },
    render: function (data, params, el, query, refresh) {
      var d = data[0], reason = d.status_reason || {}, focus = (query || {}).m, known = {};
      d.milestones.forEach(function (m) { known[m.id] = true; });
      el.appendChild(DL.head(d.loop, DL.pill(d.status, 'run'), progressBar(d)));
      if (reason.code || reason.message) {
        el.appendChild(DL.add(DL.el('p', 'callout bad reason'), DL.el('strong', null, reason.code || ''), ': ' + (reason.message || '')));
      }
      if (d.next_action) {
        var action = DL.add(DL.el('p', 'callout warn action'), DL.el('span', null, '→ '), DL.ticks(d.next_action.text));
        action.firstChild.setAttribute('aria-hidden', 'true');
        if (d.next_action.route && d.next_action.route !== DL.router.href('loop', { loop: d.loop })) {
          DL.add(action, ' ', DL.link(d.next_action.route, 'Open'));
        }
        el.appendChild(action);
      }
      DL.add(el, approval(d), kpis(d), toolbar(d), stack(d), stepsCard(d),
        DL.add(DL.el('div', 'ms-head'), DL.el('h3', null, 'Milestones'), d.milestones.length ? foldAll(el) : null));
      d.milestones.forEach(function (m) { el.appendChild(milestone(d, m, focus, known)); });
      if (!d.milestones.length) el.appendChild(DL.el('p', 'muted', 'No plan stored yet.'));
      var stray = strayGrants(d.grants, d.milestones);
      if (stray.length) {
        DL.add(el, DL.el('h4', null, 'Retries granted for milestones no longer in the plan'),
          DL.table([['Milestone'], ['Trials', 1], ['Granted'], ['Reason']], stray.map(function (g) {
            return DL.add(DL.el('tr'), DL.td(DL.el('strong', null, g.milestone || '?')), DL.td(String(g.trials), 'num'),
              DL.td(g.at ? DL.fmt.time(g.at) : '–', 'small'), DL.td(g.reason, 'small'));
          }), { cls: 'stray-grants' }));
      }
      if (focus && !refresh) {
        setTimeout(function () {
          var target = document.getElementById('ms-' + focus);
          if (target && el.isConnected) target.scrollIntoView({ block: 'start' });
        }, 0);
      }
    }
  });
})(window.DL = window.DL || {});
