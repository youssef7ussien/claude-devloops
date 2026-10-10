'use strict';
/* DL.actions (actions.js): records → turns and actions (User Story 8, research R-15). The records
   are made up and name no application (constitution II). */
const test = require('node:test');
const assert = require('node:assert/strict');
const load = require('./load.js');
const { plain } = load;

const DL = load();
const A = DL.actions;

const T = (s) => '2026-01-01T00:00:' + String(s).padStart(2, '0') + '.000Z';
const say = (s, content, extra) => Object.assign({ type: 'assistant', timestamp: T(s), message: { role: 'assistant', content } }, extra || {});
const back = (s, content) => ({ type: 'user', timestamp: T(s), message: { role: 'user', content } });
const use = (id, name, input) => ({ type: 'tool_use', id, name, input: input || {} });
const result = (id, content, isError) => ({ type: 'tool_result', tool_use_id: id, content, is_error: !!isError });

const PAGE = (url, errors) => '### Page\n- Page URL: ' + url + '\n- Page Title: Example\n- Console: ' +
  (errors || 0) + ' errors, 1 warnings';
const RAN = (code) => '### Ran Playwright code\n```js\n' + code + '\n```';

test('build: pairs uses and results into actions, grouped under Claude\'s turns', () => {
  const records = [
    { type: 'queue-operation', timestamp: T(0) },
    back(0, 'the prompt'),
    say(1, [{ type: 'thinking', thinking: '' }], { thinkingDurationMs: 1800 }),
    say(2, [{ type: 'thinking', thinking: '' }]),
    say(3, [{ type: 'text', text: 'Let me run the tests.' }, use('a', 'Bash', { command: 'make test', description: 'Run the tests' })]),
    say(3, [use('b', 'Read', { file_path: '/t/src/app.js' })]),
    back(5, [result('a', 'Exit code 2\n1 failed', true)]),
    back(6, [result('b', '1\tline one\n2\tline two')]),
    say(9, [{ type: 'text', text: 'Now edit.' }, use('c', 'Edit', { file_path: '/t/src/app.js', old_string: 'a\nb', new_string: 'a\nc\nd' })]),
    back(9, [result('zz', 'orphan')]),
    say(10, [use('o', 'StructuredOutput', { tasks: [{ id: 'T1', status: 'implemented' }] })]),
    { raw: 'not json' }
  ];
  const m = A.build(records);
  assert.deepEqual(plain(m.prompt), { rec: 1, text: 'the prompt' });
  assert.equal(m.answer.shape, 'tasks');
  assert.equal(m.answer.rec, 10);
  assert.equal(m.turns.length, 3);
  assert.deepEqual(plain(m.turns.map((t) => [t.rec, t.text, t.elapsed_ms])),
    [[null, null, null], [4, 'Let me run the tests.', 3000], [8, 'Now edit.', 9000]]);
  assert.deepEqual(plain(m.turns[0].items), [{ kind: 'thought', rec: 2, ms: 1800, text: '' }]);
  const [a, b, c, orphan] = m.actions;
  assert.deepEqual(plain([a.name, a.family, a.summary, a.outcome, a.duration_ms, a.exit_code, a.records]),
    ['Shell', 'shell', 'Run the tests', 'error', 2000, 2, [4, 6]]);
  assert.deepEqual(plain(a.failure_lines), [1]);
  assert.deepEqual([b.name, b.summary, b.outcome, b.duration_ms, b.kind_of], ['Read', 'app.js · 2 lines', 'ok', 3000, 'read']);
  assert.deepEqual([c.summary, c.outcome, c.duration_ms, c.added, c.removed], ['app.js · +2 −1', 'unfinished', null, 2, 1]);
  assert.deepEqual([orphan.name, orphan.outcome, orphan.text], ['Result', 'ok', 'orphan']);
  assert.deepEqual(plain(m.turns[1].items.map((i) => i.index)), [0, 1]);
  assert.deepEqual(plain(m.turns[2].items), [{ kind: 'action', index: 2 }, { kind: 'action', index: 3 },
    { kind: 'system', rec: 11 }]);
  assert.deepEqual(plain(m.before), [0], 'a system record before the prompt');
  assert.deepEqual(plain(m.errors), [0]);
  assert.deepEqual(plain(m.stats), { actions: 4, families: { shell: 1, read: 1, edit: 1, other: 1 }, errors: 1,
    files: { '/t/src/app.js': { added: 2, removed: 1 } } });
  // what shows each record
  assert.deepEqual(plain([0, 1, 2, 4, 6, 8, 10, 11].map((r) => A.actionOf(m, r))), [
    { type: 'system' }, { type: 'prompt' }, { type: 'turn', index: 0 }, { type: 'action', index: 0 },
    { type: 'action', index: 0 }, { type: 'action', index: 2 }, { type: 'answer' }, { type: 'system' }]);
  assert.equal(A.actionOf(m, 99), null);
  assert.deepEqual(plain(A.build([])), { prompt: null, answer: null, before: [], turns: [{ rec: null, text: null, elapsed_ms: null, items: [] }],
    actions: [], errors: [], at: {}, stats: { actions: 0, families: {}, errors: 0, files: {} } });
});

