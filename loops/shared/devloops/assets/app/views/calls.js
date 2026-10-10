/* views/calls.js: `#/calls` — every Claude call, filterable by loop, step, and text; a row opens
   the call (`#/call/<loop>/<seq>`). `?loop=<loop>` and `?step=<step>` start with those chips
   pressed (the loop view's Steps card links here, FR-020c). */
(function (DL) {
  'use strict';

  var MODEL_DEFAULT = '(Claude Code default)';

  /* The steps that have calls: those in `order` (the driver's, from the server) in that order,
     then any other by name ("?" for calls recorded without a step). */
  function steps(calls, order) {
    order = order || [];
    var seen = {};
    (calls || []).forEach(function (c) { seen[c.step || '?'] = true; });
    return Object.keys(seen).sort(function (a, b) {
      var i = order.indexOf(a), j = order.indexOf(b);
      return (i < 0 ? order.length : i) - (j < 0 ? order.length : j) || (a < b ? -1 : a > b ? 1 : 0);
    });
  }
  DL.callsView = { steps: steps };

  DL.router.register('calls', {
    title: function () { return 'Claude calls'; },
    data: function () { return ['calls']; },
    render: function (data, params, el, query, refresh) {
      var d = data[0];
      var rows = d.calls.map(function (c) {
        var failed = c.failure_class && c.failure_class !== 'none', result;
        if (failed) {
          result = DL.add(DL.el('span', 'pill tone-critical'), DL.el('span', null, '✕'), ' ' + c.failure_class);
          result.firstChild.setAttribute('aria-hidden', 'true');
        } else result = DL.el('span', 'muted small', 'ok');
        var tr = DL.add(DL.el('tr'), DL.td(c.loop), DL.td(String(c.seq), 'num'), DL.td(DL.el('strong', null, c.step || '?')),
          DL.td(c.milestone_id || 'planning'), DL.td(c.trial == null ? '' : String(c.trial), 'num'),
          DL.td(DL.el('code', 'small', (c.session_id || '').slice(0, 8))), DL.td(c.model || MODEL_DEFAULT, 'muted small'),
          DL.td(DL.tokens(c.totals), 'num'), DL.td(DL.fmt.money(c.totals.cost), 'num'),
          DL.td(DL.fmt.duration((c.duration_ms || 0) / 1000), 'num'), DL.td(result));
        tr.setAttribute('data-loop', c.loop);
        tr.setAttribute('data-step', c.step || '?'); /* as the loop view's Steps card names it */
        return DL.rowLink(tr, c.route);
      });
      var bar = DL.filter(rows, { placeholder: 'Filter calls…', groups: [
        { attr: 'loop', label: 'Loops', chips: d.loops.map(function (l) { return [l, l]; }) },
        { attr: 'step', label: 'Steps', chips: steps(d.calls, d.steps).map(function (s) { return [s, s]; }) }] });
      DL.add(el, DL.head('Claude calls', null, DL.fmt.plural(d.calls.length, 'headless Claude Code call')), bar,
        DL.table([['Loop'], ['#', 1], ['Step'], ['Milestone'], ['Trial', 1], ['Session'], ['Model'], ['Tokens', 1],
                  ['Cost', 1], ['Duration', 1], ['Result']], rows, { empty: 'No Claude call recorded.' }));
      if (d.by_model.length > 1) {
        el.appendChild(DL.el('p', 'muted small', 'Cost by model: ' + d.by_model.map(function (m) {
          return m.model + ' ' + DL.fmt.money(m.cost) + ' (' + DL.fmt.plural(m.calls, 'call') + ')';
        }).join(' · ')));
      }
      if (rows.length) el.appendChild(DL.el('p', 'muted small', 'Select a call to read its conversation, prompt, and settings.'));
      if (!refresh && query) { bar.choose('loop', query.loop); bar.choose('step', query.step); }
    }
  });
})(window.DL = window.DL || {});
