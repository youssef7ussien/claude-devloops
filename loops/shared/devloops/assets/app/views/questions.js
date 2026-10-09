/* views/questions.js: `#/questions` — the loops' open questions with their answers and where each
   came from, the planning assumptions, and the retries granted. */
(function (DL) {
  'use strict';

  function answer(q) {
    var cell = DL.td(DL.pill(q.status, 'answer'));
    if (q.answer) cell.appendChild(DL.el('div', q.status === 'suggested' ? 'muted' : null, q.answer));
    if ((q.status === 'suggested' || q.status === 'accepted') && q.reason) cell.appendChild(DL.el('div', 'muted small', 'Why: ' + q.reason));
    if (q.status === 'accepted' && q.source) cell.appendChild(DL.el('div', 'muted small', q.source));
    return cell;
  }

  DL.router.register('questions', {
    title: function () { return 'Questions'; },
    data: function () { return ['questions']; },
    render: function (data, params, el) {
      var d = data[0];
      var questions = d.questions.map(function (q) {
        var cell = DL.td(q.question);
        if (q.context) cell.appendChild(DL.el('div', 'muted small', q.context));
        return DL.add(DL.el('tr'), DL.td(q.loop), DL.td(DL.el('strong', null, q.id)), cell, answer(q));
      });
      var assumptions = d.assumptions.map(function (a) {
        return DL.add(DL.el('tr'), DL.td(a.loop), DL.td(DL.el('strong', null, a.id)), DL.td(a.text), DL.td(a.source || '', 'muted small'));
      });
      DL.add(el, DL.head('Questions and assumptions'),
        DL.el('h3', null, 'Open questions'),
        DL.table([['Loop'], ['ID'], ['Question'], ['Answer']], questions, { empty: 'No questions were raised.' }),
        DL.el('h3', null, 'Planning assumptions'),
        DL.table([['Loop'], ['ID'], ['Assumption'], ['Source']], assumptions, { empty: 'None recorded.' }));
      if (d.grants.length) {
        var grants = d.grants.map(function (g) {
          return DL.add(DL.el('tr'), DL.td(g.loop), DL.td(g.milestone_id || ''), DL.td(String(g.extra_trials), 'num'),
            DL.td(g.reason || ''), DL.td(DL.fmt.time(g.granted_at), 'muted small'));
        });
        DL.add(el, DL.el('h3', null, 'Retries granted'),
          DL.table([['Loop'], ['Milestone'], ['Trials', 1], ['Reason'], ['Granted']], grants));
      }
    }
  });
})(window.DL = window.DL || {});
