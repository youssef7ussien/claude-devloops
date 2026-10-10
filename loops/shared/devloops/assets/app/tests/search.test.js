'use strict';
/* The palette's matching. Content search must find what the server's finds: the expected hits in
   search-fixture.json are serve.py `search_corpus`'s (test_serve.SearchCorpusTest checks them). */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const path = require('path');
const load = require('./load.js');
const { plain } = load;

const DL = load();
const s = DL.search;
const fixture = JSON.parse(fs.readFileSync(path.join(__dirname, 'search-fixture.json'), 'utf8'));

test('content: the same hits as the server for the same corpus', () => {
  for (const q of fixture.queries) {
    assert.deepEqual(plain(s.content(fixture.corpus, q)), fixture.expected[q], q);
  }
  const l = fixture.limited;
  assert.deepEqual(plain(s.content(fixture.corpus, l.query, l.limit)), l.hits);
});

test('names: characters in order, the label first, best first', () => {
  const items = [
    { kind: 'file', label: 'progress.md', detail: 'backend-dev/progress.md', route: '#/file/a' },
    { kind: 'view', label: 'Overview', detail: 'the workspace', route: '#/' },
    { kind: 'call', label: '#12 implement', detail: 'backend-dev · M01 trial 1 · opus', route: '#/call/backend-dev/12' },
    { kind: 'milestone', label: 'M01 List items', detail: 'backend-dev · Achieved', route: '#/loop/backend-dev?m=M01' }
  ];
  assert.deepEqual(plain(s.names(items, 'prog')).map((i) => i.route), ['#/file/a']);
  assert.deepEqual(plain(s.names(items, 'M01')).map((i) => i.kind), ['milestone', 'call']);
  assert.deepEqual(plain(s.names(items, 'ovw')).map((i) => i.label), ['Overview']);
  assert.equal(s.names(items, '').length, 4);
  assert.deepEqual(plain(s.names(items, 'zzz')), []);
});
