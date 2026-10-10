'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const load = require('./load.js');
const { plain } = load;

const DL = load();
const lv = DL.loopView;

function milestone(id, status, depends_on) {
  return { id, title: 'Title ' + id, status, depends_on: depends_on || [] };
}

test('progress: achieved of all milestones', () => {
  assert.deepEqual(plain(lv.progress([milestone('M01', 'achieved'), milestone('M02', 'failed'),
    milestone('M03', 'pending')])), { achieved: 1, total: 3 });
  assert.deepEqual(plain(lv.progress([])), { achieved: 0, total: 0 });
});

const ref = (name, kind) => ({ id: 'f-' + name, path: 'M01/trials/1/evidence/' + name, kind: kind || 'text' });

test('evidenceGroups: files grouped by the name before the first dot, in first-seen order', () => {
  const refs = [ref('C1.body'), ref('C1.headers'), ref('C2.body'), ref('dashboard.png', 'image'), ref('notes'),
    ref('C1.command')];
  const groups = plain(lv.evidenceGroups(refs));
  assert.deepEqual(groups.map((g) => [g.check, g.files.map((f) => f.label)]),
    [['C1', ['body', 'headers', 'command']], ['C2', ['body']], ['dashboard', ['png']], ['notes', ['notes']]]);
  assert.deepEqual(groups.map((g) => g.files.map((f) => f.image)), [[false, false, false], [false], [true], [false]]);
  assert.equal(groups[0].files[0].ref.id, 'f-C1.body');
  assert.deepEqual(plain(lv.evidenceGroups(undefined)), []);
});

test('grantsOf: a milestone\'s retries granted, oldest first', () => {
  const grants = [
    { milestone_id: 'M02', extra_trials: 2, granted_at: '2026-10-07T12:00:00.000Z', reason: 'try again' },
    { milestone_id: 'M01', extra_trials: 1, granted_at: '2026-10-07T10:00:00.000Z' },
    { milestone_id: 'M02', extra_trials: 3, granted_at: '2026-10-07T11:00:00.000Z', reason: '', accepted_suggestions: ['OQ1'] },
  ];
  assert.deepEqual(plain(lv.grantsOf(grants, 'M02')), [
    { trials: 3, at: '2026-10-07T11:00:00.000Z', reason: '', accepted: 1 },
    { trials: 2, at: '2026-10-07T12:00:00.000Z', reason: 'try again', accepted: 0 }]);
  assert.deepEqual(plain(lv.grantsOf(undefined, 'M01')), []);
});

test('strayGrants: retries granted for milestones the plan no longer has', () => {
  const grants = [
    { milestone_id: 'M09', extra_trials: 1, granted_at: '2026-10-07T12:00:00Z', reason: 'old' },
    { milestone_id: 'M01', extra_trials: 2, granted_at: '2026-10-07T10:00:00Z' },
    { milestone_id: 'M07', extra_trials: 3, granted_at: '2026-10-07T11:00:00Z' }];
  assert.deepEqual(plain(lv.strayGrants(grants, [{ id: 'M01' }])), [
    { milestone: 'M07', trials: 3, at: '2026-10-07T11:00:00Z', reason: '', accepted: 0 },
    { milestone: 'M09', trials: 1, at: '2026-10-07T12:00:00Z', reason: 'old', accepted: 0 }]);
  assert.deepEqual(plain(lv.strayGrants(undefined, [])), []);
});

test('withGrants: each retry granted just before the first trial that started after it', () => {
  const t = (n, at) => ({ n, started_at: at });
  const g = (trials, at) => ({ trials, at });
  const rows = lv.withGrants([t(1, '2026-10-07T10:00:00Z'), t(2, '2026-10-07T11:00:00Z'), t(3, '2026-10-08T09:00:00Z')],
    [g(2, '2026-10-08T08:00:00Z'), g(1, '2026-10-09T00:00:00Z')]);
  assert.deepEqual(plain(rows.map((x) => x.trial ? 'T' + x.trial.n : 'G' + x.grant.trials)), ['T1', 'T2', 'G2', 'T3', 'G1']);
  assert.deepEqual(plain(lv.withGrants([], [g(1, null)])), [{ grant: { trials: 1, at: null } }]);
  assert.deepEqual(plain(lv.withGrants([t(1, null)], undefined)), [{ trial: { n: 1, started_at: null } }]);
});