test('build: no duration when a time is missing; thinking text is kept', () => {
  const m = A.build([
    say(1, [{ type: 'thinking', thinking: 'why' }]),
    { type: 'assistant', message: { role: 'assistant', content: [use('a', 'Glob', { pattern: '*.md' })] } },
    back(2, [result('a', 'x.md')])
  ]);
  assert.equal(m.actions[0].duration_ms, null);
  assert.deepEqual(plain(m.turns[0].items[0]), { kind: 'thought', rec: 0, ms: null, text: 'why' });
});

test('name: built-in tools, browser tools, MCP tools, and others', () => {
  const cases = {
    Bash: ['Shell', 'shell'], Read: ['Read', 'read'], Edit: ['Edit', 'edit'], MultiEdit: ['Edit', 'edit'],
    Write: ['Write', 'edit'], NotebookEdit: ['Edit notebook', 'edit'], Grep: ['Search', 'read'], Glob: ['Find files', 'read'],
    WebFetch: ['Fetch', 'web'], WebSearch: ['Web search', 'web'], TodoWrite: ['Todos', 'other'], Agent: ['Agent', 'other'],
    Task: ['Agent', 'other'], ToolSearch: ['Load tools', 'other'], StructuredOutput: ['Answer', 'other'],
    mcp__playwright__browser_click: ['Click', 'browser'], mcp__playwright__browser_take_screenshot: ['Screenshot', 'browser'],
    mcp__playwright__browser_network_requests: ['Requests', 'browser'], mcp__playwright__browser_new_thing: ['New thing', 'browser'],
    mcp__some_server__create_issue: ['Some server · Create issue', 'other'],
    mcp__docs__getPageText: ['Docs · Get page text', 'other'],
    TaskStop: ['Task stop', 'other'], '': ['?', 'other']
  };
  for (const [tool, want] of Object.entries(cases)) assert.deepEqual(plain(A.name(tool)), { name: want[0], family: want[1] }, tool);
});

