/* views/run.js: `#/run` — the run across loops (run/state.json, from `summary`): each loop's step
   with its status, reason, start, and end, and the handoff from the backend to the frontend. */
(function (DL) {
  'use strict';

  DL.router.register('run', {
    title: function () { return 'Run'; },
    data: function () { return ['summary']; },
    render: function (data, params, el) {
      var run = data[0].run;
      if (!run) {
        DL.add(el, DL.head('Run'), DL.el('p', 'muted', 'No run has been recorded in this workspace.'));
        return;
      }
      var rows = (run.steps || []).map(function (s) {
        var tr = DL.el('tr');
        DL.add(tr, DL.td(DL.link(DL.router.href('loop', { loop: s.loop }), s.loop)), DL.td(DL.pill(s.status, 'run')),
          DL.td(s.reason || ''), DL.td(DL.fmt.time(s.started_at), 'muted small'), DL.td(DL.fmt.time(s.ended_at), 'muted small'));
        return tr;
      });
      DL.add(el, DL.head('Run', DL.pill(run.status, 'orchestrator')),
        DL.table([['Loop'], ['Status'], ['Reason'], ['Started'], ['Ended']], rows, { empty: 'No loop has run yet.' }));
      var handoff = run.handoff || {};
      if (Object.keys(handoff).length) {
        var spec = handoff.api_spec || {}, runtime = handoff.backend_runtime || {}, dl = DL.el('dl');
        DL.add(dl, DL.el('dt', null, 'API spec'),
          DL.add(DL.el('dd'), DL.el('code', null, spec.path || '–'), DL.el('div', 'muted small', 'sha256 ' + (spec.sha256 || '–'))));
        Object.keys(runtime).forEach(function (k) {
          DL.add(dl, DL.el('dt', null, 'Backend ' + k), DL.add(DL.el('dd'), DL.el('code', null, String(runtime[k]))));
        });
        el.appendChild(DL.add(DL.el('div', 'card gap-top'), DL.el('h3', null, 'Handoff'), dl));
      }
    }
  });
})(window.DL = window.DL || {});
