'use strict';
/* DL.trialView (views/trial.js): the steps table's rows and each call's result (FR-018a), and the Checks
   table (FR-018c). The trials are made up and name no application (constitution II). */
const test = require('node:test');
const assert = require('node:assert/strict');
const load = require('./load.js');
const { plain } = load;

const DL = load();
const V = DL.trialView;

const T = (s) => new Date(Date.UTC(2026, 0, 1, 0, 0, s)).toISOString();
const tot = (cost, input, partial) => ({ calls: 1, cost, partial: !!partial,
  tokens: { input, output: 1, cache_creation: 0, cache_read: 0, total: input + 1 } });
const call = (seq, start, ms, cost) => ({ seq, started_at: start == null ? null : T(start), duration_ms: ms,
  totals: tot(cost || 0, 10) });

test('rows: one row per call in the order they ran, its start since the trial, and a total', () => {
  const steps = [{ step: 'implement', calls: [call(2, 5, 2000, 0.25), call(1, 0, 1000, 0.5)] },
                 { step: 'fix', calls: [Object.assign(call(3, 10, 500, 1), { totals: tot(1, 30, true) }), call(4, null, null)] }];
  const r = plain(V.rows(steps, T(0)));
  assert.deepEqual(r.map((x) => x.type), ['call', 'call', 'call', 'call', 'total']);
  assert.deepEqual(r.slice(0, 4).map((x) => [x.step, x.call.seq, x.at]),
    [['implement', 1, 0], ['implement', 2, 5000], ['fix', 3, 10000], ['fix', 4, null]]);
  const total = r[4].totals;
  assert.equal(total.calls, 4);
  assert.equal(total.cost, 1.75);
  assert.equal(total.duration_ms, 3500);
  assert.equal(total.tokens.input, 60);
  assert.equal(total.partial, true);
  assert.equal(plain(V.rows(steps))[0].at, null); /* no trial start */
  assert.deepEqual(plain(V.rows([])), [{ type: 'total', totals: { calls: 0, cost: 0, duration_ms: null, partial: false,
    tokens: { input: 0, output: 0, cache_creation: 0, cache_read: 0, total: 0 } } }]);
});

test('result: ok, or the failure with its detail', () => {
  const R = (c, hint) => plain(V.result(c, hint));
  assert.deepEqual(R({ failure_class: 'none' }), { ok: true });
  assert.deepEqual(R({}), { ok: true }); /* a record from before failure_class */
  assert.deepEqual(R({ failure_class: 'work', timed_out: true }), { ok: false, label: 'timeout', detail: null });
  assert.deepEqual(R({ failure_class: 'work' }, { reason: 'timeout', detail: 'no result within 1800 s' }),
    { ok: false, label: 'timeout', detail: 'no result within 1800 s' });
  assert.deepEqual(R({ failure_class: 'work' }, { reason: 'invalid-output', detail: '$.tasks: missing' }),
    { ok: false, label: 'invalid output', detail: '$.tasks: missing' });
  assert.deepEqual(R({ failure_class: 'work' }, { reason: 'claude-error', detail: 'exit code 1' }),
    { ok: false, label: 'Claude error', detail: 'exit code 1' });
  assert.deepEqual(R({ failure_class: 'work', is_error: true, subtype: 'error_max_turns' }),
    { ok: false, label: 'Claude error', detail: 'subtype=error_max_turns' });
  assert.deepEqual(R({ failure_class: 'work', is_error: false, subtype: 'success' }),
    { ok: false, label: 'invalid output', detail: 'subtype=success' });
  assert.deepEqual(R({ failure_class: 'service' }, { reason: 'rate-limited', detail: 'api_error_status=429' }),
    { ok: false, label: 'service error', detail: 'rate-limited: api_error_status=429' });
  assert.deepEqual(R({ failure_class: 'service', api_error_status: 503 }),
    { ok: false, label: 'service error', detail: 'api_error_status=503' });
  assert.deepEqual(R({ failure_class: 'work' }, { reason: 'interrupted', detail: 'stopped by the developer' }),
    { ok: false, label: 'interrupted', detail: 'stopped by the developer' });
  assert.deepEqual(R({ failure_class: 'work' }), { ok: false, label: 'failed', detail: null });
});

test('checks: HTTP checks, contract, unit tests, boundary, in that order', () => {
  const v = {
    checks: [{ check_id: 'c1', passed: false, command: 'curl -s /items', response: { status: 500, body_path: 'evidence/c1.body' },
               failures: ['status 500, expected 200'] },
             { check_id: 'c2', passed: true, command: 'curl -s /health', response: { status: 200 }, failures: [] }],
    contract: { passed: false, unmatched_operations: ['POST /x'] },
    unit_tests: { enabled: true, command: 'pytest', exit_code: 1, log_path: 'unit-tests.log' },
    boundary: { passed: false, violations: ['../outside.txt'] } };
  const r = plain(V.checks(v));
  assert.deepEqual(r.map((x) => [x.kind, x.id, x.result]), [
    ['check', 'c1', 'failed'], ['check', 'c2', 'passed'], ['contract', 'API contract', 'failed'],
    ['unit-tests', 'Unit tests', 'failed'], ['boundary', 'Boundary', 'failed']]);
  assert.deepEqual(r[0].evidence, ['evidence/c1.body']);
  assert.equal(r[0].status, 500);
  assert.deepEqual(r[0].failures, ['status 500, expected 200']);
  assert.match(r[2].detail, /1 operation not in the API document/);
  assert.equal(r[3].log, 'unit-tests.log');
  assert.equal(r[3].detail, 'exit code 1');
  assert.deepEqual(r[4].failures, ['../outside.txt']);
});

test('checks: unit tests not enabled are "not run"; a met contract and a kept boundary pass', () => {
  const r = plain(V.checks({ contract: { passed: true, unmatched_operations: [] }, unit_tests: { enabled: false },
                             boundary: { passed: true, violations: [] } }));
  assert.deepEqual(r.map((x) => x.result), ['passed', 'not run', 'passed']);
  assert.deepEqual(plain(V.checks(null)), []);
});

test('changeIndex: a row opens its own change, else its call\'s change of that exact path', () => {
  const ch = (seq, rec, path) => ({ seq, path, action: { rec } });
  const changes = [ch(1, 4, 'src/a.js'), ch(1, 9, 'a.js'), ch(2, 3, 'src/a.js')];
  assert.equal(V.changeIndex(changes, { seq: 1, block: 9, path: 'a.js' }), 1);
  assert.equal(V.changeIndex(changes, { seq: 2, block: 7, path: 'src/a.js' }), 2, 'not its block: the same path');
  assert.equal(V.changeIndex(changes, { seq: 2, block: 7, path: 'a.js' }), -1, 'never another file with that ending');
  assert.equal(V.changeIndex(changes, { seq: 3, block: 1, path: 'a.js' }), -1, 'a call not loaded');
});
