'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const load = require('./load.js');

test('parse and href, both ways', () => {
  const R = load().router;
  const cases = [
    ['#/', 'overview', {}],
    ['#/run', 'run', {}],
    ['#/loop/backend-dev', 'loop', { loop: 'backend-dev' }],
    ['#/loop/backend-dev/m/M01/t/2.1', 'trial', { loop: 'backend-dev', milestone: 'M01', key: '2.1' }],
    ['#/calls', 'calls', {}],
    ['#/call/frontend-dev/12', 'call', { loop: 'frontend-dev', seq: '12' }],
    ['#/files', 'files', {}],
    ['#/file/f-backend-dev-progress-md', 'file', { id: 'f-backend-dev-progress-md' }],
    ['#/questions', 'questions', {}],
    ['#/events', 'events', {}],
  ];
  for (const [hash, view, params] of cases) {
    const r = R.parse(hash);
    assert.equal(r.view, view, hash);
    assert.deepEqual(load.plain(r.params), params, hash);
    assert.equal(R.href(view, params), hash, hash);
  }
});

test('queries, encoding, and unknown addresses', () => {
  const R = load().router;
  const r = R.parse('#/call/backend-dev/3?at=12&q=a%20b');
  assert.deepEqual(load.plain(r.query), { at: '12', q: 'a b' });
  assert.equal(R.href('call', { loop: 'backend-dev', seq: 3 }, { at: 12 }), '#/call/backend-dev/3?at=12');
  assert.equal(R.href('file', { id: 'a b/c' }), '#/file/a%20b%2Fc');
  assert.equal(R.parse('#/file/a%20b%2Fc').params.id, 'a b/c');
  assert.equal(R.parse('').view, 'overview');
  assert.equal(R.parse('#/loop/x/').view, 'loop');
  const unknown = R.parse('#/nowhere/at/all');
  assert.equal(unknown.view, 'overview');
  assert.equal(unknown.unknown, true);
});

/* A DL whose API answers from `answers` (path -> [value, version]) and records the requests. */
function fake(answers) {
  const DL = load();
  const asked = [];
  DL.api.source = () => 'api';
  DL.api.get = (path) => { asked.push(path); const a = answers[path]; return Promise.resolve(a ? a[0] : null); };
  DL.api.versionOf = (path) => (answers[path] ? answers[path][1] : null);
  let dropped = 0;
  DL.api.invalidate = () => { dropped++; for (const p in answers) answers[p][1] = 'v2'; };
  return { DL, asked, dropped: () => dropped };
}

test('a view whose answers come from two versions is asked again once', async () => {
  const { DL, asked, dropped } = fake({ 'loops/a': [{ n: 1 }, 'v1'], 'summary': [{ s: 1 }, 'v2'] });
  DL.router.register('loop', { data: (p) => ['loops/' + p.loop, 'summary'], render() {} });
  const loaded = await DL.router.load(DL.router.parse('#/loop/a'));
  assert.equal(dropped(), 1);
  assert.deepEqual(asked, ['loops/a', 'summary', 'loops/a', 'summary']);
  assert.equal(loaded.data.length, 2);
});

test('answers from one version are used as they are', async () => {
  const { DL, asked, dropped } = fake({ 'loops/a': [{}, 'v1'], 'summary': [{}, 'v1'] });
  DL.router.register('loop', { data: (p) => ['loops/' + p.loop, 'summary'], render() {} });
  await DL.router.load(DL.router.parse('#/loop/a'));
  assert.equal(dropped(), 0);
  assert.deepEqual(asked, ['loops/a', 'summary']);
});

test('after a change only the mounted view is loaded again (SC-003)', async () => {
  const { DL, asked } = fake({ 'calls': [{}, 'v1'], 'events': [{}, 'v1'], 'files': [{}, 'v1'] });
  DL.router.register('calls', { data: () => ['calls'], render() {} });
  DL.router.register('events', { data: () => ['events'], render() {} });
  DL.router.register('files', { data: () => ['files'], render() {} });
  const shown = [];
  DL.router._show = (loaded, refresh) => shown.push([loaded.route.view, !!refresh]);
  await DL.router.mount(DL.router.parse('#/events'));
  asked.length = 0;
  DL.bus.on('changed', DL.router.refresh); /* as router.start does */
  DL.bus.emit('changed', 'v2');
  await new Promise((resolve) => setTimeout(resolve, 10));
  assert.deepEqual(asked, ['events']);
  assert.deepEqual(shown, [['events', false], ['events', true]]);
});

test('a view that is not registered is shown as not available, not an error', async () => {
  const { DL } = fake({});
  const shown = [];
  DL.router._show = (loaded) => shown.push(loaded.def);
  await DL.router.mount({ view: 'not-a-view', params: {}, query: {} });
  assert.deepEqual(shown, [null]);
});

test('the plan view\'s old address opens the loop view, keeping the milestone (FR-020a)', () => {
  const R = load().router;
  const r = R.parse('#/loop/backend-dev/plan?m=M03');
  assert.equal(r.view, 'loop');
  assert.deepEqual(load.plain(r.params), { loop: 'backend-dev' });
  assert.deepEqual(load.plain(r.query), { m: 'M03' });
  assert.equal(R.href('loop', { loop: 'backend-dev' }, { m: 'M03' }), '#/loop/backend-dev?m=M03');
});
