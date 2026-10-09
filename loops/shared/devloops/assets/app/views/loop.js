/* views/loop.js: `#/loop/<loop>` — one loop: why it stopped and what to do next, its totals with
   the tokens spelled out, its outputs (opened in the viewer), its stack and runtime, cost by step,
   planning, and its milestones with their tasks, acceptance criteria, and trials (each linking to
   the trial). `?m=<milestone>` opens that milestone and scrolls to it. */
(function (DL) {
  'use strict';

  function kpis(d) {
    var s = d.stats, t = d.totals, tok = t.tokens;
    return DL.kpis([
      DL.kpi('Milestones', s.achieved + ' / ' + s.milestones),
      DL.kpi('First-try', s.achieved ? DL.fmt.percent(s.first_try / s.achieved) : '–'),
      DL.kpi('Trials', String(s.trials)),
      DL.kpi('Calls', String(s.calls)),
      DL.kpi('Cost', DL.fmt.money(t.cost)),
      DL.kpi('Cost per milestone', DL.fmt.money(t.cost_per_achieved), 'per achieved milestone'),
      DL.kpi('Tokens', DL.tokens(t)),
      DL.kpi('Input', DL.fmt.tokens(tok.input)),
      DL.kpi('Output', DL.fmt.tokens(tok.output)),
      DL.kpi('Cache write', DL.fmt.tokens(tok.cache_creation)),
      DL.kpi('Cache read', DL.fmt.tokens(tok.cache_read), 'hit rate ' + DL.fmt.percent(t.cache_hit_rate)),
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
    if (d.ui_url) {
      var ui = DL.link(d.ui_url, d.ui_url);
      ui.target = '_blank';
      ui.rel = 'noopener noreferrer';
      bar.appendChild(DL.add(DL.el('span', 'tag'), 'UI ', ui));
    }
    var r = DL.router;
    DL.add(bar, DL.el('span', 'spacer'),
      DL.add(DL.link(r.href('plan', { loop: d.loop }), null, 'btn ghost'), DL.icon('plan'), 'Plan'),
      DL.add(DL.link(r.href('calls', null, { loop: d.loop }), null, 'btn ghost'), DL.icon('chat'), DL.fmt.plural(d.stats.calls, 'call')),
      DL.add(DL.link(r.href('files'), null, 'btn ghost'), DL.icon('folder'), 'Files'));
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

  function trialsTable(trials, empty) {
    var rows = trials.map(function (t) {
      var detail = t.detail || '', cell = DL.td([], 'small detail');
      if (t.reason) DL.add(cell, DL.el('strong', null, t.reason), ': ');
      DL.add(cell, detail.length > 600 ? detail.slice(0, 600) + '…' : detail);
      var tr = DL.add(DL.el('tr'), DL.td(String(t.key || t.n), 'num'), DL.td(t.kind || ''), DL.td(DL.pill(t.status, 'trial')), cell,
        DL.td(DL.fmt.duration(t.seconds), 'num'), DL.td(DL.fmt.money(t.totals ? t.totals.cost : t.cost), 'num'),
        DL.td(t.totals ? DL.tokens(t.totals) : '–', 'num'));
      if (t.route) DL.rowLink(tr, t.route);
      return tr;
    });
    return DL.table([['#', 1], ['Kind'], ['Result'], ['Detail'], ['Duration', 1], ['Cost', 1], ['Tokens', 1]], rows, { empty: empty });
  }

  function milestone(d, m, focus) {
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
    if (m.depends_on.length) body.appendChild(DL.el('p', 'muted small', 'Depends on ' + m.depends_on.join(', ')));
    var tasks = m.tasks.map(function (t) {
      var done = t.status === 'achieved', check = DL.el('span', 'check' + (done ? ' on' : ''), done ? '✓' : '○');
      check.setAttribute('aria-label', done ? 'achieved' : t.status);
      return DL.add(DL.el('li'), check, DL.add(DL.el('div'), DL.el('strong', null, t.id), ' ' + t.title + ' ',
        DL.el('span', 'refs', (t.requirement_refs || []).join(', ')), DL.el('div', 'muted small', t.description || '')));
    });
    var criteria = m.criteria.map(function (c) {
      var evidence = DL.el('div', 'evidence');
      c.evidence.forEach(function (ref) { evidence.appendChild(DL.viewer.link(ref, ref.path.split('/').pop(), c.evidence)); });
      return DL.add(DL.el('tr'), DL.td([DL.el('strong', null, c.id), ' ' + c.text]),
        DL.td(c.result ? DL.pill(c.result, 'trial') : DL.el('span', 'muted small', 'Not validated')),
        DL.td(c.observed || '', 'small'), DL.td(evidence));
    });
    DL.add(body, DL.el('h4', null, 'Tasks'), DL.add(DL.el('ul', 'tasks'), tasks),
      DL.el('h4', null, 'Acceptance criteria' + (m.criteria_trial ? ' · trial ' + m.criteria_trial : '')),
      DL.table([['Criterion'], ['Result'], ['Observed'], ['Evidence']], criteria, { cls: 'criteria', empty: 'No acceptance criteria.' }),
      DL.el('h4', null, 'Trials'), trialsTable(m.trials, 'No trials yet.'));
    return DL.add(det, sum, body);
  }

  function steps(d) {
    var names = Object.keys(d.by_step).sort(function (a, b) { return d.by_step[b].cost - d.by_step[a].cost; });
    var rows = names.map(function (n) {
      var t = d.by_step[n];
      return DL.add(DL.el('tr'), DL.td(DL.el('strong', null, n)), DL.td(String(t.calls), 'num'),
        DL.td(DL.fmt.money(t.cost), 'num'), DL.td(DL.tokens(t), 'num'));
    });
    return DL.table([['Step'], ['Calls', 1], ['Cost', 1], ['Tokens', 1]], rows, { empty: 'No Claude call yet.' });
  }

  DL.router.register('loop', {
    title: function (params) { return params.loop; },
    data: function (params) { return ['loops/' + params.loop]; },
    render: function (data, params, el, query, refresh) {
      var d = data[0], reason = d.status_reason || {}, focus = (query || {}).m;
      el.appendChild(DL.head(d.loop, DL.pill(d.status, 'run')));
      if (reason.code || reason.message) {
        el.appendChild(DL.add(DL.el('p', 'callout bad reason'), DL.el('strong', null, reason.code || ''), ': ' + (reason.message || '')));
      }
      if (d.next_action) {
        var action = DL.add(DL.el('p', 'callout warn action'), DL.el('span', null, '→ '), DL.ticks(d.next_action.text));
        action.firstChild.setAttribute('aria-hidden', 'true');
        if (d.next_action.route) DL.add(action, ' ', DL.link(d.next_action.route, 'Open'));
        el.appendChild(action);
      }
      DL.add(el, kpis(d), toolbar(d), stack(d), DL.el('h3', null, 'Cost by step'), steps(d),
        DL.el('h3', null, 'Planning'), trialsTable(d.planning.trials, 'No planning trial yet.'),
        DL.el('h3', null, 'Milestones'));
      d.milestones.forEach(function (m) { el.appendChild(milestone(d, m, focus)); });
      if (!d.milestones.length) el.appendChild(DL.el('p', 'muted', 'No plan stored yet.'));
      if (focus && !refresh) {
        setTimeout(function () {
          var target = document.getElementById('ms-' + focus);
          if (target && el.isConnected) target.scrollIntoView({ block: 'start' });
        }, 0);
      }
    }
  });
})(window.DL = window.DL || {});
