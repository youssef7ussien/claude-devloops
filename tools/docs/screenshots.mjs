#!/usr/bin/env node
/* Screenshots of the dashboard for the documentation (spec 006 FR-010, research R-10).

     node tools/docs/screenshots.mjs              # run the sample, shoot every view
     node tools/docs/screenshots.mjs <project>    # shoot an existing project's dashboard

   It runs the examples' sample (python3 tools/docs/examples.py --keep: the same run the outputs on
   the site come from), starts `devloops dashboard --daemon` on a free port, opens it in headless
   Chromium over the DevTools protocol at 1400x900 in the light theme, and saves one PNG per view
   to docs/assets/screenshots/<view>.png. Then it stops the server and removes the sample. Run it
   by hand when the dashboard changes; it is not part of the tests (a browser is not always there).

   Needs node 22 or later (its fetch and WebSocket) and Chromium or Chrome: set CHROME to its path
   when it is not `chromium`, `chromium-browser`, `google-chrome` or `google-chrome-stable`. */
import { spawn, execFileSync } from 'node:child_process';
import fs from 'node:fs';
import net from 'node:net';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const OUT = path.join(ROOT, 'docs', 'assets', 'screenshots');
const DEVLOOPS = path.join(ROOT, 'bin', 'devloops');
const WIDTH = 1400, HEIGHT = 900;
const sleep = (ms) => new Promise((done) => setTimeout(done, ms));

function freePort() {
  return new Promise((done, fail) => {
    const server = net.createServer();
    server.on('error', fail);
    server.listen(0, '127.0.0.1', () => { const { port } = server.address(); server.close(() => done(port)); });
  });
}

function chrome() {
  const names = [process.env.CHROME, 'chromium', 'chromium-browser', 'google-chrome', 'google-chrome-stable'];
  for (const name of names.filter(Boolean)) {
    try { return execFileSync('sh', ['-c', `command -v "${name}"`], { encoding: 'utf8' }).trim(); } catch { /* next */ }
  }
  throw new Error('no Chromium or Chrome found; set CHROME to its path');
}

/* One DevTools connection to one page: send(method, params) -> result. */
async function connect(wsUrl) {
  const ws = new WebSocket(wsUrl);
  await new Promise((done, fail) => { ws.onopen = done; ws.onerror = fail; });
  let id = 0;
  const waiting = new Map();
  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    if (msg.id && waiting.has(msg.id)) {
      const { done, fail } = waiting.get(msg.id);
      waiting.delete(msg.id);
      if (msg.error) fail(new Error(`${msg.error.message} (${msg.error.code})`)); else done(msg.result);
    }
  };
  const send = (method, params = {}) => new Promise((done, fail) => {
    id += 1;
    waiting.set(id, { done, fail });
    ws.send(JSON.stringify({ id, method, params }));
  });
  return { send, close: () => ws.close() };
}

async function evaluate(page, expression) {
  const { result, exceptionDetails } = await page.send('Runtime.evaluate',
    { expression, awaitPromise: true, returnByValue: true });
  if (exceptionDetails) throw new Error(`${expression}: ${exceptionDetails.text}`);
  return result.value;
}

/* Wait until `expression` is true in the page (the view rendered), then let it settle. */
async function until(page, expression, what) {
  for (let i = 0; i < 100; i += 1) {
    if (await evaluate(page, `Boolean(${expression})`)) { await sleep(600); return; }
    await sleep(100);
  }
  throw new Error(`timed out waiting for ${what}`);
}

/* The first value in `data` (any depth) for which `test` is true, or undefined. */
function find(data, test) {
  if (test(data)) return data;
  if (data && typeof data === 'object') {
    for (const value of Object.values(data)) {
      const found = find(value, test);
      if (found !== undefined) return found;
    }
  }
  return undefined;
}

async function shoot(page, name) {
  const { data } = await page.send('Page.captureScreenshot', { format: 'png' });
  fs.writeFileSync(path.join(OUT, `${name}.png`), Buffer.from(data, 'base64'));
  console.log(`wrote ${path.relative(ROOT, path.join(OUT, name + '.png'))}`);
}

