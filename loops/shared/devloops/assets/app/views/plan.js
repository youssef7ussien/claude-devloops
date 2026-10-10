/* views/plan.js: `#/loop/<loop>/plan` — the loop's plan and its progress (FR-020): while the plan
   waits for approval, a callout naming the commands; then each milestone in plan order with its
   status, goal, trials used, the milestones it depends on (links within the page), its acceptance
   criteria marked passing, failing (linking to the trial), or not checked, and its tasks with their
   requirement references; then the open questions with their answers, and the assumptions.
   `?m=<milestone>` scrolls to that milestone. */
(function (DL) {
  'use strict';

  function refs(list) {
    return list && list.length ? DL.el('span', 'refs', list.join(', ')) : null;
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
      return DL.el('p', 'muted small', (a.action === 'replan' ? 'Replanned and approved' : 'Approved') +
        (a.approved_at ? ' ' + DL.fmt.time(a.approved_at) : '') + '.');
    }
    return null;
  }

  function criterion(c) {
    var s = DL.status(c.state, 'criterion'), mark = DL.el('span', 'state tone-' + s[2], s[1]);
    mark.setAttribute('role', 'img');
    mark.setAttribute('aria-label', s[0]);
    mark.title = s[0];
    var li = DL.add(DL.el('li', 'criterion ' + c.state), mark,
      DL.add(DL.el('div'), DL.el('strong', null, c.id), ' ' + c.text + ' ', refs(c.requirement_refs)));
    if (c.trial_route) DL.add(li.lastChild, ' ', DL.link(c.trial_route, 'Why it fails'));
    return li;
  }

  function task(t) {
    var s = DL.status(t.status, 'task'), mark = DL.el('span', 'state tone-' + s[2], s[1]);
    mark.setAttribute('role', 'img');
    mark.setAttribute('aria-label', s[0]);
    mark.title = s[0];
    return DL.add(DL.el('li'), mark, DL.add(DL.el('div'), DL.el('strong', null, t.id), ' ' + t.title + ' ',
      refs(t.requirement_refs), t.description ? DL.el('div', 'muted small', t.description) : null));
  }

  function milestone(d, m) {
    var card = DL.el('section', 'card plan-ms');
    card.id = 'plan-' + m.id;
    var deps = null;
    if (m.depends_on.length) {
      deps = DL.add(DL.el('p', 'muted small'), 'Depends on ');
      m.depends_on.forEach(function (id, k) {
        DL.add(deps, k ? ', ' : null, DL.link(DL.router.href('plan', { loop: d.loop }, { m: id }), id));
      });
    }
    DL.add(card,
      DL.add(DL.el('h3'), DL.el('span', 'mid', m.id), ' ' + m.title + ' ', DL.pill(m.status, 'milestone'),
        DL.add(DL.el('span', 'muted small'), ' · ', DL.fmt.plural(m.trials_used, 'trial'), ' · ', DL.link(m.route, 'Trials and cost'))),
      m.goal ? DL.el('p', 'goal', m.goal) : null, deps,
      DL.el('h4', null, 'Acceptance criteria'),
      m.criteria.length ? DL.add(DL.el('ul', 'checklist'), m.criteria.map(criterion)) : DL.el('p', 'muted', 'No acceptance criteria.'),
      DL.el('h4', null, 'Tasks'),
      m.tasks.length ? DL.add(DL.el('ul', 'checklist'), m.tasks.map(task)) : DL.el('p', 'muted', 'No tasks.'));
    return card;
  }

  function questions(d) {
    var rows = d.open_questions.map(function (q) {
      return DL.add(DL.el('tr'), DL.td(DL.el('strong', null, q.id)),
        DL.td([DL.el('div', null, q.question), q.context ? DL.el('div', 'muted small', q.context) : null]),
        DL.td(q.answer ? q.answer : DL.el('span', 'muted', q.suggested_answer ? 'Suggested: ' + q.suggested_answer : '–')),
        DL.td(DL.pill(q.status, 'answer')));
    });
    return DL.table([['Question'], [''], ['Answer'], ['Status']], rows, { empty: 'No open questions.' });
  }

  function assumptions(d) {
    var rows = d.assumptions.map(function (a) {
      return DL.add(DL.el('tr'), DL.td(DL.el('strong', null, a.id || '')), DL.td(a.text), DL.td(a.source || '', 'small muted'));
    });
    return DL.table([['Assumption'], [''], ['Source']], rows, { empty: 'No assumptions.' });
  }

  DL.router.register('plan', {
    title: function (params) { return params.loop + ' · plan'; },
    data: function (params) { return ['loops/' + params.loop + '/plan']; },
    render: function (data, params, el, query, refresh) {
      var d = data[0], focus = (query || {}).m, done = 0;
      d.milestones.forEach(function (m) { if (m.status === 'achieved') done += 1; });
      DL.add(el, DL.head(d.loop + ' · plan', DL.pill(d.status, 'run'),
        d.milestones.length ? done + ' of ' + DL.fmt.plural(d.milestones.length, 'milestone') + ' achieved' : null),
        DL.add(DL.el('div', 'toolbar'), DL.add(DL.link(d.routes.loop, null, 'btn ghost'), DL.icon('loop'), d.loop)),
        approval(d));
      if (!d.milestones.length) el.appendChild(DL.el('p', 'muted', 'No plan stored yet.'));
      d.milestones.forEach(function (m) { el.appendChild(milestone(d, m)); });
      DL.add(el, DL.el('h3', null, 'Open questions'), questions(d), DL.el('h3', null, 'Assumptions'), assumptions(d));
      if (focus && !refresh) {
        setTimeout(function () {
          var target = document.getElementById('plan-' + focus);
          if (target && el.isConnected) target.scrollIntoView({ block: 'start' });
        }, 0);
      }
    }
  });
})(window.DL = window.DL || {});
