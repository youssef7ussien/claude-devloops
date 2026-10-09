/* views/overview.js: `#/` — the workspace at a glance, from `summary` only: the totals, what needs
   attention (each item links to where to look), a card per loop, the trial timeline, and cost by
   milestone and by step. */
(function (DL) {
  'use strict';

  var ATTENTION = { critical: ['✕', 'Needs action'], warning: ['!', 'Check'], info: ['i', 'Note'] };

  function kpis(s) {
    var t = s.totals || {};
    return DL.kpis([
      DL.kpi('Status', DL.pill(s.status, 'run')),
      DL.kpi('Milestones achieved', t.achieved + ' / ' + t.milestones),
      DL.kpi('First-try pass rate', t.achieved ? DL.fmt.percent(t.first_try / t.achieved) : '–', 'achieved on trial 1'),
      DL.kpi('Trials', String(t.trials), 'counted (voids excluded)'),
      DL.kpi('Claude calls', String(t.calls)),
      DL.kpi('Cost', DL.fmt.money(t.cost)),
      DL.kpi('Tokens', DL.tokens(t), 'input + output + cache'),
      DL.kpi('Elapsed', DL.fmt.duration(t.elapsed), 'first to last recorded action')
    ], false, 'Totals');
  }

  function item(a) {
    var li = DL.el('li', 'tone-' + a.tone), icon = DL.el('span', 'a-icon', ATTENTION[a.tone][0]);
    icon.setAttribute('aria-hidden', 'true');
    var body = DL.el('div');
    if (a.kind === 'loop') {
      DL.add(body, DL.add(DL.link(a.route, null), DL.el('strong', null, a.loop)), ' is ', DL.pill(a.status, 'run'),
        a.reason ? ' ' + a.reason : null);
      if (a.action) {
        var next = DL.add(DL.el('div', 'small'), '→ ', DL.ticks(a.action.text));
        if (a.action.route) DL.add(next, ' ', DL.link(a.action.route, 'Open'));
        body.appendChild(next);
      }
    } else if (a.kind === 'large-evidence') {
      DL.add(body, a.message + ': ');
      a.files.forEach(function (f, i) {
        DL.add(body, i ? ', ' : null, f.route ? DL.link(f.route, f.path) : f.path, ' (' + DL.fmt.bytes(f.bytes) + ')');
      });
    } else {
      body.appendChild(DL.link(a.route, a.message));
    }
    return DL.add(li, icon, DL.el('span', 'sr-only', ATTENTION[a.tone][1] + ': '), body);
  }

  function attention(items) {
    if (!items.length) {
      var ok = DL.el('div', 'attention ok'), icon = DL.el('span', 'a-icon tone-good', '✓');
      icon.setAttribute('aria-hidden', 'true');
      return DL.add(ok, icon, 'Nothing needs attention.');
    }
    var box = DL.el('section', 'attention'), urgent = items.some(function (a) { return a.tone !== 'info'; });
    box.setAttribute('aria-label', urgent ? 'Needs attention' : 'Worth knowing');
    DL.add(box, DL.add(DL.el('h3', null, urgent ? 'Needs attention ' : 'Worth knowing '), DL.el('span', 'count', String(items.length))),
      DL.add(DL.el('ul'), items.map(item)));
    return box;
  }

  function card(l) {
    var a = DL.link(l.route, null, 'card loop-card'), m = l.milestones || {};
    var bar = DL.el('div', 'progress'), fill = DL.el('span');
    bar.setAttribute('role', 'img');
    bar.setAttribute('aria-label', m.achieved + ' of ' + m.total + ' milestones achieved');
    fill.style.width = (m.total ? Math.round(100 * m.achieved / m.total) : 0) + '%';
    bar.appendChild(fill);
    function fact(value, word) { return DL.add(DL.el('span'), DL.add(DL.el('b'), value), word ? ' ' + word : null); }
    var t = l.totals || {};
    DL.add(a,
      DL.add(DL.el('div', 'row'), DL.icon('loop'), DL.el('span', 'name', l.loop), DL.add(DL.el('span', 'end'), DL.pill(l.status, 'run'))),
      bar,
      DL.add(DL.el('div', 'facts'), fact(m.achieved + '/' + m.total, 'milestones'), fact(String(l.trials), 'trials'),
        fact(String(t.calls), 'calls'), fact(DL.fmt.money(t.cost)), fact(DL.tokens(t), 'tokens'), fact(DL.fmt.duration(l.seconds))),
      l.next_action ? DL.add(DL.el('div', 'small next'), '→ ', DL.ticks(l.next_action.text)) : null);
    return a;
  }

  function costCharts(s) {
    var milestones = (s.cost_by_milestone || []).map(function (r) {
      var t = r.totals;
      return {
        label: r.loop + ' · ' + (r.id || 'Planning'), value: t.cost,
        tip: r.loop + ' ' + (r.id ? r.id + ' ' + r.title : 'planning') + ': ' + DL.fmt.money(t.cost) + ' over ' +
          DL.fmt.plural(t.calls, 'call') + ', ' + DL.fmt.plural(r.trials, 'trial') + ', ' + DL.fmt.tokens(t.tokens.total) + ' tokens'
      };
    });
    var steps = (s.by_step || []).map(function (r) {
      var t = r.totals;
      return { label: r.step, value: t.cost, tip: r.step + ': ' + DL.fmt.money(t.cost) + ' over ' + DL.fmt.plural(t.calls, 'call') +
        ', ' + DL.fmt.tokens(t.tokens.total) + ' tokens (' + DL.fmt.tokenParts(t.tokens) + ')' };
    });
    function box(title, rows, col) {
      return DL.add(DL.el('div', 'card'), DL.el('h3', null, title),
        DL.charts.bars(rows, { format: DL.fmt.money, title: title, columns: [col, 'Cost'] }));
    }
    return DL.add(DL.el('div', 'grid cols-2 gap-top'), box('Cost by milestone', milestones, 'Milestone'), box('Cost by step', steps, 'Step'));
  }

  DL.router.register('overview', {
    title: function () { return 'Overview'; },
    data: function () { return ['summary']; },
    render: function (data, params, el) {
      var s = data[0], req = s.requirements || {}, sub = DL.el('span');
      if (req.path) DL.add(sub, 'Requirements ', DL.el('code', null, req.path), ' · mode ' + (req.mode || '–'),
        req.story_id ? ' · story ' + req.story_id : null, ' · ');
      DL.add(sub, 'generated ' + DL.fmt.time(s.generated_at));
      DL.add(el, DL.head('Overview', null, sub), kpis(s), attention(s.attention || []));
      if (!(s.loops || []).length) {
        el.appendChild(DL.el('p', 'muted gap-top', 'No loop has started in this workspace yet.'));
        return;
      }
      DL.add(el, DL.el('h3', null, 'Loops'), DL.add(DL.el('div', 'grid cols-2'), s.loops.map(card)),
        DL.el('h3', null, 'Trial timeline'), DL.add(DL.el('div', 'card'), DL.charts.timeline(s.timeline || [])),
        costCharts(s));
    }
  });
})(window.DL = window.DL || {});