test('summary: per tool, with the generic fallback', () => {
  const s = (tool, input, extra) => A.summary(Object.assign({ tool, input }, extra || {}));
  assert.equal(s('Bash', { command: 'make\n  test' }), 'make');
  assert.equal(s('Bash', { command: 'make', description: 'Build it' }), 'Build it');
  assert.equal(s('Read', { file_path: '/a/b/c.py', offset: 10, limit: 5 }), 'c.py · lines 10–14');
  assert.equal(s('Read', { file_path: '/a/c.py' }), 'c.py');
  assert.equal(s('Edit', { file_path: '/a/c.py', old_string: 'x', new_string: 'y\nz' },
    { record: { toolUseResult: { structuredPatch: [{ newStart: 28 }] } } }), 'c.py · +2 −1 at line 28');
  assert.equal(s('MultiEdit', { file_path: '/a/c.py', edits: [{ old_string: 'a', new_string: 'b' }, { old_string: '', new_string: 'n' }] }), 'c.py · +2 −1');
  assert.equal(s('Write', { file_path: '/a/c.py', content: 'a\nb\nc\n' }), 'c.py · 3 lines');
  assert.equal(s('Grep', { pattern: 'TODO', path: 'src' }), 'TODO in src');
  assert.equal(s('Grep', { pattern: 'TODO', glob: '*.js' }), 'TODO in *.js');
  assert.equal(s('Glob', { pattern: '**/*.md' }), '**/*.md');
  assert.equal(s('WebFetch', { url: 'https://example.org/a', prompt: 'read' }), 'https://example.org/a');
  assert.equal(s('WebSearch', { query: 'how to' }), 'how to');
  assert.equal(s('ToolSearch', { query: 'select:x' }), 'select:x');
  assert.equal(s('TodoWrite', { todos: [{ status: 'completed' }, { status: 'pending' }] }), '2 items, 1 done');
  assert.equal(s('Agent', { description: 'Look around', prompt: 'long' }), 'Look around');
  assert.equal(s('mcp__x__y', { count: 3, label: 'the label' }), 'the label');
  assert.equal(s('mcp__x__y', { url: 'u', description: 'first' }), 'first');
  assert.equal(s('mcp__x__y', { n: 1, m: 2 }), '2 inputs');
  assert.equal(s('mcp__x__y', {}), '');
  const long = s('Other', { text: 'y'.repeat(400) });
  assert.equal(long.length, 160);
  assert.ok(long.endsWith('…'));
});

test('summary: browser actions name their target and the page they lead to', () => {
  const b = (action, input, text, before) => A.summary({ tool: 'mcp__playwright__browser_' + action, input, text, url_before: before });
  assert.equal(b('click', { element: 'Save button' }, RAN("await page.getByRole('button', { name: 'Save' }).click();") + '\n' + PAGE('http://h/x'), 'http://h/x'),
    'button "Save"');
  assert.equal(b('click', { element: 'Save button' }, PAGE('http://h/y'), 'http://h/x'), 'Save button → /y');
  assert.equal(b('click', {}, RAN("await page.getByText('Don\\'t').click();")), 'text "Don\'t"');
  assert.equal(b('type', { text: 'hello' }, RAN("await page.getByRole('textbox', { name: 'Title' }).fill('hello');")), '"hello" into textbox "Title"');
  assert.equal(b('fill_form', { fields: [{ name: 'Due date', value: '2026-01-02' }] }, ''), 'Due date = 2026-01-02');
  assert.equal(b('fill_form', { fields: [{ name: 'a' }, { name: 'b' }] }, ''), '2 fields');
  assert.equal(b('fill_form', { fields: [null] }, ''), '1 field', 'a field that is not an object');
  assert.equal(b('navigate', { url: 'http://h/' }, PAGE('http://h/'), ''), 'http://h/');
  assert.equal(b('snapshot', {}, PAGE('http://h/tasks?x=1')), '/tasks · Example');
  assert.equal(b('take_screenshot', { fullPage: true, filename: '/w/evidence/shot.png' }, ''), 'full page → evidence/shot.png');
  assert.equal(b('evaluate', { function: '() => 1 + 1' }, '### Result\n2\n' + RAN('x')), '() => 1 + 1 → 2');
  assert.equal(b('network_requests', {}, '### Result\n1. [GET] http://h/a => [200] OK\n2. [GET] http://h/b => [200] OK'), '2 requests, all 200');
  assert.equal(b('network_requests', {}, '### Result\n1. [GET] http://h/a => [200] OK\n2. [POST] http://h/b => [404] Not Found'),
    '2 requests, statuses 200, 404');
  assert.equal(b('press_key', { key: 'Enter' }, ''), 'Enter');
  assert.equal(b('wait_for', { time: 2 }, ''), '2 s');
  assert.equal(b('new_thing', { element: 'thing' }, ''), 'thing');
  assert.equal(b('click', { target: 'e209' }, '### Error\nfailed'), 'e209');
  assert.equal(b('click', { target: "getByRole('link', { name: 'Home' })" }, ''), 'link "Home"');
});

