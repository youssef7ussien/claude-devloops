'use strict';
const test = require('node:test');
const assert = require('node:assert');
const load = require('./load.js');

const DL = load();

test('bars: nothing to draw', () => {
  assert.strictEqual(DL.charts._layoutBars([]), null);
  assert.strictEqual(DL.charts._layoutBars([{ label: 'a', value: 0 }, { label: 'b', value: null }]), null);
});

test('bars: scaled to the peak, with a minimum width', () => {
  const lay = DL.charts._layoutBars([
    { label: 'a', value: 10, tip: 'A' }, { label: 'b', value: 5, tip: 'B' },
    { label: 'c', value: 0.01, tip: 'C' }, { label: 'skip', value: null }]);
  assert.strictEqual(lay.peak, 10);
  assert.strictEqual(lay.width, 170 + 250 + 64);
  assert.strictEqual(lay.height, 28 * 3 + 8);
  assert.deepStrictEqual(load.plain(lay.rows.map((r) => [r.label, r.y, r.w, r.valueX])),
    [['a', 4, 250, 426], ['b', 32, 125, 301], ['c', 60, 8, 184]]);
  assert.strictEqual(lay.rows[0].d, 'M170,10 h246 a4,4 0 0 1 4,4 v8 a4,4 0 0 1 -4,4 h-246 z');
  assert.strictEqual(lay.rows[0].textY, 4 + 14 + 4);
});

test('timeline: nothing started', () => {
  assert.strictEqual(DL.charts._layoutTimeline([{ label: 'x', trials: [{ status: 'passed' }] }]), null);
  assert.strictEqual(DL.charts._layoutTimeline([]), null);
});

test('timeline: positions in time, grid, tips and routes', () => {
  const lay = DL.charts._layoutTimeline([
    { label: 'backend-dev · Planning', trials: [
      { status: 'passed', label: 'Planning trial 1 (plan)', started_at: '2026-01-01T00:00:00Z',
        ended_at: '2026-01-01T00:01:00Z' }] },
    { label: 'backend-dev · M01', trials: [
      { status: 'failed', label: 'M01 trial 1 (implement)', reason: 'criteria-failed',
        started_at: '2026-01-01T00:01:00Z', ended_at: '2026-01-01T00:03:00Z', route: '#/loop/backend-dev/m/M01/t/1' },
      { status: 'in-progress', label: 'M01 trial 2 (fix)', started_at: '2026-01-01T00:04:00Z' }] }]);
  assert.strictEqual(lay.total, 240);
  assert.strictEqual(lay.height, 30 * 2 + 30);
  assert.deepStrictEqual(load.plain(lay.grid.map((g) => g.label)), ['+0s', '+1m 00s', '+2m 00s', '+3m 00s', '+4m 00s']);
  assert.strictEqual(lay.grid[4].x, 190 + 900);
  const [plan, m01] = lay.rows;
  assert.deepStrictEqual(load.plain(plan.segs[0]), {
    x: 190, y: 9, w: 223, h: 18, tone: 'good', route: null,
    tip: 'Planning trial 1 (plan) — ✓ Passed · 1m 00s' });
  assert.strictEqual(m01.segs[0].x, 190 + 225);
  assert.strictEqual(m01.segs[0].tone, 'critical');
  assert.strictEqual(m01.segs[0].route, '#/loop/backend-dev/m/M01/t/1');
  assert.strictEqual(m01.segs[0].tip, 'M01 trial 1 (implement) — ✕ Failed: criteria-failed · 2m 00s');
  // A trial still running has no end: a minimum-width mark, and no duration.
  assert.strictEqual(m01.segs[1].w, 6);
  assert.strictEqual(m01.segs[1].tip, 'M01 trial 2 (fix) — ◷ In progress · –');
});
