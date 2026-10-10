'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const load = require('./load.js');
const { plain } = load;

const DL = load();
const f = DL.fmt;

test('money as dashboard.py money()', () => {
  assert.equal(f.money(null), '–');
  assert.equal(f.money(0), '$0.00');
  assert.equal(f.money(1234.5), '$1,234.50');
  assert.equal(f.money(0.005), '$0.01');
  assert.equal(f.money(2.999), '$3.00');
});

test('number and tokens as dashboard.py number()', () => {
  assert.equal(f.number(null), '–');
  assert.equal(f.number(999), '999');
  assert.equal(f.number(1000), '1.0k');
  assert.equal(f.tokens(12345), '12.3k');
  assert.equal(f.number(2500000), '2.5M');
  assert.equal(f.number(3e9), '3.0B');
});

test('duration as dashboard.py duration()', () => {
  assert.equal(f.duration(null), '–');
  assert.equal(f.duration(59.4), '59s');
  assert.equal(f.duration(61), '1m 01s');
  assert.equal(f.duration(3600 + 120), '1h 02m');
});

test('percent, time, bytes, plural', () => {
  assert.equal(f.percent(null), '–');
  assert.equal(f.percent(0.426), '43%');
  assert.equal(f.time('2026-10-09T12:34:56.789Z'), '2026-10-09 12:34:56 UTC');
  assert.equal(f.time('nonsense'), 'nonsense');
  assert.equal(f.bytes(512), '512 bytes');
  assert.equal(f.bytes(2048), '2.0 KB');
  assert.equal(f.bytes(5 * 1024 * 1024), '5.0 MB');
  assert.equal(f.plural(1, 'call'), '1 call');
  assert.equal(f.plural(2, 'call'), '2 calls');
});

test('status tables carry a label, an icon, and a tone', () => {
  assert.deepEqual(load.plain(DL.status('completed', 'run')), ['Completed', '✓', 'good']);
  assert.deepEqual(load.plain(DL.status('weird', 'run')), ['weird', '•', 'muted']);
});

test('tokens spelled out', () => {
  assert.equal(DL.fmt.tokenParts({ input: 1200, output: 300, cache_creation: 5000, cache_read: 20000 }),
    'input 1.2k · output 300 · cache write 5.0k · cache read 20.0k');
  assert.equal(DL.fmt.tokenParts(null), 'input 0 · output 0 · cache write 0 · cache read 0');
});

test('a totals cell: the total, its parts, and partial', () => {
  const t = { tokens: { input: 1200, output: 300, cache_creation: 5000, cache_read: 20000, total: 26500 }, partial: false };
  assert.deepEqual(plain(DL.fmt.totalsCell(t)), {
    text: '26.5k', partial: false, tip: 'input 1.2k · output 300 · cache write 5.0k · cache read 20.0k'
  });
  const p = DL.fmt.totalsCell(Object.assign({}, t, { partial: true }));
  assert.equal(p.partial, true);
  assert.match(p.tip, /· partial: some calls did not record usage$/);
  assert.deepEqual(plain(DL.fmt.totalsCell(null)), {
    text: '0', partial: false, tip: 'input 0 · output 0 · cache write 0 · cache read 0'
  });
});

test('the now panel lists the last 20 tools, or all', () => {
  const tools = Array.from({ length: 25 }, (_, i) => ({ name: 'T' + i }));
  assert.deepEqual(plain(DL.now.visible(tools, false)).map((t) => t.name), tools.slice(5).map((t) => t.name));
  assert.equal(DL.now.visible(tools, true).length, 25);
  assert.equal(DL.now.visible(tools.slice(0, 3), false).length, 3);
  assert.equal(DL.now.visible(null, false).length, 0);
});

test('refTip: what a plan id says, or null (FR-020d)', () => {
  const DL = load();
  const refs = { 'FR-1': 'List items', 'M01-T01': 'GET /items', 'M01-AC1': 'GET /items returns 200' };
  assert.equal(DL.refTip('FR-1', refs), 'List items');
  assert.equal(DL.refTip('M01-AC1', refs), 'GET /items returns 200');
  assert.equal(DL.refTip('FR-9', refs), null);
  assert.equal(DL.refTip('FR-1', undefined), null);
  assert.equal(DL.refTip('toString', refs), null);
});