test('browserInfo and target read a browser result', () => {
  const info = plain(A.browserInfo(RAN("await page.getByRole('link', { name: 'Home' }).click();") + '\n' + PAGE('http://h/', 2) +
    '\n### Snapshot\n- a\n- b'));
  assert.deepEqual(info, { code: "await page.getByRole('link', { name: 'Home' }).click();", url: 'http://h/', title: 'Example',
    errors: 2, warnings: 1, snapshot: '- a\n- b', result: '', error: '' });
  assert.equal(A.target("page.getByLabel('Email')"), 'field "Email"');
  assert.equal(A.target("page.getByRole('checkbox')"), 'checkbox');
  assert.equal(A.target('page.locator("x")'), '');
});

test('kind and resultParts: how a result is shown; only four image types are kept', () => {
  const png = { type: 'image', source: { type: 'base64', media_type: 'image/png', data: 'AAA' } };
  const svg = { type: 'image', source: { type: 'base64', media_type: 'image/svg+xml', data: 'BBB' } };
  assert.deepEqual(plain(A.resultParts({ content: [{ type: 'text', text: 'saw' }, png, svg] })),
    { text: 'saw\n[image: image/svg+xml, not shown]', images: [{ media_type: 'image/png', data: 'AAA' }] });
  assert.deepEqual(plain(A.resultParts({ content: 'plain' })), { text: 'plain', images: [] });
  assert.equal(A.kind('mcp__playwright__browser_take_screenshot', '', [{}]), 'image');
  assert.equal(A.kind('mcp__playwright__browser_click', 'x', []), 'browser');
  assert.equal(A.kind('Read', '1→a\n2→b', []), 'read');
  assert.equal(A.kind('Read', 'EISDIR', []), 'text');
  assert.equal(A.kind('Edit', 'updated', []), 'edit');
  assert.equal(A.kind('Write', 'created', []), 'edit');
  assert.equal(A.kind('Bash', 'out', []), 'terminal');
  assert.equal(A.kind('mcp__x__y', '## Title\ntext', []), 'markdown');
  assert.equal(A.kind('mcp__x__y', '- item', []), 'markdown');
  assert.equal(A.kind('mcp__x__y', '{"a": 1}', []), 'text');
});

test('failureLines: failure-looking lines, not zero counts', () => {
  const yes = ['✖ adds two numbers', 'not ok 3 - parses', 'FAIL src/a.test.js', 'npm ERR! code 1', 'Error: boom',
    'Traceback (most recent call last):', 'Tests: 3 failed, 4 passed', 'it failed'];
  const no = ['ℹ fail 0', '0 failed', 'failures: 0', 'no errors', 'ℹ pass 3', 'all good', '# fail 0', 'Failures = 0', '"failures": [],', '"failed": false', 'failures: none'];
  assert.deepEqual(plain(A.failureLines(yes.join('\n'))), yes.map((_, k) => k));
  assert.deepEqual(plain(A.failureLines(no.join('\n'))), []);
  assert.deepEqual(plain(A.failureLines('')), []);
});

test('diff: lines removed, added, and kept, with counts', () => {
  const d = plain(A.diff('a\nb\nc\nd', 'a\nx\nc\nd\ne'));
  assert.deepEqual(d.lines.map((l) => l.op + l.text), [' a', '-b', '+x', ' c', ' d', '+e']);
  assert.deepEqual([d.added, d.removed], [2, 1]);
  assert.deepEqual(plain(A.diff('', 'n')), { lines: [{ op: '+', text: 'n' }], added: 1, removed: 0 });
  assert.deepEqual(plain(A.diff('same', 'same')), { lines: [{ op: ' ', text: 'same' }], added: 0, removed: 0 });
});

