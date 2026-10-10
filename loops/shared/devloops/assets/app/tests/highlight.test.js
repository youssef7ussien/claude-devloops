/* Syntax highlighting helpers (highlight.js): code through Prism's tokens (FR-033, R-16). */
'use strict';
const fs = require('fs');
const path = require('path');
const test = require('node:test');
const assert = require('node:assert/strict');
const load = require('./load.js');

const DL = load();
/* The app as exported: the listed scripts without vendor/ (no Prism). */
const listed = fs.readFileSync(path.join(__dirname, '..', 'scripts.txt'), 'utf8').split('\n')
  .map((line) => line.split('#')[0].trim()).filter(Boolean);
const BARE = load(listed.filter((name) => !name.startsWith('vendor/')));
const SAMPLES = {
  js: 'const s = `a${b}` // note\nfunction f(x) { return 1; }',
  jsx: 'const x = <div className="a">{f(1)}</div>;',
  python: 'def f():  # hi\n    return "s"',
  csharp: 'public class A { int x = 1; }',
  sql: "SELECT name FROM t WHERE id = 1 -- one",
};

test('tokenize marks keys, strings, and numbers in JSON', () => {
  const tokens = load.plain(DL.hl.tokenize('{"a": "b", "n": 1}', 'json'));
  assert.deepEqual(tokens.filter((t) => t[0] && t[0] !== 'pun'),
    [['key', '"a"'], ['str', '"b"'], ['key', '"n"'], ['num', '1']]);
  assert.equal(tokens.map((t) => t[1]).join(''), '{"a": "b", "n": 1}');
});

test('tokenize keeps the text of an unknown language whole', () => {
  assert.deepEqual(load.plain(DL.hl.tokenize('plain', 'nope')), [[null, 'plain']]);
});

test('python keywords, names, and comments', () => {
  const tokens = load.plain(DL.hl.tokenize('def f():  # hi', 'python'));
  assert.deepEqual(tokens.filter((t) => t[0] && t[0] !== 'pun'), [['kw', 'def'], ['fn', 'f'], ['com', '# hi']]);
});

test('with Prism, code is typed tokens whose texts join to the input', () => {
  for (const [lang, text] of Object.entries(SAMPLES)) {
    const tokens = load.plain(DL.hl.tokenize(text, lang));
    assert.equal(tokens.map((t) => t[1]).join(''), text, lang);
    assert.ok(tokens.some((t) => t[0] === 'kw'), lang);
    assert.ok(tokens.length > 3, lang);
  }
  const jsx = load.plain(DL.hl.tokenize(SAMPLES.jsx, 'jsx'));
  assert.ok(jsx.some((t) => t[0] === 'str' && t[1] === 'a'));
  const js = load.plain(DL.hl.tokenize(SAMPLES.js, 'js'));
  assert.ok(js.some((t) => t[0] === 'com' && t[1] === '// note'));
  assert.ok(js.some((t) => t[0] === null && t[1] === 'b'), 'code inside a template string is plain');
});

test('without Prism (the export), code is one plain token; logs and HTTP keep their rules', () => {
  for (const [lang, text] of Object.entries(SAMPLES)) {
    assert.deepEqual(load.plain(BARE.hl.tokenize(text, lang)), [[null, text]], lang);
  }
  assert.deepEqual(load.plain(BARE.hl.tokenize('ERROR at x', 'log'))[0], ['err', 'ERROR']);
  assert.deepEqual(load.plain(BARE.hl.tokenize('HTTP/1.1 200 OK', 'http')), [['head', 'HTTP/1.1 200 OK']]);
  assert.deepEqual(load.plain(BARE.hl.tokenize('+a\n-b', 'diff')), [['str', '+a'], [null, '\n'], ['lit', '-b']]);
});

test('langOf maps fence names and file extensions', () => {
  const cases = { PY: 'python', bash: 'shell', js: 'js', mjs: 'js', cjs: 'js', jsx: 'jsx', ts: 'ts',
    tsx: 'tsx', cs: 'csharp', csharp: 'csharp', go: 'go', java: 'java', sql: 'sql', yml: 'yaml',
    xml: 'html', md: 'markdown', json: 'json', log: 'log', http: 'http', rust: 'text', '': 'text' };
  for (const [name, lang] of Object.entries(cases)) assert.equal(DL.hl.langOf(name), lang, name);
});

test('pretty indents JSON objects only', () => {
  assert.equal(DL.hl.pretty('{"a":1}'), '{\n  "a": 1\n}');
  assert.equal(DL.hl.pretty('42'), '42');
  assert.equal(DL.hl.pretty('not json'), 'not json');
});
