'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const load = require('./load.js');

const DL = load();

test('an export says what it is a snapshot of', () => {
  const ds = { exportedAt: '2026-10-10T06:20:27Z', devloopsVersion: '0.2.0', running: 'false' };
  assert.equal(DL.main.snapshotLabel(ds), 'Snapshot · 2026-10-10 06:20:27 UTC · devloops 0.2.0');
  ds.running = 'true';
  assert.equal(DL.main.snapshotLabel(ds), 'Snapshot · 2026-10-10 06:20:27 UTC · devloops 0.2.0 · run in progress');
  assert.equal(DL.main.NOTICE, 'Contains full Claude Code conversations — review before sharing');
});
