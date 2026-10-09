/* highlight.js: syntax highlighting (a small rule-based tokenizer per language), pretty JSON, and
   the JSON tree. `tokenize`, `langOf`, and `pretty` are pure; `codeView` and `jsonTree` build DOM
   (only when called). */
(function (DL) {
  'use strict';

  DL.prefs = DL.prefs || { wrap: DL.store('wrap') !== '0', ln: DL.store('ln') !== '0' };

  var STR2 = /"(?:[^"\\\n]|\\.)*"|'(?:[^'\\\n]|\\.)*'/y,
    NUM = /\b-?(?:0x[\da-f]+|\d+(?:\.\d+)?(?:e[+-]?\d+)?)\b/iy,
    WORD = /[A-Za-z_$][\w$]*/y;
  function kw(words) { return new RegExp('\\b(?:' + words.split(' ').join('|') + ')\\b', 'y'); }
  var LANGS = {
    json: [[/"(?:[^"\\\n]|\\.)*"(?=\s*:)/y, 'key'], [/"(?:[^"\\\n]|\\.)*"/y, 'str'],
      [/-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?/y, 'num'], [/\b(?:true|false|null)\b/y, 'lit'], [/[{}\[\],:]/y, 'pun']],
    python: [[/#.*/y, 'com'], [/[rbfu]{0,2}("""[\s\S]*?"""|'''[\s\S]*?''')/iy, 'str'],
      [/[rbfu]{0,2}(?:"(?:[^"\\\n]|\\.)*"|'(?:[^'\\\n]|\\.)*')/iy, 'str'],
      [kw('def class return if elif else for while in import from as with try except finally raise pass break continue lambda yield not and or is global nonlocal async await assert del'), 'kw'],
      [kw('True False None self cls'), 'lit'], [/@[\w.]+/y, 'kw'], [NUM, 'num'], [WORD, null]],
    js: [[/\/\/.*/y, 'com'], [/\/\*[\s\S]*?\*\//y, 'com'], [/`(?:[^`\\]|\\[\s\S])*`/y, 'str'], [STR2, 'str'],
      [kw('const let var function return if else for while do switch case break continue new class extends import from export default try catch finally throw await async typeof instanceof in of yield this'), 'kw'],
      [kw('true false null undefined NaN'), 'lit'], [NUM, 'num'], [WORD, null]],
    shell: [[/#.*/y, 'com'], [STR2, 'str'], [/\$\{?[\w@#?*!-]+\}?/y, 'key'], [/(?:^|(?<=\s))--?[\w-]+/y, 'kw'],
      [kw('if then else elif fi for in do done while case esac function export local return sudo cd'), 'kw'], [NUM, 'num'], [WORD, null]],
    yaml: [[/#.*/y, 'com'], [/[\w.\/-]+(?=:(?:\s|$))/y, 'key'], [STR2, 'str'], [kw('true false null yes no on off'), 'lit'],
      [NUM, 'num'], [/^\s*-(?=\s)/my, 'pun'], [WORD, null]],
    http: [[/^HTTP\/[\d.]+ \d+.*$/my, 'head'], [/^(?:GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS) .*$/my, 'head'],
      [/^[\w-]+(?=:)/my, 'key'], [NUM, 'num'], [WORD, null]],
    html: [[/<!--[\s\S]*?-->/y, 'com'], [/<\/?[\w-]+/y, 'kw'], [/\/?>/y, 'kw'], [/[\w-]+(?==)/y, 'key'], [STR2, 'str'], [WORD, null]],
    css: [[/\/\*[\s\S]*?\*\//y, 'com'], [/[\w-]+(?=\s*:[^{]*[;}])/y, 'key'], [/#[\da-f]{3,8}\b/iy, 'num'], [NUM, 'num'], [STR2, 'str'], [WORD, null]],
    markdown: [[/^#{1,6} .*$/my, 'head'], [/^```.*$/my, 'com'], [/`[^`\n]+`/y, 'str'], [/\*\*[^*\n]+\*\*/y, 'kw'],
      [/^\s*(?:[-*+]|\d+\.)(?=\s)/my, 'pun'], [/\[[^\]\n]*\]\([^)\n]*\)/y, 'key'], [WORD, null]],
    log: [[/\b\d{4}-\d\d-\d\dT[\d:.]+Z?\b/y, 'com'], [/\b(?:ERROR|Error|FAIL(?:ED)?|Traceback|Exception|exit [1-9]\d*)\b/y, 'err'],
      [/\b(?:WARN(?:ING)?|Warning)\b/y, 'warn'], [/"(?:[^"\\\n]|\\.)*"/y, 'str'], [/\b(?:GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\b/y, 'kw'], [NUM, 'num'], [WORD, null]],
    text: []
  };
  LANGS.ts = LANGS.js;
  LANGS.diff = [[/^\+.*$/my, 'str'], [/^-.*$/my, 'lit'], [/^@@.*$/my, 'kw']];
  var MAX_HL = 400000;

  /* `[[class or null, text]]`: the text cut into tokens by the language's rules. */
  function tokenize(text, lang) {
    var rules = LANGS[lang] || [], out = [], plain = '', i = 0, n = text.length;
    if (!rules.length || n > MAX_HL) return [[null, text]];
    outer: while (i < n) {
      for (var r = 0; r < rules.length; r++) {
        var re = rules[r][0];
        re.lastIndex = i;
        var m = re.exec(text);
        if (m && m[0].length) {
          if (rules[r][1]) { if (plain) { out.push([null, plain]); plain = ''; } out.push([rules[r][1], m[0]]); }
          else plain += m[0];
          i += m[0].length;
          continue outer;
        }
      }
      plain += text[i++];
    }
    if (plain) out.push([null, plain]);
    return out;
  }

  function langOf(s) {
    s = (s || '').toLowerCase();
    return {
      py: 'python', python: 'python', js: 'js', javascript: 'js', ts: 'ts', typescript: 'ts',
      json: 'json', jsonc: 'json', sh: 'shell', bash: 'shell', shell: 'shell', zsh: 'shell', console: 'shell',
      yml: 'yaml', yaml: 'yaml', html: 'html', xml: 'html', css: 'css', http: 'http', md: 'markdown',
      markdown: 'markdown', diff: 'diff', log: 'log'
    }[s] || 'text';
  }

  /* JSON text indented, whatever its source; any other text unchanged. */
  function pretty(text) {
    try {
      var v = JSON.parse(text);
      return v !== null && typeof v === 'object' ? JSON.stringify(v, null, 2) : text;
    } catch (e) { return text; }
  }

  /* A code block: one `span.l` per line (CSS numbers them), tokens as `span.t-<class>`. */
  function codeView(text, lang, opts) {
    opts = opts || {};
    var el = DL.el, box = el('div', 'code' + (DL.prefs.wrap ? ' wrap' : '') + (DL.prefs.ln && opts.ln !== false ? '' : ' no-ln'));
    var line = el('span', 'l'), lines = [line], count = 1;
    box.appendChild(line);
    tokenize(String(text).replace(/\n$/, ''), lang).forEach(function (t) {
      t[1].split('\n').forEach(function (p, k) {
        if (k) { line = el('span', 'l'); box.appendChild(line); lines.push(line); count++; }
        if (!p) return;
        if (t[0]) line.appendChild(el('span', 't-' + t[0], p));
        else line.appendChild(document.createTextNode(p));
      });
    });
    lines.forEach(function (l) { if (!l.firstChild) l.appendChild(document.createTextNode('​')); });
    box.style.setProperty('--gw', String(count).length + 'ch');
    return box;
  }

  /* --- the JSON tree ------------------------------------------------------------------------ */
  function jval(v) {
    var t = v === null ? 'lit' : typeof v === 'string' ? 'str' : typeof v === 'number' ? 'num' : 'lit';
    return DL.el('span', 't-' + t, typeof v === 'string' ? JSON.stringify(v) : String(v));
  }
  function preview(v) {
    if (Array.isArray(v)) return '[' + v.length + ' item' + (v.length === 1 ? '' : 's') + ']';
    var k = Object.keys(v), hint = ['type', 'id', 'name', 'step', 'status'].filter(function (x) { return typeof v[x] === 'string'; })[0];
    return '{' + (hint ? hint + ': ' + JSON.stringify(v[hint]).slice(0, 60) + ', ' : '') + k.length + ' key' + (k.length === 1 ? '' : 's') + '}';
  }
  function jnode(key, v, depth) {
    var el = DL.el;
    if (v && typeof v === 'object') {
      var d = el('details'), s = el('summary');
      d.open = depth < 2;
      if (key !== null) { s.appendChild(el('span', 't-key', key)); s.appendChild(el('span', 't-pun', ': ')); }
      s.appendChild(el('span', 'cnt', preview(v)));
      d.appendChild(s);
      var done = false, fill = function () {
        if (done) return;
        done = true;
        (Array.isArray(v) ? v.map(function (x, k) { return [String(k), x]; })
          : Object.keys(v).map(function (k) { return [JSON.stringify(k), v[k]]; }))
          .forEach(function (kv) { d.appendChild(jnode(kv[0], kv[1], depth + 1)); });
      };
      if (d.open) fill(); else d.addEventListener('toggle', fill);
      return d;
    }
    var leaf = el('div', 'leaf');
    if (key !== null) { leaf.appendChild(el('span', 't-key', key)); leaf.appendChild(el('span', 't-pun', ': ')); }
    leaf.appendChild(jval(v));
    return leaf;
  }
  /* A JSON document, or JSON lines (`lines`) as one record each; null when `text` is not JSON. */
  function jsonTree(text, lines) {
    var box = DL.el('div', 'jt');
    if (!lines) {
      try { box.appendChild(jnode(null, JSON.parse(text), 0)); } catch (e) { return null; }
      return box;
    }
    var n = 0;
    String(text).split('\n').forEach(function (l) {
      if (!l.trim()) return;
      n++;
      var r = DL.el('div', 'rec');
      try { r.appendChild(jnode('#' + n, JSON.parse(l), 1)); }
      catch (e) { r.appendChild(DL.el('span', 't-err', '#' + n + ' (not JSON) ' + l)); }
      box.appendChild(r);
    });
    return box;
  }

  DL.hl = { LANGS: LANGS, tokenize: tokenize, langOf: langOf, pretty: pretty, codeView: codeView, jsonTree: jsonTree };
})(window.DL = window.DL || {});
