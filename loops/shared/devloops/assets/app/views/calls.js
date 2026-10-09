/* views/calls.js: `#/calls` — every Claude call, filterable by loop and text; a row opens the call
   (`#/call/<loop>/<seq>`). `?loop=<loop>` starts with that loop's chip pressed. */
(function (DL) {
  'use strict';

  var MODEL_DEFAULT = '(Claude Code default)';

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
        var tr = DL.add(DL.el('tr'), DL.td(c.loop), DL.td(String(c.seq), 'num'), DL.td(DL.el('strong', null, c.step)),
          DL.td(c.milestone_id || 'planning'), DL.td(c.trial == null ? '' : String(c.trial), 'num'),
          DL.td(DL.el('code', 'small', (c.session_id || '').slice(0, 8))), DL.td(c.model || MODEL_DEFAULT, 'muted small'),
          DL.td(DL.tokens(c.totals), 'num'), DL.td(DL.fmt.money(c.totals.cost), 'num'),
          DL.td(DL.fmt.duration((c.duration_ms || 0) / 1000), 'num'), DL.td(result));
        tr.setAttribute('data-loop', c.loop);
        return DL.rowLink(tr, c.route);
      });
      var bar = DL.filter(rows, { placeholder: 'Filter calls…', attr: 'loop', chipsLabel: 'Loops',
                                   chips: d.loops.map(function (l) { return [l, l]; }) });
      DL.add(el, DL.head('Claude calls', null, DL.fmt.plural(d.calls.length, 'headless Claude Code call')), bar,
        DL.table([['Loop'], ['#', 1], ['Step'], ['Milestone'], ['Trial', 1], ['Session'], ['Model'], ['Tokens', 1],
                  ['Cost', 1], ['Duration', 1], ['Result']], rows, { empty: 'No Claude call recorded.' }));
      if (d.by_model.length > 1) {
        el.appendChild(DL.el('p', 'muted small', 'Cost by model: ' + d.by_model.map(function (m) {
          return m.model + ' ' + DL.fmt.money(m.cost) + ' (' + DL.fmt.plural(m.calls, 'call') + ')';
        }).join(' · ')));
      }
      if (rows.length) el.appendChild(DL.el('p', 'muted small', 'Select a call to read its conversation, prompt, and settings.'));
      var chip = !refresh && query && query.loop && DL.$('[data-chip="' + CSS.escape(query.loop) + '"]', bar);
      if (chip) chip.click();
    }
  });
})(window.DL = window.DL || {});
