/* The Markdown parser (md.js): the tree it builds, including the list-item fix (FR-025). */
'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const load = require('./load.js');

const DL = load();
const parse = (src) => load.plain(DL.md.parse(src)).c;

/* The text of a node, its children's joined. */
function text(n) {
  if (typeof n === 'string') return n;
  return (n.c || []).map(text).join('');
}

test('a list item written over two lines keeps both (the reported case)', () => {
  const [ul] = parse('- Work only on this milestone\nand its listed tasks.');
  assert.equal(ul.t, 'ul');
  assert.equal(ul.c.length, 1);
  assert.equal(text(ul.c[0]), 'Work only on this milestone and its listed tasks.');
});

test('a wrapped item followed by another item', () => {
  const [ul] = parse('- first line\n  continued here\n- second');
  assert.deepEqual(ul.c.map(text), ['first line continued here', 'second']);
});

test('a wrapped item with inline marks keeps every part', () => {
  const [ul] = parse('- **Bold** start\n  and `code` end');
  const li = ul.c[0];
  assert.equal(text(li), 'Bold start and code end');
  assert.deepEqual(li.c.filter((c) => typeof c !== 'string').map((c) => c.t), ['strong', 'code']);
});

test('nested lists', () => {
  const [ul] = parse('- a\n  - b\n  - c\n- d');
  assert.equal(ul.c.length, 2);
  const nested = ul.c[0].c.find((c) => c.t === 'ul');
  assert.ok(nested);
  assert.deepEqual(nested.c.map(text), ['b', 'c']);
  assert.equal(text(ul.c[1]), 'd');
});

test('ordered lists keep their start', () => {
  const [ol] = parse('3. three\n4. four');
  assert.equal(ol.t, 'ol');
  assert.equal(ol.a.start, 3);
  assert.equal(ol.c.length, 2);
});

test('task items', () => {
  const [ul] = parse('- [x] done\n- [ ] todo');
  assert.deepEqual(ul.c.map((li) => [li.a.task, li.a.checked, text(li)]),
    [[true, true, 'done'], [true, false, 'todo']]);
});

test('a blank line inside an item followed by an indented paragraph', () => {
  const [ul] = parse('- first para\n\n  second para\n- next');
  assert.equal(ul.c.length, 2);
  const paras = ul.c[0].c.filter((c) => c.t === 'p');
  assert.deepEqual(paras.map(text), ['first para', 'second para']);
});

test('a table with alignment', () => {
  const [table] = parse('| a | b | c |\n|:---|:---:|---:|\n| 1 | 2 | 3 |');
  assert.equal(table.t, 'table');
  const [head, body] = table.c;
  assert.deepEqual(head.c[0].c.map(text), ['a', 'b', 'c']);
  assert.deepEqual(body.c[0].c.map((td) => td.a.align || ''), ['', 'center', 'right']);
  assert.deepEqual(body.c[0].c.map(text), ['1', '2', '3']);
});

test('a fenced code block keeps its language and text', () => {
  const [pre] = parse('```python\ndef f():\n    return "<b>"\n```');
  assert.equal(pre.t, 'pre');
  assert.equal(pre.a.lang, 'python');
  assert.equal(pre.c[0], 'def f():\n    return "<b>"');
  const [tilde] = parse('~~~\nx\n~~~');
  assert.equal(tilde.c[0], 'x');
});

test('emphasis, strong, strike, and code spans', () => {
  const [p] = parse('a *em* b **strong** c ~~del~~ d `x*y`');
  assert.deepEqual(p.c.filter((c) => typeof c !== 'string').map((c) => [c.t, text(c)]),
    [['em', 'em'], ['strong', 'strong'], ['del', 'del'], ['code', 'x*y']]);
});

test('headings, rules, quotes, and paragraphs', () => {
  const blocks = parse('# Title\n\ntext one\ntext two\n\n---\n\n> quoted\n> more');
  assert.deepEqual(blocks.map((b) => b.t), ['h1', 'p', 'hr', 'blockquote']);
  assert.equal(text(blocks[0]), 'Title');
  assert.equal(text(blocks[1]), 'text one text two');
  assert.equal(text(blocks[3]), 'quoted more');
});

test('links and images', () => {
  const [p] = parse('see [the plan](outputs/plan.md) and ![shot](a.png) and <https://x.dev>');
  const marks = p.c.filter((c) => typeof c !== 'string');
  assert.deepEqual(marks.map((c) => [c.t, c.a.url]),
    [['link', 'outputs/plan.md'], ['img', 'a.png'], ['autolink', 'https://x.dev']]);
  assert.equal(text(marks[0]), 'the plan');
  assert.equal(marks[1].a.alt, 'shot');
});

test('model-written HTML stays text', () => {
  const [p] = parse('<script>alert(1)</script>');
  assert.deepEqual(p.c, ['<script>alert(1)</script>']);
});
