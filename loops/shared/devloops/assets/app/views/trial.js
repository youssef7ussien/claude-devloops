/* views/trial.js: `#/loop/<loop>/m/<milestone>/t/<key>` — one trial (FR-018, FR-019): its outcome,
   duration, and totals; first, when it did not pass, why (each reason next to the evidence that
   decided it: screenshots as thumbnails, logs and response bodies in the viewer, the browser's
   requests with their errors marked); then its steps with their calls, the full validation
   result, the files in its folder, and the files its calls changed (each opening the call at the
   change). */
(function (DL) {
  'use strict';

  function code(text) { return DL.el('code', null, text); }

  /* A screenshot shown small, opening the viewer; another file as a link. */
  function evidenceItem(ref, list) {
    if (ref.kind !== 'image' || ref.missing || !ref.id) return DL.viewer.link(ref, ref.path.split('/').pop(), list);
    var a = DL.viewer.link(ref, null, list), img = DL.el('img', 'thumb');
    img.alt = ref.path.split('/').pop();
    a.textContent = '';
    a.appendChild(img);
    DL.api.file(ref).then(function (f) { if (f.url) img.src = f.url; }, function () { img.alt += ' (could not load)'; });
    return a;
  }

  function evidence(refs) {
    if (!refs || !refs.length) return null;
    var box = DL.el('div', 'evidence');
    refs.forEach(function (ref) { box.appendChild(evidenceItem(ref, refs)); });
    return box;
  }

  function list(items, cls) {
    return items && items.length ? DL.add(DL.el('ul', cls || null), items.map(function (x) { return DL.add(DL.el('li'), x); })) : null;
  }

  function requests(rows) {
    return DL.table([['Method'], ['URL'], ['Result']], rows.map(function (r) {
      var bad = !!r.error || (r.status != null && r.status >= 400);
      var tr = DL.add(DL.el('tr', bad ? 'err' : null), DL.td(r.method), DL.td(code(r.url)),
        DL.td(r.error ? r.error : r.status == null ? '–' : String(r.status), 'num'));
      return tr;
    }));
  }

  /* One reason the trial did not pass, as a card. */
  function reason(r) {
    var card = DL.el('div', 'card reason-card'), title;
    if (r.kind === 'check') {
      title = 'Check ' + r.check_id + ' failed';
      DL.add(card, DL.el('h4', null, title), DL.add(DL.el('p'), code(r.command || '')),
        DL.el('p', 'small', 'Response status: ' + (r.status == null ? 'none' : r.status)),
        list(r.failures), evidence(r.evidence));
    } else if (r.kind === 'criterion') {
      DL.add(card, DL.add(DL.el('h4'), 'Criterion ' + r.criterion_id + ' not met'),
        r.text ? DL.el('p', null, r.text) : null,
        r.steps.length ? DL.add(DL.el('ol', 'small'), r.steps.map(function (s) { return DL.el('li', null, s); })) : null,
        DL.add(DL.el('p', 'small'), DL.el('strong', null, 'Observed: '), r.observed || '–'), evidence(r.evidence));
    } else if (r.kind === 'contract') {
      DL.add(card, DL.el('h4', null, 'API contract not met'), r.problem ? DL.el('p', null, r.problem) : null,
        r.unmatched_operations.length ? DL.el('p', 'small', 'Not in the API document:') : null,
        list(r.unmatched_operations.map(code)),
        r.network_requests.length ? [DL.el('h5', null, 'Requests the browser made'), requests(r.network_requests)] : null);
    } else if (r.kind === 'unit-tests') {
      DL.add(card, DL.el('h4', null, 'Unit tests exited with ' + r.exit_code), r.command ? DL.add(DL.el('p'), code(r.command)) : null,
        r.log ? DL.add(DL.el('p', 'small'), 'Log: ', DL.viewer.link(r.log, r.log.path.split('/').pop())) : null);
    } else if (r.kind === 'boundary') {
      DL.add(card, DL.el('h4', null, 'Changed files outside the target'), list(r.violations.map(code)));
    } else if (r.kind === 'voided' || r.kind === 'interrupted') {
      DL.add(card, DL.el('h4', null, r.kind === 'voided' ? 'Voided (not counted)' : 'Interrupted'), DL.el('p', null, r.message));
    } else {
      DL.add(card, DL.el('h4', null, 'Failed' + (r.reason ? ': ' + r.reason : '')), r.detail ? DL.el('p', 'small detail', r.detail) : null);
    }
    return card;
  }

  function steps(d) {
    if (!d.steps.length) return [DL.el('p', 'muted', 'No Claude call was recorded for this trial.')];
    return d.steps.map(function (s) {
      var rows = s.calls.map(function (c) {
        var tr = DL.add(DL.el('tr'), DL.td(DL.link(c.route, '#' + c.seq), 'num'), DL.td(c.model || '–', 'small'),
          DL.td(DL.fmt.duration(c.duration_ms == null ? null : c.duration_ms / 1000), 'num'),
          DL.td(DL.fmt.money(c.totals.cost), 'num'), DL.td(DL.tokens(c.totals), 'num'),
          DL.td(c.failure_class && c.failure_class !== 'none' ? DL.pill('failed', 'trial') : '', null),
          DL.td(c.conversation === 'copied' ? '' : DL.el('span', 'muted small', 'conversation ' + c.conversation)));
        return DL.rowLink(tr, c.route);
      });
      var t = s.totals;
      return DL.add(DL.el('div', 'gap-top'),
        DL.add(DL.el('h4'), s.step + ' ', DL.el('span', 'muted small', DL.fmt.plural(t.calls, 'call') + ' · ' + DL.fmt.money(t.cost) + ' · '),
          DL.tokens(t), DL.el('span', 'muted small', ' tokens')),
        DL.table([['Call', 1], ['Model'], ['Duration', 1], ['Cost', 1], ['Tokens', 1], ['Result'], ['']], rows));
    });
  }

  function validation(d) {
    var v = d.validation;
    if (!v) return [DL.el('p', 'muted', d.status === 'in-progress' ? 'Not validated yet.' : 'No validation result was recorded for this trial.')];
    var out = [DL.add(DL.el('p'), DL.pill(v.passed ? 'passed' : 'failed', 'trial'), ' ' + v.kind + ' validation',
      v.ui_url ? DL.add(DL.el('span', 'muted small'), ' of ', code(v.ui_url)) : null)];
    var criteria = (v.criteria || []).map(function (c) {
      return DL.add(DL.el('tr'), DL.td(DL.el('strong', null, c.criterion_id)), DL.td(DL.pill(c.passed ? 'passed' : 'failed', 'trial')),
        DL.td(c.observed || '', 'small'), DL.td(evidence((c.evidence || []).map(function (e) { return ref(d, e); }))));
    });
    if (criteria.length) out.push(DL.el('h4', null, 'Criteria'), DL.table([['Criterion'], ['Result'], ['Observed'], ['Evidence']], criteria, { cls: 'criteria' }));
    var checks = (v.checks || []).map(function (c) {
      return DL.add(DL.el('tr'), DL.td(DL.el('strong', null, c.check_id)), DL.td(DL.pill(c.passed ? 'passed' : 'failed', 'trial')),
        DL.td(String((c.response || {}).status == null ? '–' : c.response.status), 'num'), DL.td(code(c.command || '')),
        DL.td(list(c.failures || [], 'small')));
    });
    if (checks.length) out.push(DL.el('h4', null, 'Checks'), DL.table([['Check'], ['Result'], ['Status', 1], ['Command'], ['Failures']], checks));
    var facts = DL.el('dl'), contract = v.contract || {}, unit = v.unit_tests || {}, boundary = v.boundary || {};
    DL.add(facts, DL.el('dt', null, 'API contract'), DL.el('dd', null, contract.passed ? 'met' : 'not met' + (contract.problem ? ': ' + contract.problem : '')),
      DL.el('dt', null, 'Unit tests'), DL.el('dd', null, !unit.enabled ? 'not run' : 'exit code ' + unit.exit_code),
      DL.el('dt', null, 'Boundary'), DL.el('dd', null, boundary.passed ? 'kept' : DL.fmt.plural((boundary.violations || []).length, 'violation')));
    out.push(DL.el('h4', null, 'Other checks'), facts);
    return out;
  }

  /* The FileRef of a path relative to the trial's folder, from the trial's own file list. */
  function ref(d, rel) {
    var want = rel.replace(/^\.\//, ''), found = null;
    d.evidence.forEach(function (r) { if (!found && r.path.slice(-want.length - 1) === '/' + want) found = r; });
    return found || { id: null, path: want, missing: true };
  }

  function changed(d) {
    var rows = d.files_changed.map(function (f) {
      return DL.add(DL.el('tr'), DL.td(code(f.path)), DL.td(f.step || ''), DL.td(f.tool || '', 'small'),
        DL.td(DL.link(f.call_route, 'Open the change')));
    });
    return DL.table([['File'], ['Step'], ['Tool'], ['']], rows, { empty: 'No file change was recorded in this trial’s conversations.' });
  }

  DL.router.register('trial', {
    title: function (params) { return params.milestone + ' · trial ' + params.key; },
    data: function (params) {
      return ['loops/' + params.loop + '/milestones/' + encodeURIComponent(params.milestone) + '/trials/' + encodeURIComponent(params.key)];
    },
    render: function (data, params, el) {
      var d = data[0], t = d.totals;
      var nav = DL.add(DL.el('div', 'toolbar'), DL.add(DL.link(d.routes.loop, null, 'btn ghost'), DL.icon('loop'), d.loop + ' · ' + d.milestone));
      if (d.routes.trials.length > 1) {
        var chips = DL.el('div', 'chips');
        chips.setAttribute('aria-label', 'Trials of ' + d.milestone);
        d.routes.trials.forEach(function (x) {
          var a = DL.link(x.route, 'Trial ' + x.key, 'chip');
          if (x.key === d.key) a.setAttribute('aria-current', 'page');
          a.title = DL.status(x.status, 'trial')[0];
          chips.appendChild(a);
        });
        nav.appendChild(chips);
      }
      DL.add(el, DL.head(d.milestone + ' · trial ' + d.key, DL.pill(d.status, 'trial'),
        d.title + ' · ' + d.kind + (d.attempt > 1 ? ' · attempt ' + d.attempt : '')), nav,
        DL.kpis([
          DL.kpi('Started', DL.fmt.time(d.started_at)),
          DL.kpi('Duration', DL.fmt.duration(d.seconds)),
          DL.kpi('Calls', String(t.calls)),
          DL.kpi('Cost', DL.fmt.money(t.cost)),
          DL.kpi('Tokens', DL.tokens(t))
        ], true, 'Trial totals'));
      if (d.why.length) {
        DL.add(el, DL.el('h3', null, d.status === 'void' ? 'Why it was voided' : 'Why it failed'),
          DL.add(DL.el('div', 'why'), d.why.map(reason)));
      }
      DL.add(el, DL.el('h3', null, 'Steps'), steps(d), DL.el('h3', null, 'Validation'), validation(d),
        DL.el('h3', null, 'Files in the trial’s folder'),
        d.evidence.length ? list(d.evidence.map(function (r) { return DL.viewer.link(r, r.path.split('/').slice(-2).join('/'), d.evidence); }), 'files')
          : DL.el('p', 'muted', d.key.indexOf('.') >= 0 ? 'This attempt was voided and run again under the same number: the folder holds the later attempt’s files.' : 'No file.'),
        DL.el('h3', null, 'Files changed'), changed(d));
    }
  });
})(window.DL = window.DL || {});
