'use strict';
/* The Files view's shared tree (tree.js, FR-018b) and its folder filter (views/files.js,
   FR-020f). The paths are made up and name no application (constitution II). */
const test = require('node:test');
const assert = require('node:assert/strict');
const load = require('./load.js');
const { plain } = load;

const DL = load();

const f = (path, size) => ({ id: path, path, kind: 'text', size: size || 1 });

test('tree.build: folders below the root with counts and sizes, folders first', () => {
  const root = 'loop-a/state/milestones/M01/trials/2';
  const t = plain(DL.tree.build([f(root + '/validation.json', 10), f(root + '/evidence/b.png', 5),
                                 f(root + '/evidence/a.body', 7), f(root + '/trial.json', 3)], root + '/'));
  assert.equal(t.name, '2');
  assert.equal(t.count, 4);
  assert.equal(t.size, 25);
  assert.deepEqual(t.children.map((c) => c.name), ['evidence', 'trial.json', 'validation.json']);
  const ev = t.children[0];
  assert.equal(ev.count, 2);
  assert.equal(ev.size, 12);
  assert.deepEqual(ev.children.map((c) => c.file.path), [root + '/evidence/a.body', root + '/evidence/b.png']);
  assert.deepEqual(plain(DL.tree.build([], 'x')), { name: 'x', children: [], count: 0, size: 0 });
  /* folder names that are also Object.prototype members are plain folders */
  const odd = plain(DL.tree.build([f('constructor/a.js', 1), f('__proto__/toString/b.js', 2)], ''));
  assert.deepEqual(odd.children.map((c) => [c.name, c.count]), [['__proto__', 1], ['constructor', 1]]);
});

test('filesView.inDir: by path or by place in the tree, whole folder names only', () => {
  const inDir = DL.filesView.inDir;
  /* a loop's input outside its folder, kept by its place in the tree */
  assert.ok(inDir('/elsewhere/PRD.md', 'loop-a/Inputs', 'loop-a'));
  assert.ok(!inDir('/elsewhere/PRD.md', 'loop-b/Inputs', 'loop-a'));
  /* the workspace's own files, by the tree */
  assert.ok(inDir('workspace.json', 'workspace', 'workspace'));
  assert.ok(inDir('orchestrator/state.json', 'workspace', 'workspace/'));
  /* a real trial folder by its path */
  assert.ok(inDir('loop-a/state/milestones/M03/trials/2/evidence/x.png', 'loop-a/Milestones/M03/Trial 2/evidence',
                  'loop-a/state/milestones/M03/trials/2'));
  assert.ok(!inDir('loop-a/state/milestones/M03/trials/20/x', 'loop-a/Milestones/M03/Trial 20', 'loop-a/state/milestones/M03/trials/2'));
  /* not a prefix of another name */
  assert.ok(!inDir('loop-a-2/state/x', 'loop-a-2/Run state', 'loop-a'));
  /* no folder: everything */
  assert.ok(inDir('anything', 'top', ''));
});
