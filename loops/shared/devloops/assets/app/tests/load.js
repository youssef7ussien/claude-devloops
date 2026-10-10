/* Loads the app's scripts for node --test: every file listed in ../scripts.txt (or `names`) is
   evaluated, in order, in one vm context with a stub window and document, and the context's DL
   is returned. Only the pure parts of the app run here; the DOM is not emulated. */
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const APP = path.join(__dirname, '..');

function listed() {
  return fs.readFileSync(path.join(APP, 'scripts.txt'), 'utf8').split('\n')
    .map((line) => line.split('#')[0].trim()).filter(Boolean);
}

function stubDocument() {
  const noop = () => {};
  return {
    readyState: 'loading',
    hidden: false,
    documentElement: {
      dataset: {}, classList: { add: noop, remove: noop, toggle: noop },
      getAttribute: () => null, setAttribute: noop, removeAttribute: noop,
    },
    addEventListener: noop, removeEventListener: noop,
    querySelector: () => null, querySelectorAll: () => [],
    getElementById: () => null, getElementsByTagName: () => [],
  };
}

module.exports = function load(names, extra) {
  const context = { console, setTimeout, clearTimeout, setInterval, clearInterval, Promise, JSON, Math, Date };
  context.window = context;
  context.document = stubDocument();
  context.location = { hash: '', pathname: '/', search: '' };
  context.history = { pushState() {}, replaceState() {} };
  context.addEventListener = () => {};
  Object.assign(context, extra || {});
  vm.createContext(context);
  for (const name of names || listed()) {
    const file = path.join(APP, name);
    if (!fs.existsSync(file)) continue; /* test_app_js checks that every listed file exists */
    vm.runInContext(fs.readFileSync(file, 'utf8'), context, { filename: file });
  }
  return context.DL;
};

/* Values made in the vm context have that context's prototypes, which assert.deepStrictEqual
   tells apart from this realm's: compare `plain(value)`. */
module.exports.plain = (value) => JSON.parse(JSON.stringify(value));
