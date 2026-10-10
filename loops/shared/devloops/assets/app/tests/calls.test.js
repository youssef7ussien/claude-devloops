/* The Claude calls view's step filter and the chip filter it uses (core.js DL.filterMatch). */
'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const load = require('./load.js');
const { plain } = load;

const DL = load();

test('filterMatch: the text and every chosen value must match; an unchosen group passes', () => {
  const row = { loop: 'backend-dev', step: 'fix' };
  const get = (attr) => row[attr];
  assert.equal(DL.filterMatch('fix M01', get, '', { loop: null, step: null }), true);
  assert.equal(DL.filterMatch('fix M01', get, '', { loop: 'backend-dev', step: 'fix' }), true);
  assert.equal(DL.filterMatch('fix M01', get, '', { loop: 'backend-dev', step: 'implement' }), false);
  assert.equal(DL.filterMatch('fix M01', get, '', { loop: 'frontend-dev', step: null }), false);
  assert.equal(DL.filterMatch('fix M01', get, 'm01', {}), true);
  assert.equal(DL.filterMatch('fix M01', get, 'm02', { loop: 'backend-dev' }), false);
});

test('steps: the steps with calls, in the server\'s order, then others by name', () => {
  const order = ['plan', 'replan', 'implement', 'fix', 'author-checks', 'validate-ui'];
  const calls = ['fix', 'implement', 'zeta', 'plan', 'validate-ui', 'fix', 'alpha', 'author-checks']
    .map((step) => ({ step }));
  assert.deepEqual(plain(DL.callsView.steps(calls, order)),
    ['plan', 'implement', 'fix', 'author-checks', 'validate-ui', 'alpha', 'zeta']);
  assert.deepEqual(plain(DL.callsView.steps(calls)),
    ['alpha', 'author-checks', 'fix', 'implement', 'plan', 'validate-ui', 'zeta']);
  assert.deepEqual(plain(DL.callsView.steps([], order)), []);
  /* a call recorded without a step is "?", as the loop view's Steps card names it */
  assert.deepEqual(plain(DL.callsView.steps([{ step: null }, { step: 'fix' }], order)), ['fix', '?']);
});

test('the Steps card links a step to its loop\'s calls of that step', () => {
  assert.equal(DL.router.href('calls', null, { loop: 'backend-dev', step: 'fix' }), '#/calls?loop=backend-dev&step=fix');
});
