'use strict';
/* views/conversation.js: its pure formatting (the model it draws is tested in actions.test.js). */
const test = require('node:test');
const assert = require('node:assert/strict');
const load = require('./load.js');

const DL = load();
const c = DL.conversation;

test('ms: a duration, with a tenth of a second under ten seconds', () => {
  assert.equal(c.ms(null), '');
  assert.equal(c.ms(0), '0.0s');
  assert.equal(c.ms(1840), '1.8s');
  assert.equal(c.ms(72000), '1m 12s');
});

test('since: the time since the call started', () => {
  assert.equal(c.since(null), '');
  assert.equal(c.since(0), '+0:00');
  assert.equal(c.since(7400), '+0:07');
  assert.equal(c.since(65000), '+1:05');
  assert.equal(c.since(-5), '+0:00');
});
