/* highlight.js: syntax highlighting, pretty JSON, and the JSON tree. Code is cut into tokens by
   Prism (vendor/, research R-16) through `Prism.tokenize` only, so text never becomes markup
   (FR-033); logs, HTTP, and diffs keep small rules of their own. Without Prism (the export) or a
   grammar, the text is one plain token. `tokenize`, `langOf`, and `pretty` are pure; `codeView`
   and `jsonTree` build DOM (only when called). */
(function (DL) {
  'use strict';

  DL.prefs = DL.prefs || { wrap: DL.store('wrap') !== '0', ln: DL.store('ln') !== '0' };

  var NUM = /\b-?(?:0x[\da-f]+|\d+(?:\.\d+)?(?:e[+-]?\d+)?)\b/iy,
    WORD = /[A-Za-z_$][\w$]*/y;
  /* The languages with rules of their own: `[[pattern, class or null]]`, tried in order. */
  var RULES = {
    http: [[/^HTTP\/[\d.]+ \d+.*$/my, 'head'], [/^(?:GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS) .*$/my, 'head'],
      [/^[\w-]+(?=:)/my, 'key'], [NUM, 'num'], [WORD, null]],
    log: [[/\b\d{4}-\d\d-\d\dT[\d:.]+Z?\b/y, 'com'], [/\b(?:ERROR|Error|FAIL(?:ED)?|Traceback|Exception|exit [1-9]\d*)\b/y, 'err'],
      [/\b(?:WARN(?:ING)?|Warning)\b/y, 'warn'], [/"(?:[^"\\\n]|\\.)*"/y, 'str'], [/\b(?:GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\b/y, 'kw'], [NUM, 'num'], [WORD, null]],
    diff: [[/^\+.*$/my, 'str'], [/^-.*$/my, 'lit'], [/^@@.*$/my, 'kw']]
  };
  /* Our language names → Prism's grammars. */
  var GRAMMAR = {
    js: 'javascript', ts: 'typescript', jsx: 'jsx', tsx: 'tsx', json: 'json', python: 'python',
    shell: 'bash', yaml: 'yaml', html: 'markup', css: 'css', markdown: 'markdown', csharp: 'csharp',
    go: 'go', java: 'java', sql: 'sql'
  };
  /* Prism's token types (or aliases) → our classes; '' resets to plain (code inside a string). */
  var TYPES = {
    keyword: 'kw', selector: 'kw', atrule: 'kw', important: 'kw', decorator: 'kw', annotation: 'kw',
    directive: 'kw', bold: 'kw', italic: 'kw',
    string: 'str', 'template-string': 'str', 'string-interpolation': 'str', 'triple-quoted-string': 'str',
    char: 'str', 'attr-value': 'str', regex: 'str', code: 'str', 'code-snippet': 'str',
    number: 'num', boolean: 'lit', constant: 'lit', 'null': 'lit', nil: 'lit',
    comment: 'com', prolog: 'com', doctype: 'com', cdata: 'com', shebang: 'com',
    property: 'key', 'attr-name': 'key', tag: 'key', key: 'key', variable: 'key', url: 'key',
    'function': 'fn', 'function-variable': 'fn', 'class-name': 'fn', builtin: 'fn',
    punctuation: 'pun', operator: 'pun', list: 'pun', hr: 'pun', blockquote: 'pun',
    title: 'head', interpolation: ''
  };
  var MAX_HL = 400000;

  function rules(text, list) {
    var out = [], plain = '', i = 0, n = text.length;
    outer: while (i < n) {
      for (var r = 0; r < list.length; r++) {
        var re = list[r][0];
        re.lastIndex = i;
        var m = re.exec(text);
        if (m && m[0].length) {
          if (list[r][1]) { if (plain) { out.push([null, plain]); plain = ''; } out.push([list[r][1], m[0]]); }
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

  function classOf(token, inherited) {
    var names = [token.type].concat(token.alias || []);
    for (var k = 0; k < names.length; k++) {
      if (Object.prototype.hasOwnProperty.call(TYPES, names[k])) return TYPES[names[k]] || null;
    }
    return inherited;
  }
  /* Prism's token tree as `[[class or null, text]]`, a nested token taking its own class or its
     parent's, adjacent texts of one class joined. */
  function flatten(list, cls, out) {
    (Array.isArray(list) ? list : [list]).forEach(function (t) {
      if (typeof t !== 'string') return flatten(t.content, classOf(t, cls), out);
      var last = out[out.length - 1];
      if (!t) return;
      if (last && last[0] === cls) last[1] += t;
      else out.push([cls, t]);
    });
    return out;
  }

  /* `[[class or null, text]]`: the text cut into tokens; their texts join to the text. */
  function tokenize(text, lang) {
    if (!text || text.length > MAX_HL) return [[null, text]];
    if (RULES[lang]) return rules(text, RULES[lang]);
    var P = window.Prism, grammar = P && P.tokenize && P.languages && P.languages[GRAMMAR[lang]];
    return grammar ? flatten(P.tokenize(text, grammar), null, []) : [[null, text]];
  }

  function langOf(s) {
    s = (s || '').toLowerCase();
    return {
      py: 'python', python: 'python', js: 'js', mjs: 'js', cjs: 'js', javascript: 'js', jsx: 'jsx',
      ts: 'ts', mts: 'ts', cts: 'ts', typescript: 'ts', tsx: 'tsx',
      json: 'json', jsonc: 'json', sh: 'shell', bash: 'shell', shell: 'shell', zsh: 'shell', console: 'shell',
      yml: 'yaml', yaml: 'yaml', html: 'html', htm: 'html', xml: 'html', svg: 'html', css: 'css',
      http: 'http', md: 'markdown', markdown: 'markdown', diff: 'diff', log: 'log',
      cs: 'csharp', csharp: 'csharp', go: 'go', java: 'java', sql: 'sql'
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

  DL.hl = { tokenize: tokenize, langOf: langOf, pretty: pretty, codeView: codeView, jsonTree: jsonTree };
})(window.DL = window.DL || {});
