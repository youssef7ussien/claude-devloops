'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const load = require('./load.js');

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
