/* views/questions.js: `#/questions` — the loops' open questions with their answers and where each
   came from, and the planning assumptions (the retries granted show on their milestone in the loop
   view, FR-020j). Loop chips filter the questions and the assumptions together, `?loop=<loop>`
   starting with that loop's chip pressed (FR-020e); the plan ids a question affects show what they say on hover and focus (FR-020d). */
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
    render: function (data, params, el, query, refresh) {
      var d = data[0], refs = d.refs || {};
      function affects(q) {
        var ids = Array.isArray(q.affects) ? q.affects : (q.affects ? [q.affects] : []);
        return ids.length ? DL.add(DL.el('div', 'muted small'), 'Affects ', DL.refList(ids, refs[q.loop])) : null;
      }
      var questions = d.questions.map(function (q) {
        var cell = DL.td(q.question);
        if (q.context) cell.appendChild(DL.el('div', 'muted small', q.context));
        DL.add(cell, affects(q));
        var tr = DL.add(DL.el('tr'), DL.td(q.loop), DL.td(DL.el('strong', null, q.id)), cell, answer(q));
        tr.setAttribute('data-loop', q.loop);
        return tr;
      });
      var assumptions = d.assumptions.map(function (a) {
        var tr = DL.add(DL.el('tr'), DL.td(a.loop), DL.td(DL.el('strong', null, a.id)), DL.td([a.text, affects(a)]),
          DL.td(a.source || '', 'muted small'));
        tr.setAttribute('data-loop', a.loop);
        return tr;
      });
      var loops = Object.keys(refs);
      var bar = DL.filter(questions.concat(assumptions), { placeholder: 'Filter questions and assumptions…',
        groups: [{ attr: 'loop', label: 'Loops', chips: loops.map(function (l) { return [l, l]; }) }] });
      DL.add(el, DL.head('Questions and assumptions'), bar,
        DL.el('h3', null, 'Open questions'),
        DL.table([['Loop'], ['ID'], ['Question'], ['Answer']], questions, { empty: 'No questions were raised.' }),
        DL.el('h3', null, 'Planning assumptions'),
        DL.table([['Loop'], ['ID'], ['Assumption'], ['Source']], assumptions, { empty: 'None recorded.' }));
      if (!refresh && query) bar.choose('loop', query.loop);
    }
  });
})(window.DL = window.DL || {});
