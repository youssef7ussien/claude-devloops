'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const load = require('./load.js');
const { plain } = load;

const DL = load();
const c = DL.conversation;

function use(name, input, id) {
  return { type: 'tool_use', id: id || 't1', name, input };
}

test('hint: the command, path, URL, or pattern of a tool use', () => {
  assert.equal(c.hint(use('Bash', { command: 'pytest -q\n  --tb=short', description: 'run' })), 'pytest -q --tb=short');
  assert.equal(c.hint(use('Edit', { file_path: '/t/app.py', old_string: 'a', new_string: 'b' })), '/t/app.py');
  assert.equal(c.hint(use('WebFetch', { url: 'https://x.dev/a', prompt: 'read' })), 'https://x.dev/a');
  assert.equal(c.hint(use('Grep', { pattern: 'TODO', path: 'src' })), 'TODO');
  assert.equal(c.hint(use('LS', { path: 'src' })), 'src');
  assert.equal(c.hint(use('Glob', { pattern: '**/*.py' })), '**/*.py');
  assert.equal(c.hint(use('TodoWrite', { todos: [] })), '');
  assert.equal(c.hint({ type: 'tool_use', name: 'X' }), '');
  const long = c.hint(use('Bash', { command: 'x'.repeat(500) }));
  assert.equal(long.length, 160);
  assert.ok(long.endsWith('…'));
});

test('fold: one item per message part, in order, folded as the rules say', () => {
  const many = (n) => Array.from({ length: n }, (_, k) => 'line ' + k).join('\n');
  const records = [
    { type: 'system', subtype: 'init', session_id: 's' },
    { type: 'user', message: { role: 'user', content: many(41) } },
    { type: 'assistant', message: { role: 'assistant', content: [
      { type: 'thinking', thinking: 'hmm' }, { type: 'text', text: '**Plan**' },
      use('Bash', { command: 'pytest' }, 'a'), use('Read', { file_path: 'app.py' }, 'b')] } },
    { type: 'user', message: { role: 'user', content: [
      { type: 'tool_result', tool_use_id: 'a', is_error: true, content: many(30) },
      { type: 'tool_result', tool_use_id: 'b', content: [{ type: 'text', text: many(13) }] }] } },
    { type: 'user', message: { role: 'user', content: 'short' } },
    { raw: 'not json' },
    { type: 'result', subtype: 'success' }
  ];
  const items = plain(c.fold(records));
  assert.deepEqual(items.map((it) => [it.rec, it.kind, it.folded]), [
    [0, 'system', true],
    [1, 'user', true],
    [2, 'thinking', true], [2, 'claude', false], [2, 'tool', true], [2, 'tool', true],
    [3, 'result', false], [3, 'result', true],
    [4, 'user', false],
    [5, 'system', true],
    [6, 'system', true]
  ]);
  assert.deepEqual([items[4].name, items[4].hint], ['Bash', 'pytest']);
  assert.deepEqual([items[6].tool, items[6].error], ['Bash', true]);
  assert.deepEqual([items[7].tool, items[7].error], ['Read', false]);
  assert.equal(items[7].text, many(13));
  assert.equal(items[3].text, '**Plan**');
  assert.equal(items[9].text, 'not json');
  assert.equal(items[10].type, 'result');
  // a result of 12 lines is not folded; 13 is
  const r = plain(c.fold([{ type: 'user', message: { role: 'user', content: [
    { type: 'tool_result', tool_use_id: 'z', content: many(12) }] } }]));
  assert.equal(r[0].folded, false);
  assert.equal(r[0].tool, null);
  assert.deepEqual(plain(c.fold([])), []);
});