async function main() {
  let project = process.argv[2] ? path.resolve(process.argv[2]) : null;
  const sample = !project;
  if (sample) {
    project = execFileSync('python3', [path.join(ROOT, 'tools', 'docs', 'examples.py'), '--keep'],
      { encoding: 'utf8', cwd: ROOT }).trim().split('\n').pop();
  }
  const scratch = fs.mkdtempSync(path.join(os.tmpdir(), 'devloops-shots-'));
  const env = { ...process.env, DEVLOOPS_NO_BROWSER: '1', XDG_RUNTIME_DIR: path.join(scratch, 'runtime') };
  let browser = null;
  try {  /* everything after the sample exists: the finally stops and removes what was started */
    const port = await freePort();
    const started = execFileSync(DEVLOOPS, ['dashboard', '--daemon', '--port', String(port), '--no-token'],
      { cwd: project, env, encoding: 'utf8' });
    const base = (started.match(/serving: (\S+)/) || [])[1];
    if (!base) throw new Error(`the dashboard did not start:\n${started}`);
    const api = async (p) => (await fetch(new URL(`api/${p}`, base))).json();

    browser = spawn(chrome(), ['--headless=new', '--disable-gpu', '--no-first-run', '--hide-scrollbars',
      '--remote-debugging-port=0', `--user-data-dir=${path.join(scratch, 'chrome')}`, 'about:blank'],
    { stdio: 'ignore' });
    const portFile = path.join(scratch, 'chrome', 'DevToolsActivePort');
    for (let i = 0; i < 100 && !fs.existsSync(portFile); i += 1) await sleep(100);
    const devtools = fs.readFileSync(portFile, 'utf8').split('\n')[0];
    const target = await (await fetch(`http://127.0.0.1:${devtools}/json/new?about:blank`, { method: 'PUT' })).json();
    const page = await connect(target.webSocketDebuggerUrl);
    await page.send('Page.enable');
    await page.send('Runtime.enable');
    await page.send('Emulation.setDeviceMetricsOverride',
      { width: WIDTH, height: HEIGHT, deviceScaleFactor: 1, mobile: false });
    await page.send('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-color-scheme', value: 'light' }] });

    /* The items each view shows, from the dashboard's own answers. */
    const calls = (await api('calls')).calls;
    const conversation = (calls.find((c) => c.step === 'implement') || calls[0]).route;
    const trial = (find(await api('loops/backend-dev'),
      (v) => typeof v === 'string' && /^#\/loop\/backend-dev\/m\/[^/]+\/t\/[^/]+$/.test(v)));
    const file = find(await api('files'), (v) => v && v.path === 'backend-dev/outputs/openapi.json');
    const fileId = file && file.id;
    if (!trial || !fileId) throw new Error('the sample workspace has no trial or no openapi.json');

    const views = [
      ['overview', '#/'], ['run', '#/run'], ['loop', '#/loop/backend-dev'], ['trial', trial],
      ['calls', '#/calls'], ['conversation', conversation], ['files', '#/files'],
      ['viewer', `#/file/${fileId}`],
      ['questions', '#/questions'], ['events', '#/events'],
    ];
    fs.mkdirSync(OUT, { recursive: true });
    /* Each view in a freshly loaded page, so nothing of the previous one (the file viewer) stays. */
    const open = async (hash, view, what) => {
      await page.send('Page.navigate', { url: 'about:blank' });  /* else a new hash keeps the page */
      await until(page, "location.href === 'about:blank'", 'a blank page');
      await page.send('Page.navigate', { url: base + hash });
      await until(page, `document.readyState === 'complete' && document.querySelector('section.view-${view}')`, what);
      await evaluate(page, "document.documentElement.setAttribute('data-theme', 'light')");
      await sleep(300);
    };
    for (const [name, hash] of views) {
      const view = hash.startsWith('#/call/') ? 'call' : hash.startsWith('#/file/') ? 'file'
        : hash.startsWith('#/loop/') && hash.includes('/t/') ? 'trial'
          : hash === '#/' ? 'overview' : hash.slice(2).split('/')[0];
      await open(hash, view, `the ${name} view`);
      await shoot(page, name);
    }
    /* Search: the "Go to" box (Ctrl K), with a word every sample view has. */
    await open('#/', 'overview', 'the overview');
    await evaluate(page, "document.querySelector('[data-action=\"palette\"]').click()");
    await until(page, "document.activeElement && document.activeElement.tagName === 'INPUT'", 'the search box');
    await page.send('Input.insertText', { text: 'items' });
    await sleep(1500);
    await shoot(page, 'search');
    page.close();
  } finally {
    if (browser) browser.kill();
    try { execFileSync(DEVLOOPS, ['dashboard', '--stop'], { cwd: project, env, stdio: 'ignore' }); } catch { /* gone */ }
    fs.rmSync(scratch, { recursive: true, force: true });
    if (sample) fs.rmSync(path.dirname(project), { recursive: true, force: true });
  }
}

main().catch((err) => { console.error(`screenshots: ${err.message}`); process.exit(1); });
