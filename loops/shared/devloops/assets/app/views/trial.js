/* views/trial.js: `#/loop/<loop>/m/<milestone>/t/<key>` — one trial (FR-018, FR-019): its outcome,
   duration, and totals; first, when it did not pass, why (each reason next to the evidence that
   decided it: screenshots as thumbnails, logs and response bodies in the viewer, the browser's
   requests with their errors marked); then its calls in one table, one row per call with how it
   ended (FR-018a), the validation's criteria and one Checks table (FR-018c), the files its calls
   changed with lines added and removed, each change opening in a dialog (FR-018d), and the files
   in its folder as the Files view's tree (FR-018b). Requirement, task, and criterion ids show their text on
   hover (FR-020d), from the loop's `refs`. */
(function (DL) {
  'use strict';

  function code(text) { return DL.el('code', null, text); }
  function time(iso) { var t = iso ? Date.parse(iso) : NaN; return isNaN(t) ? null : t; }

  /* --- pure helpers (DL.trialView, tests/trial.test.js) ----------------------------------------- */

  function zero() {
    return { calls: 0, cost: 0, duration_ms: null, partial: false,
             tokens: { input: 0, output: 0, cache_creation: 0, cache_read: 0, total: 0 } };
  }
  /* `into` plus a call's totals (or another sum), as dashboard.add does. */
  function addUp(into, t, calls, ms) {
    into.calls += calls;
    into.cost += (t && t.cost) || 0;
    Object.keys(into.tokens).forEach(function (k) { into.tokens[k] += ((t && t.tokens) || {})[k] || 0; });
    into.partial = into.partial || !!(t && t.partial);
    if (ms != null) into.duration_ms = (into.duration_ms || 0) + ms;
  }

  /* The steps table's rows (FR-018a): `{type: 'call', step, call, at}` per call in the order the
     calls ran (by seq; a step makes one call per trial, so no step headings), `at` in ms since
     `startedAt` (the trial's start) or null, then a last `{type: 'total', totals}` summing them.
     Totals: `{calls, cost, tokens, partial, duration_ms}`. */
  function rows(steps, startedAt) {
    var calls = [], all = zero(), t0 = time(startedAt);
    (steps || []).forEach(function (s) { (s.calls || []).forEach(function (c) { calls.push({ step: s.step, call: c }); }); });
    calls.sort(function (a, b) { return (a.call.seq || 0) - (b.call.seq || 0); });
    var out = calls.map(function (x) {
      var cs = time(x.call.started_at);
      addUp(all, x.call.totals, 1, x.call.duration_ms);
      return { type: 'call', step: x.step, call: x.call, at: cs != null && t0 != null ? Math.max(0, cs - t0) : null };
    });
    out.push({ type: 'total', totals: all });
    return out;
  }

  /* The driver's failure reasons (claude.py `_classify`, engine.py) as the Result column says them. */
  var REASONS = { timeout: 'timeout', 'invalid-output': 'invalid output', 'claude-error': 'Claude error',
                  'auth-failed': 'service error', 'rate-limited': 'service error',
                  'service-unavailable': 'service error', interrupted: 'interrupted' };

  /* How a call ended (FR-018a): `{ok: true}`, or `{ok: false, label, detail}`. The call's
     `failure_class` (none | work | service) says whether it failed; its label comes from the
     call's own fields when they are there (`failure_reason`, `timed_out`, `api_error_status`,
     `is_error`, `subtype`), else from `hint` (`{reason, detail}`: the trial's failure, given for
     the trial's last failed call); a service failure without one is "service error", a work
     failure "failed". */
  function result(call, hint) {
    var fc = call.failure_class;
    if (!fc || fc === 'none') return { ok: true };
    var reason = call.failure_reason || (call.timed_out ? 'timeout' : null), detail = call.failure_detail || null;
    if (!reason && hint && hint.reason) { reason = hint.reason; detail = detail || hint.detail || null; }
    if (!reason && fc === 'work' && call.subtype !== undefined) {
      reason = call.is_error || call.subtype !== 'success' ? 'claude-error' : 'invalid-output';
    }
    var label = REASONS[reason] || (reason ? String(reason).replace(/-/g, ' ') : fc === 'service' ? 'service error' : 'failed');
    /* a service error names which one (auth-failed, rate-limited, service-unavailable) on hover */
    if (label === 'service error' && reason) detail = reason + (detail ? ': ' + detail : '');
    if (!detail && call.api_error_status != null) detail = 'api_error_status=' + call.api_error_status;
    if (!detail && call.subtype) detail = 'subtype=' + call.subtype;
    return { ok: false, label: label, detail: detail };
  }

  /* The Checks table's rows (FR-018c), in order: each HTTP check, the API contract, the unit
     tests, the boundary. Each `{kind, id, result: 'passed'|'failed'|'not run', detail, command?,
     status?, failures?, operations?, evidence: [path relative to the trial folder], log?}`. */
  function checks(v) {
    if (!v) return [];
    var out = [];
    (v.checks || []).forEach(function (c) {
      var r = c.response || {};
      out.push({ kind: 'check', id: c.check_id, result: c.passed ? 'passed' : 'failed', command: c.command || '',
        status: r.status == null ? null : r.status, failures: c.failures || [],
        detail: 'response status ' + (r.status == null ? 'none' : r.status),
        evidence: [r.body_path, r.headers_path].filter(Boolean) });
    });
    var ct = v.contract;
    if (ct) {
      var ops = ct.unmatched_operations || [];
      out.push({ kind: 'contract', id: 'API contract', result: ct.passed ? 'passed' : 'failed', operations: ops,
        detail: ct.passed ? 'every call is in the API document' + ((ct.covered_operations || []).length
          ? ' · ' + DL.fmt.plural(ct.covered_operations.length, 'operation') + ' verified' : '')
          : (ct.problem || (ops.length ? DL.fmt.plural(ops.length, 'operation') + ' not in the API document' : 'not met')),
        evidence: [] });
    }
    var u = v.unit_tests;
    if (u) {
      out.push(!u.enabled ? { kind: 'unit-tests', id: 'Unit tests', result: 'not run', detail: 'not enabled for this loop', evidence: [] }
        : { kind: 'unit-tests', id: 'Unit tests', result: u.exit_code === 0 ? 'passed' : 'failed', command: u.command || '',
            detail: 'exit code ' + (u.exit_code == null ? '–' : u.exit_code), log: u.log_path || null,
            evidence: u.log_path ? [u.log_path] : [] });
    }
    var b = v.boundary;
    if (b) {
      var bad = b.violations || [];
      out.push({ kind: 'boundary', id: 'Boundary', result: b.passed ? 'passed' : 'failed', failures: bad,
        detail: b.passed ? 'every write inside the target' : DL.fmt.plural(bad.length, 'write') + ' outside the target',
        evidence: [] });
    }
    return out;
  }

  /* --- evidence ------------------------------------------------------------------------------ */

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

  /* The FileRef of a path relative to the trial's folder, from the trial's own file list. */
  function ref(d, rel) {
    var want = rel.replace(/^\.\//, ''), found = null;
    d.evidence.forEach(function (r) { if (!found && r.path.slice(-want.length - 1) === '/' + want) found = r; });
    return found || { id: null, path: want, missing: true };
  }

  function requests(rows) {
    return DL.table([['Method'], ['URL'], ['Result']], rows.map(function (r) {
      var bad = !!r.error || (r.status != null && r.status >= 400);
      var tr = DL.add(DL.el('tr', bad ? 'err' : null), DL.td(r.method), DL.td(code(r.url)),
        DL.td(r.error ? r.error : r.status == null ? '–' : String(r.status), 'num'));
      return tr;
    }));
  }

  /* --- why it failed (FR-019) -------------------------------------------------------------------- */

  function whyId(kind, id) { return 'why-' + kind + '-' + String(id).replace(/\s+/g, '_'); }

  /* One reason the trial did not pass, as a card (with an id the validation's rows link to). */
  function reason(r, refs) {
    var card = DL.el('div', 'card reason-card');
    card.tabIndex = -1;
    if (r.kind === 'check') {
      card.id = whyId('check', r.check_id);
      DL.add(card, DL.add(DL.el('h4'), 'Check ', DL.ref(r.check_id, refs), ' failed'), DL.add(DL.el('p'), code(r.command || '')),
        DL.el('p', 'small', 'Response status: ' + (r.status == null ? 'none' : r.status)),
        list(r.failures), evidence(r.evidence));
    } else if (r.kind === 'criterion') {
      card.id = whyId('criterion', r.criterion_id);
      DL.add(card, DL.add(DL.el('h4'), 'Criterion ', DL.ref(r.criterion_id, refs), ' not met'),
        r.text ? DL.el('p', null, r.text) : null,
        r.steps.length ? DL.add(DL.el('ol', 'small'), r.steps.map(function (s) { return DL.el('li', null, s); })) : null,
        DL.add(DL.el('p', 'small'), DL.el('strong', null, 'Observed: '), r.observed || '–'), evidence(r.evidence));
    } else if (r.kind === 'contract') {
      card.id = whyId('contract', 'x');
      DL.add(card, DL.el('h4', null, 'API contract not met'), r.problem ? DL.el('p', null, r.problem) : null,
        r.unmatched_operations.length ? DL.el('p', 'small', 'Not in the API document:') : null,
        list(r.unmatched_operations.map(code)),
        r.network_requests.length ? [DL.el('h5', null, 'Requests the browser made'), requests(r.network_requests)] : null);
    } else if (r.kind === 'unit-tests') {
      card.id = whyId('unit-tests', 'x');
      DL.add(card, DL.el('h4', null, 'Unit tests exited with ' + r.exit_code), r.command ? DL.add(DL.el('p'), code(r.command)) : null,
        r.log ? DL.add(DL.el('p', 'small'), 'Log: ', DL.viewer.link(r.log, r.log.path.split('/').pop())) : null);
    } else if (r.kind === 'boundary') {
      card.id = whyId('boundary', 'x');
      DL.add(card, DL.el('h4', null, 'Changed files outside the target'), list(r.violations.map(code)));
    } else if (r.kind === 'voided' || r.kind === 'interrupted') {
      DL.add(card, DL.el('h4', null, r.kind === 'voided' ? 'Voided (not counted)' : 'Interrupted'), DL.el('p', null, r.message));
    } else {
      DL.add(card, DL.el('h4', null, 'Failed' + (r.reason ? ': ' + r.reason : '')), r.detail ? DL.el('p', 'small detail', r.detail) : null);
    }
    return card;
  }

  /* A "Why it failed" link to a reason card: brings it into view and focuses it. */
  function whyLink(id) {
    var b = DL.el('button', 'linkish small', 'Why it failed');
    b.type = 'button';
    b.addEventListener('click', function () {
      var card = document.getElementById(id);
      if (!card) return;
      card.scrollIntoView({ block: 'center' });
      card.focus();
      card.classList.add('hit');
      setTimeout(function () { card.classList.remove('hit'); }, 1600);
    });
    return b;
  }

  /* --- the steps table (FR-018a) ----------------------------------------------------------------- */

  function resultCell(r) {
    if (r.ok) return DL.el('span', 'res ok', 'ok');
    var span = DL.el('span', 'res bad', r.label);
    if (r.detail) { span.dataset.tip = r.detail; span.tabIndex = 0; }
    return span;
  }

  function stepsTable(d) {
    if (!d.steps.length) return DL.el('p', 'muted', 'No Claude call was recorded for this trial.');
    var all = rows(d.steps, d.started_at), last = null;
    all.forEach(function (r) { if (r.type === 'call' && r.call.failure_class && r.call.failure_class !== 'none') last = r.call; });
    var hint = d.reason ? { reason: d.reason, detail: d.detail } : null;
    var trs = all.map(function (r) {
      if (r.type === 'total') {
        var t = r.totals;
        return DL.add(DL.el('tr', 'total'), DL.td(DL.el('strong', null, 'Total')), DL.td(DL.fmt.plural(t.calls, 'call'), 'small'),
          DL.td(''), DL.td(''), DL.td(DL.conversation.ms(t.duration_ms) || '–', 'num'),
          DL.td(DL.fmt.money(t.cost), 'num'), DL.td(DL.tokens(t), 'num'), DL.td(''));
      }
      var c = r.call;
      var tr = DL.add(DL.el('tr', 'call-row'), DL.td(r.step), DL.td(DL.link(c.route, '#' + c.seq), 'num'),
        DL.td(c.model || '–', 'small'), DL.td(r.at == null ? '–' : DL.conversation.since(r.at), 'num'),
        DL.td(c.duration_ms == null ? '–' : DL.conversation.ms(c.duration_ms), 'num'),
        DL.td(DL.fmt.money(c.totals.cost), 'num'), DL.td(DL.tokens(c.totals), 'num'),
        DL.td([resultCell(result(c, c === last ? hint : null)),
               c.conversation === 'copied' ? null : DL.el('span', 'muted small', ' · conversation ' + c.conversation)]));
      return DL.rowLink(tr, c.route);
    });
    return DL.table([['Step'], ['Call', 1], ['Model'], ['Start', 1], ['Duration', 1], ['Cost', 1], ['Tokens', 1], ['Result']],
      trs, { cls: 'steps-table' });
  }

  /* --- validation: criteria and the Checks table (FR-018c, FR-019) --------------------------------- */

  function checkResult(r) {
    return r === 'not run' ? DL.el('span', 'muted small', 'not run') : DL.pill(r, 'trial');
  }

  /* "N failure lines" of the unit-test log, by the conversation view's rule (FR-021c). The count
     is kept per log and size, so a refresh does not read the log again. */
  var failureCounts = {};
  function failureMark(logRef) {
    var span = DL.el('span', 'small muted');
    if (!logRef || logRef.missing) return span;
    var key = logRef.id + ':' + logRef.size;
    if (!failureCounts[key]) {
      failureCounts[key] = DL.api.file(logRef).then(function (f) {
        return f.text != null ? DL.actions.failureLines(f.text).length : 0;
      });
      failureCounts[key].catch(function () { delete failureCounts[key]; });
    }
    failureCounts[key].then(function (n) {
      if (n) { span.className = 'flag bad'; span.textContent = n + (n === 1 ? ' failure line' : ' failure lines'); }
    }, function () {});
    return span;
  }

  function checksTable(d, why) {
    var trs = checks(d.validation).map(function (c) {
      var refs = c.evidence.map(function (p) { return ref(d, p); });
      var detail = [DL.el('div', 'small', c.detail)];
      if (c.command) detail.unshift(DL.add(DL.el('div'), code(c.command)));
      if (c.kind === 'check' || c.kind === 'boundary') detail.push(list((c.failures || []).map(c.kind === 'boundary' ? code : String), 'small'));
      if (c.kind === 'contract') detail.push(list((c.operations || []).map(code), 'small'));
      if (c.kind === 'unit-tests' && c.log) detail.push(failureMark(ref(d, c.log)));
      var target = c.result === 'failed' ? whyId(c.kind === 'check' ? 'check' : c.kind, c.kind === 'check' ? c.id : 'x') : null;
      return DL.add(DL.el('tr', c.result === 'failed' ? 'bad-row' : null),
        DL.td(DL.el('strong', null, c.id)), DL.td([checkResult(c.result), target && why[target] ? [' ', whyLink(target)] : null]),
        DL.td(detail), DL.td(evidence(refs)));
    });
    return trs.length ? DL.table([['Check'], ['Result'], ['Detail'], ['Evidence']], trs, { cls: 'checks-table' }) : null;
  }

  function validation(d, refs, why) {
    var v = d.validation;
    if (!v) return [DL.el('p', 'muted', d.status === 'in-progress' ? 'Not validated yet.' : 'No validation result was recorded for this trial.')];
    var out = [DL.add(DL.el('p'), DL.pill(v.passed ? 'passed' : 'failed', 'trial'), ' ' + v.kind + ' validation',
      v.ui_url ? DL.add(DL.el('span', 'muted small'), ' of ', code(v.ui_url)) : null)];
    var criteria = (v.criteria || []).map(function (c) {
      var target = whyId('criterion', c.criterion_id);
      return DL.add(DL.el('tr', c.passed ? null : 'bad-row'), DL.td(DL.add(DL.el('strong'), DL.ref(c.criterion_id, refs))),
        DL.td([DL.pill(c.passed ? 'passed' : 'failed', 'trial'), !c.passed && why[target] ? [' ', whyLink(target)] : null]),
        DL.td(c.observed || '', 'small'), DL.td(evidence((c.evidence || []).map(function (e) { return ref(d, e); }))));
    });
    if (criteria.length) out.push(DL.el('h4', null, 'Criteria'), DL.table([['Criterion'], ['Result'], ['Observed'], ['Evidence']], criteria, { cls: 'criteria' }));
    var table = checksTable(d, why);
    if (table) out.push(DL.el('h4', null, 'Checks'), table);
    return out;
  }

  /* --- the trial's folder (FR-018b) -------------------------------------------------------------- */

  function folder(d) {
    if (!d.evidence.length) {
      return DL.el('p', 'muted', d.key.indexOf('.') >= 0 ? 'This attempt was voided and run again under the same number: the folder holds the later attempt’s files.' : 'No file.');
    }
    var first = d.evidence[0].path, mark = '/trials/' + d.n, at = first.indexOf(mark + '/');
    var root = at >= 0 ? first.slice(0, at + mark.length) : '';
    var model = DL.tree.build(d.evidence, root), drawn = DL.tree.draw(model);
    DL.$$('details.dir', drawn.el).forEach(function (x) { x.open = true; });
    var det = DL.el('details', 'card folder-sec'), sum = DL.el('summary');
    DL.add(sum, DL.icon('folder'), ' ', DL.el('strong', null, 'Files in the trial’s folder'),
      DL.el('span', 'muted small', ' · ' + DL.fmt.plural(model.count, 'file') + ' · ' + DL.fmt.bytes(model.size)));
    det.dataset.key = 'trial-folder';
    return DL.add(det, sum, drawn.el);
  }

  /* --- files changed and the change dialog (FR-018d) ---------------------------------------------- */

  function delta(c) {
    return DL.add(DL.el('span', 'delta'), DL.el('span', 'add', '+' + c.added), ' ', DL.el('span', 'del', '−' + c.removed));
  }

  function relTo(path, target) {
    var root = String(target || '').replace(/\/+$/, '');
    return root && path.indexOf(root + '/') === 0 ? path.slice(root.length + 1) : path;
  }

  /* Every edit of the trial's calls, in the order they ran: `{path, seq, step, route, action}`. */
  function changesOf(calls, models, loop, target) {
    var out = [];
    calls.forEach(function (c) {
      var m = models[c.seq];
      if (!m) return;
      m.actions.forEach(function (a) {
        if (a.family !== 'edit' || !DL.actions.edits(a.tool, a.input).length) return;
        var i = a.input || {}, path = relTo(String(i.file_path || i.notebook_path || ''), target);
        out.push({ path: path, seq: c.seq, step: c.step, action: a,
                   route: DL.router.href('call', { loop: loop, seq: c.seq }, { at: a.rec }) });
      });
    });
    return out;
  }

  /* The viewer's items of the trial's changes: each id names its call and action, so the list can
     grow (more calls loaded) under the change shown. */
  function changeItems(changes) {
    return changes.map(function (ch) {
      return {
        id: 'change:' + ch.seq + ':' + ch.action.index, path: ch.path,
        meta: 'call #' + ch.seq + ' · ' + ch.step,
        tools: function () {
          var a = DL.link(ch.route, 'Open in the conversation', 'btn ghost');
          a.addEventListener('click', function () { DL.viewer.close(); });
          return [delta(ch.action), DL.el('span', 'spacer'), a];
        },
        panel: function () {
          return DL.add(DL.el('div', 'v-pane change-pane'),
            DL.add(DL.el('p', 'small muted'), ch.action.name + ' in call #' + ch.seq + ' (' + ch.step + ')'),
            DL.conversation.change(ch.action));
        }
      };
    });
  }

  /* Where `f` (a files_changed row) is among `changes`: its own change, else that call's last
     change of the same path; -1 when that call is not loaded. */
  function changeIndex(changes, f) {
    var k = -1;
    changes.forEach(function (ch, j) { if (ch.seq === f.seq && ch.action.rec === f.block) k = j; });
    if (k < 0) changes.forEach(function (ch, j) { if (ch.seq === f.seq && ch.path === f.path) k = j; });
    return k;
  }

  /* "Files changed" (FR-018d): the counts come with the trial. A change opens once its own call's
     conversation is read (cached by DL.api); the trial's other calls are read after it, and the
     dialog's previous and next then reach their changes too. */
  function changedTable(d, calls) {
    var box = DL.el('div');
    if (!d.files_changed.length) {
      box.appendChild(DL.el('p', 'muted', 'No file change was recorded in this trial’s conversations.'));
      return box;
    }
    var models = {}, asked = {}, all = null;
    function load(seq) {
      if (!asked[seq]) {
        asked[seq] = DL.api.get('calls/' + d.loop + '/' + seq).then(function (call) { models[seq] = DL.actions.build(call.records || []); },
          function () { models[seq] = null; });
      }
      return asked[seq];
    }
    function changes() { return changesOf(calls, models, d.loop, d.target_dir); }
    var trs = d.files_changed.map(function (f) {
      var a = DL.link(f.call_route, 'Open the change');
      a.addEventListener('click', function (ev) {
        if (ev.button || ev.metaKey || ev.ctrlKey || ev.shiftKey) return;
        ev.preventDefault();
        load(f.seq).then(function () {
          var now = changes(), k = changeIndex(now, f);
          if (k < 0) { location.hash = f.call_route; return; } /* not found: the call itself */
          var items = changeItems(now);
          DL.viewer.panel(now[k].path, null, { item: items[k], list: items, opener: a });
          all = all || Promise.all(calls.filter(function (c) { return c.conversation !== 'unavailable'; })
            .map(function (c) { return load(c.seq); }));
          all.then(function () { DL.viewer.relist(changeItems(changes())); });
        });
      });
      return DL.add(DL.el('tr'), DL.td(code(f.path)), DL.td(delta(f), 'num'), DL.td(f.step || ''), DL.td(f.tool || '', 'small'), DL.td(a));
    });
    box.appendChild(DL.table([['File'], ['Lines', 1], ['Step'], ['Tool'], ['']], trs));
    return box;
  }

  DL.trialView = { rows: rows, result: result, checks: checks, changeIndex: changeIndex };

  DL.router.register('trial', {
    title: function (params) { return params.milestone + ' · trial ' + params.key; },
    data: function (params) {
      return ['loops/' + params.loop + '/milestones/' + encodeURIComponent(params.milestone) + '/trials/' + encodeURIComponent(params.key)];
    },
    render: function (data, params, el) {
      var d = data[0], t = d.totals, refs = d.refs;
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
      var why = {};
      if (d.why.length) {
        var cards = d.why.map(function (r) { var c = reason(r, refs); if (c.id) why[c.id] = true; return c; });
        DL.add(el, DL.el('h3', null, d.status === 'void' ? 'Why it was voided' : 'Why it failed'), DL.add(DL.el('div', 'why'), cards));
      }
      var calls = [];
      d.steps.forEach(function (s) { s.calls.forEach(function (c) { calls.push(c); }); });
      DL.add(el, DL.el('h3', null, 'Steps'), stepsTable(d), DL.el('h3', null, 'Validation'), validation(d, refs, why),
        DL.el('h3', null, 'Files changed'), changedTable(d, calls),
        folder(d));
    }
  });
})(window.DL = window.DL || {});
