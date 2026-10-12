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
function fake(answers, extra) {
  const DL = load(undefined, extra);
  const asked = [];
  DL.api.source = () => 'api';
  DL.api.get = (path) => { asked.push(path); const a = answers[path]; return Promise.resolve(a ? a[0] : null); };
  DL.api.versionOf = (path) => (answers[path] ? answers[path][1] : null);
  DL.api.contentOf = (answer) => JSON.stringify(answer); /* the server's X-Devloops-Content */
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

test('after a change only the mounted live view is loaded again (SC-003)', async () => {
  const { DL, asked } = fake({ 'calls': [{}, 'v1'], 'events': [{}, 'v1'], 'files': [{}, 'v1'] });
  DL.router.register('calls', { data: () => ['calls'], render() {} });
  DL.router.register('events', { live: true, data: () => ['events'], render() {} });
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
  assert.equal(DL.router.stale, false);
});

const settle = () => new Promise((resolve) => setTimeout(resolve, 10));

/* A served DL with two views that are read, `calls` and `events`, recording what is drawn and
   the stale marks. */
function reader(answers) {
  const f = fake(answers, { scrollTo() {} });
  const shown = [], stale = [];
  f.DL.router.register('calls', { data: () => ['calls'], render() {} });
  f.DL.router.register('events', { data: () => ['events'], render() {} });
  f.DL.router._show = (loaded, refresh) => shown.push([loaded.route.view, !!refresh]);
  f.DL.bus.on('stale', (s) => stale.push(s));
  f.DL.bus.on('changed', f.DL.router.refresh); /* as router.start does */
  return Object.assign(f, { shown, stale });
}

test('after a change a view that is read stays as it is, marked stale when its data changed (FR-003 revised)', async () => {
  const answers = { 'calls': [{ n: 1 }, 'v1'], 'events': [{}, 'v1'] };
  const { DL, shown, stale } = reader(answers);
  await DL.router.mount(DL.router.parse('#/calls'));
  /* the workspace changed, but not what this view shows (the same content hash) */
  answers.calls[0] = { n: 1 };
  DL.bus.emit('changed', 'v2');
  await settle();
  assert.deepEqual(shown, [['calls', false]]);
  assert.equal(DL.router.stale, false);
  /* what it shows changed: still not drawn again, only marked */
  answers.calls[0] = { n: 2 };
  DL.bus.emit('changed', 'v3');
  await settle();
  assert.deepEqual(shown, [['calls', false]]);
  assert.equal(DL.router.stale, true);
  assert.deepEqual(stale, [true]);
  /* the reader asks for the changes: the same view again, in place */
  await DL.router.update();
  assert.deepEqual(shown, [['calls', false], ['calls', true]]);
  assert.equal(DL.router.stale, false);
  /* opening another view also shows the latest data and clears the mark */
  answers.calls[0] = { n: 3 };
  DL.bus.emit('changed', 'v4');
  await settle();
  await DL.router.mount(DL.router.parse('#/events'));
  assert.deepEqual(shown.at(-1), ['events', false]);
  assert.deepEqual(stale, [true, false, true, false]);
});

test('a failed update keeps the stale mark', async () => {
  const answers = { 'calls': [{ n: 1 }, 'v1'] };
  const { DL, shown } = reader(answers);
  await DL.router.mount(DL.router.parse('#/calls'));
  answers.calls[0] = { n: 2 };
  DL.bus.emit('changed', 'v2');
  await settle();
  assert.equal(DL.router.stale, true);
  DL.api.get = () => Promise.reject(Object.assign(new Error('HTTP 500'), { status: 500 }));
  await DL.router.update();
  assert.deepEqual(shown, [['calls', false]]);
  assert.equal(DL.router.stale, true);
});

test('a view that failed to load is loaded again after a change', async () => {
  const answers = { 'calls': [{ n: 1 }, 'v1'] };
  const { DL, shown } = reader(answers);
  const get = DL.api.get;
  DL.api.get = () => Promise.reject(Object.assign(new Error('not found'), { status: 404 }));
  /* the error message is drawn into a stand-in host (no DOM under node) */
  DL.router.host = { firstElementChild: null, appendChild() {}, replaceChild() {} };
  DL.el = () => ({ appendChild() {} });
  DL.add = () => {};
  DL.btn = () => ({});
  DL.tips = () => {};
  await DL.router.mount(DL.router.parse('#/calls'));
  assert.equal(DL.router.failed, true);
  DL.api.get = get;
  DL.bus.emit('changed', 'v2');
  await settle();
  assert.deepEqual(shown, [['calls', true]]);
  assert.equal(DL.router.failed, false);
  assert.equal(DL.router.stale, false);
});

/* Makes `DL.api.get` wait until the returned `release()` is called, answering what `answers`
   holds at that moment. */
function held(DL, answers) {
  const waiting = [];
  DL.api.get = (path) => new Promise((resolve) => waiting.push(() => resolve(answers[path][0])));
  return () => { waiting.splice(0).forEach((go) => go()); };
}

test('a change while a view loads is checked once it is drawn', async () => {
  const answers = { 'calls': [{ n: 1 }, 'v1'] };
  const { DL, asked, shown } = reader(answers);
  const get = DL.api.get, release = held(DL, answers);
  const mounted = DL.router.mount(DL.router.parse('#/calls'));
  DL.bus.emit('changed', 'v2');   /* the load may hold the data from before this change */
  release();                      /* it draws n: 1 */
  answers.calls[0] = { n: 2 };    /* while the workspace now says n: 2 */
  DL.api.get = get;
  await mounted;
  await settle();
  assert.deepEqual(shown, [['calls', false]]);
  assert.equal(DL.router.stale, true);
  assert.deepEqual(asked, ['calls']); /* asked once, after the drawing */
});

test('opening a view after an error is a first drawing, even when a change comes meanwhile', async () => {
  const answers = { 'calls': [{ n: 1 }, 'v1'], 'events': [{}, 'v1'] };
  const { DL, shown } = reader(answers);
  const get = DL.api.get;
  DL.api.get = () => Promise.reject(Object.assign(new Error('not found'), { status: 404 }));
  DL.router.host = { firstElementChild: null, appendChild() {}, replaceChild() {} };
  DL.el = () => ({ appendChild() {} });
  DL.add = () => {};
  DL.btn = () => ({});
  DL.tips = () => {};
  await DL.router.mount(DL.router.parse('#/calls'));
  assert.equal(DL.router.failed, true);
  const release = held(DL, answers);
  const mounted = DL.router.mount(DL.router.parse('#/events'));
  assert.equal(DL.router.failed, false);
  DL.bus.emit('changed', 'v2');
  release();
  DL.api.get = get;
  await mounted;
  await settle();
  /* drawn as a first drawing (what its address asks for is applied), not replaced by a refresh */
  assert.deepEqual(shown, [['events', false]]);
});

test('a view already stale is not asked again on each change', async () => {
  const answers = { 'calls': [{ n: 1 }, 'v1'] };
  const { DL, asked } = reader(answers);
  await DL.router.mount(DL.router.parse('#/calls'));
  answers.calls[0] = { n: 2 };
  DL.bus.emit('changed', 'v2');
  await settle();
  assert.equal(DL.router.stale, true);
  asked.length = 0;
  DL.bus.emit('changed', 'v3');
  DL.bus.emit('changed', 'v4');
  await settle();
  assert.deepEqual(asked, []);
});

test('a check that ends after a newer drawing does not mark it stale', async () => {
  const answers = { 'calls': [{ n: 1 }, 'v1'] };
  const { DL, shown } = reader(answers);
  await DL.router.mount(DL.router.parse('#/calls'));
  const get = DL.api.get, release = held(DL, answers);
  answers.calls[0] = { n: 2 };
  DL.bus.emit('changed', 'v2');   /* a quiet check starts and waits */
  DL.api.get = get;
  await DL.router.update();       /* the reader draws n: 2 meanwhile */
  answers.calls[0] = { n: 3 };
  release();                      /* the old check now answers n: 3 */
  await settle();
  assert.deepEqual(shown, [['calls', false], ['calls', true]]);
  assert.equal(DL.router.stale, false);
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

test('a redraw (the time zone) draws the data on screen again: nothing is asked, and a stale view stays stale', async () => {
  const answers = { 'calls': [{ n: 1 }, 'v1'] };
  const { DL, asked } = fake(answers);
  DL.router.register('calls', { data: () => ['calls'], render() {} });
  const shown = [];
  DL.router._show = (loaded, refresh) => shown.push([loaded.data[0].n, !!refresh]);
  await DL.router.mount(DL.router.parse('#/calls'));
  answers.calls[0] = { n: 2 };
  await DL.router.refresh();
  assert.equal(DL.router.stale, true);
  asked.length = 0;
  shown.length = 0;
  DL.router.redraw();
  assert.deepEqual(asked, []);
  assert.deepEqual(shown, [[1, true]]);
  assert.equal(DL.router.stale, true);
});