test('build works out an edit\'s counts and a read\'s lines once, for the summary and the views', () => {
  const recs = [
    { type: 'user', message: { role: 'user', content: [{ type: 'text', text: 'go' }] } },
    { type: 'assistant', message: { role: 'assistant', content: [
      { type: 'tool_use', id: 'e', name: 'Edit', input: { file_path: '/t/a.py', old_string: 'a\nb', new_string: 'a\nc\nd' } },
      { type: 'tool_use', id: 'r', name: 'Read', input: { file_path: '/t/b.py' } }] } },
    { type: 'user', message: { role: 'user', content: [
      { type: 'tool_result', tool_use_id: 'e', content: 'ok' },
      { type: 'tool_result', tool_use_id: 'r', content: '     1→x\n     2→y' }] } }];
  const [edit, read] = A.build(recs).actions;
  assert.deepEqual([edit.added, edit.removed, edit.summary], [2, 1, 'a.py · +2 −1']);
  assert.deepEqual([read.kind_of, read.summary, plain(read.read_lines).length], ['read', 'b.py · 2 lines', 2]);
  assert.equal(edit.read_lines, null);
  /* the summary uses the counts it is given */
  assert.equal(A.summary({ tool: 'Edit', input: { file_path: 'x.py' }, added: 7, removed: 3 }), 'x.py · +7 −3');
});

test('readLines and clip', () => {
  assert.deepEqual(plain(A.readLines('     1→first\n     2→\tsecond\n\n<note>')),
    [{ n: 1, text: 'first' }, { n: 2, text: '\tsecond' }, { n: null, text: '' }, { n: null, text: '<note>' }]);
  assert.deepEqual(plain(A.readLines('10\tten\n11\televen')), [{ n: 10, text: 'ten' }, { n: 11, text: 'eleven' }]);
  assert.equal(A.readLines('no numbers'), null);
  const ls = Array.from({ length: 41 }, (_, k) => 'l' + k);
  const c = plain(A.clip(ls));
  assert.deepEqual([c.head.length, c.tail.length, c.hidden, c.head[0], c.tail[9]], [15, 10, 16, 'l0', 'l40']);
  assert.deepEqual(plain(A.clip(ls.slice(0, 40))), { head: ls.slice(0, 40), tail: [], hidden: 0 });
});

test('answer: the last StructuredOutput, with its shape', () => {
  const so = (input) => say(1, [use('s', 'StructuredOutput', input)]);
  assert.equal(A.answer([so({ tasks: [] }), so({ criteria: [{ id: 'C1', passed: true }] })]).shape, 'criteria');
  assert.equal(A.answer([so({ tasks: [{ id: 'T1' }] })]).shape, 'tasks');
  assert.equal(A.answer([so({ verdict: 'ok' })]).shape, 'other');
  assert.equal(A.answer([say(1, [{ type: 'text', text: 'hi' }])]), null);
  assert.equal(A.answer([]), null);
});

test('build: a browser row flags only the console errors it added', () => {
  const click = (id) => use(id, 'mcp__playwright__browser_click', { element: 'x' });
  const m = A.build([
    say(1, [click('a'), click('b'), click('c'), click('d')]),
    back(2, [result('a', PAGE('http://h/', 2)), result('b', PAGE('http://h/', 2)), result('c', PAGE('http://h/', 3)),
      result('d', PAGE('http://h/other', 1))])
  ]);
  assert.deepEqual(plain(m.actions.map((a) => a.console_new)), [2, 0, 1, 1]);
});

test('known: tools with rules of their own', () => {
  assert.equal(A.known('Bash'), true);
  assert.equal(A.known('mcp__playwright__browser_click'), true);
  assert.equal(A.known('mcp__x__y'), false);
  assert.equal(A.known('toString'), false);
});

test('build: a system record shows where it happened, between the actions around it', () => {
  const m = A.build([
    back(0, 'the prompt'),
    say(1, [use('a', 'Bash', { command: 'ls' })]),
    { type: 'attachment', timestamp: T(2) },
    back(3, [result('a', 'ok')]),
    say(4, [use('b', 'Bash', { command: 'pwd' })]),
  ]);
  assert.deepEqual(plain(m.before), []);
  assert.deepEqual(plain(m.turns[0].items), [{ kind: 'action', index: 0 }, { kind: 'system', rec: 2 },
    { kind: 'action', index: 1 }]);
});
