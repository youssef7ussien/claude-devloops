/* Syntax highlighting helpers (highlight.js). */
'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const load = require('./load.js');

const DL = load();

test('tokenize marks keys, strings, and numbers in JSON', () => {
  const tokens = load.plain(DL.hl.tokenize('{"a": "b", "n": 1}', 'json'));
  assert.deepEqual(tokens.filter((t) => t[0] && t[0] !== 'pun'),
    [['key', '"a"'], ['str', '"b"'], ['key', '"n"'], ['num', '1']]);
  assert.equal(tokens.map((t) => t[1]).join(''), '{"a": "b", "n": 1}');
});

test('tokenize keeps the text of an unknown language whole', () => {
  assert.deepEqual(load.plain(DL.hl.tokenize('plain', 'nope')), [[null, 'plain']]);
});

test('python keywords and comments', () => {
  const tokens = load.plain(DL.hl.tokenize('def f():  # hi', 'python'));
  assert.deepEqual(tokens.filter((t) => t[0]), [['kw', 'def'], ['com', '# hi']]);
});

test('langOf maps fence names', () => {
  assert.equal(DL.hl.langOf('PY'), 'python');
  assert.equal(DL.hl.langOf('bash'), 'shell');
  assert.equal(DL.hl.langOf('rust'), 'text');
  assert.equal(DL.hl.langOf(''), 'text');
});

test('pretty indents JSON objects only', () => {
  assert.equal(DL.hl.pretty('{"a":1}'), '{\n  "a": 1\n}');
  assert.equal(DL.hl.pretty('42'), '42');
  assert.equal(DL.hl.pretty('not json'), 'not json');
});
