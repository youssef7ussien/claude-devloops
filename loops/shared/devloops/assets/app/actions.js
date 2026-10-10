/* actions.js: a conversation's records as the model the conversation view draws (User Story 8,
   FR-021a–FR-021f, research R-15). Each tool use is paired with its result (by `tool_use_id`) into
   one action with a readable name, a family (its icon and filter), a one-line summary, an outcome
   (ok | error | unfinished), and a duration from the two records' times. Claude's text messages
   start turns that hold the actions after them; an empty thinking block becomes "thought for N s".
   The call's answer is its last `StructuredOutput` input; the first user text is the prompt.
   Everything here is pure: no DOM, so it runs under node --test. */
(function (DL) {
  'use strict';

  var SUMMARY_CHARS = 160, CLIP_OVER = 40, HEAD = 15, TAIL = 10, DIFF_CELLS = 250000;
  var IMAGE_TYPES = { 'image/png': 1, 'image/jpeg': 1, 'image/gif': 1, 'image/webp': 1 };
  var FAMILIES = { shell: 'Shell', read: 'Read', edit: 'Edit', browser: 'Browser', web: 'Web', other: 'Other' };
  var BUILTIN = {
    Bash: ['Shell', 'shell'], Read: ['Read', 'read'], Edit: ['Edit', 'edit'], MultiEdit: ['Edit', 'edit'],
    Write: ['Write', 'edit'], NotebookEdit: ['Edit notebook', 'edit'], Grep: ['Search', 'read'],
    Glob: ['Find files', 'read'], LS: ['List', 'read'], WebFetch: ['Fetch', 'web'], WebSearch: ['Web search', 'web'],
    TodoWrite: ['Todos', 'other'], Agent: ['Agent', 'other'], Task: ['Agent', 'other'],
    ToolSearch: ['Load tools', 'other'], StructuredOutput: ['Answer', 'other']
  };
  var BROWSER = {
    click: 'Click', type: 'Type', fill_form: 'Fill form', navigate: 'Navigate', navigate_back: 'Go back',
    snapshot: 'Snapshot', take_screenshot: 'Screenshot', evaluate: 'Evaluate', network_requests: 'Requests',
    console_messages: 'Console', wait_for: 'Wait', press_key: 'Press key', select_option: 'Select',
    hover: 'Hover', close: 'Close', resize: 'Resize', drag: 'Drag', file_upload: 'Upload',
    handle_dialog: 'Dialog', tabs: 'Tabs', run_code: 'Run code', install: 'Install'
  };
  var FIRST_KEYS = ['description', 'command', 'file_path', 'path', 'url', 'query', 'pattern', 'element', 'text', 'name'];

  /* --- small helpers ---------------------------------------------------------------------------- */

  function str(v) { return typeof v === 'string' ? v : ''; }

  function oneLine(text) {
    var s = String(text == null ? '' : text).replace(/\s+/g, ' ').trim();
    return s.length > SUMMARY_CHARS ? s.slice(0, SUMMARY_CHARS - 1) + '…' : s;
  }

  function lines(text) { return text ? String(text).replace(/\n$/, '').split('\n') : []; }

  function base(path) {
    var p = str(path).replace(/\/+$/, '');
    return p.slice(p.lastIndexOf('/') + 1) || p;
  }

  /* "some_server" → "Some server"; "createIssue" → "Create issue". */
  function words(s) {
    var w = String(s || '').replace(/([a-z0-9])([A-Z])/g, '$1 $2').replace(/[_\-]+/g, ' ').trim().toLowerCase();
    return w ? w.charAt(0).toUpperCase() + w.slice(1) : '';
  }

  function time(value) {
    var t = typeof value === 'string' ? Date.parse(value) : NaN;
    return isNaN(t) ? null : t;
  }

  /* --- names ------------------------------------------------------------------------------------ */

  /* A tool's readable name and its family. */
  function name(tool) {
    tool = String(tool || '');
    if (Object.prototype.hasOwnProperty.call(BUILTIN, tool)) return { name: BUILTIN[tool][0], family: BUILTIN[tool][1] };
    var parts = tool.split('__');
    if (parts[0] === 'mcp' && parts.length >= 3) {
      var server = parts[1], t = parts.slice(2).join('__');
      if (server === 'playwright' && t.indexOf('browser_') === 0) {
        var a = t.slice(8);
        return { name: BROWSER[a] || words(a), family: 'browser' };
      }
      return { name: words(server) + ' · ' + words(t), family: 'other' };
    }
    return { name: words(tool) || '?', family: 'other' };
  }

  /* The first meaningful input: the first non-empty string of the usual keys, then of any key;
     else "N inputs". */
  function firstInput(input) {
    var i = input && typeof input === 'object' ? input : {};
    var keys = FIRST_KEYS.concat(Object.keys(i).filter(function (k) { return FIRST_KEYS.indexOf(k) < 0; }));
    for (var k = 0; k < keys.length; k++) {
      if (typeof i[keys[k]] === 'string' && i[keys[k]].trim()) return oneLine(i[keys[k]]);
    }
    var n = Object.keys(i).length;
    return n ? n + (n === 1 ? ' input' : ' inputs') : '';
  }

  /* --- results ---------------------------------------------------------------------------------- */

  /* A result block's text (its string, or its text parts joined) and its images. */
  function resultParts(block) {
    var c = block ? block.content : null, text = [], images = [];
    if (typeof c === 'string') text.push(c);
    else if (Array.isArray(c)) {
      c.forEach(function (p) {
        if (typeof p === 'string') text.push(p);
        else if (p && p.type === 'text') text.push(p.text || '');
        else if (p && p.type === 'image') {
          var src = p.source || {};
          if (src.type === 'base64' && IMAGE_TYPES[src.media_type] && typeof src.data === 'string') {
            images.push({ media_type: src.media_type, data: src.data });
          } else text.push('[image: ' + (src.media_type || src.type || 'unknown') + ', not shown]');
        } else if (p && p.type === 'tool_reference') text.push(p.tool_name || '');
        else if (p) text.push(JSON.stringify(p));
      });
    } else if (c != null) text.push(JSON.stringify(c, null, 2));
    return { text: text.join('\n'), images: images };
  }

  /* A browser tool's Markdown answer split at its "### " headings: {title: body}. */
  function sections(text) {
    var out = {}, cur = null, buf = [];
    lines(text).forEach(function (l) {
      var m = /^### (.+)$/.exec(l);
      if (m) {
        if (cur) out[cur] = buf.join('\n').trim();
        cur = m[1].trim();
        buf = [];
      } else if (cur) buf.push(l);
    });
    if (cur) out[cur] = buf.join('\n').trim();
    return out;
  }

  /* What a browser result says: the code it ran, the page after it, the console counts, the
     snapshot, the result, the error. */
  function browserInfo(text) {
    var s = sections(text), info = { code: '', url: '', title: '', errors: 0, warnings: 0, snapshot: '', result: '', error: '' };
    var code = s['Ran Playwright code'] || '';
    info.code = code.replace(/^```\w*\n?|\n?```$/g, '').trim();
    var page = s.Page || '';
    var u = /^- Page URL: (.+)$/m.exec(page), t = /^- Page Title: (.*)$/m.exec(page), c = /^- Console: (.+)$/m.exec(page);
    if (u) info.url = u[1].trim();
    if (t) info.title = t[1].trim();
    if (c) {
      var e = /(\d+) errors?/.exec(c[1]), w = /(\d+) warnings?/.exec(c[1]);
      info.errors = e ? +e[1] : 0;
      info.warnings = w ? +w[1] : 0;
    }
    info.snapshot = s.Snapshot || s['Page state'] || '';
    info.result = s.Result || '';
    info.error = s.Error || '';
    return info;
  }

  /* The element a browser action targeted, from the code it ran: `getByRole('button', { name:
     'Save' })` → `button "Save"`. */
  function target(code) {
    var m = /getByRole\(\s*'([^']+)'\s*,\s*\{\s*name:\s*'((?:[^'\\]|\\.)*)'/.exec(code || '');
    if (m) return m[1] + ' "' + m[2].replace(/\\(.)/g, '$1') + '"';
    m = /getBy(Text|Label|Placeholder|TestId|Title|AltText)\(\s*'((?:[^'\\]|\\.)*)'/.exec(code || '');
    if (m) return ({ Text: 'text', Label: 'field', Placeholder: 'field', TestId: 'test id', Title: 'title', AltText: 'image' })[m[1]] +
      ' "' + m[2].replace(/\\(.)/g, '$1') + '"';
    m = /getByRole\(\s*'([^']+)'/.exec(code || '');
    return m ? m[1] : '';
  }

  function pathOf(url) {
    var m = /^[a-z]+:\/\/[^/]+(\/[^?#]*)?/i.exec(url || '');
    return m ? (m[1] || '/') : url;
  }

  /* Lines of shell output that look like failures (a hint only; the outcome is the tool's):
     their indexes. A "fail" word next to a zero count or an empty value ("fail 0", "0 failed",
     `"failures": []`) is not one. */
  function failureLines(text) {
    var out = [];
    lines(text).forEach(function (l, k) {
      if (/✖|✗|✕|\bnot ok\b|ERR!|\bError:|Traceback/.test(l)) { out.push(k); return; }
      var re = /\b(fail(?:ed|ing|ures?|s)?)\b/gi, m;
      while ((m = re.exec(l))) {
        var before = l.slice(0, m.index), after = l.slice(m.index + m[0].length);
        if (/\b0\s*$/.test(before) || /^["']?\s*[:=]?\s*(0\b|\[\s*\]|\{\s*\}|false\b|null\b|none\b)/i.test(after)) continue;
        out.push(k);
        return;
      }
    });
    return out;
  }

  /* A line diff of `a` and `b`: [{op: ' '|'-'|'+', text}], with the counts. */
  function diff(a, b) {
    var x = lines(a), y = lines(b), pre = 0, post = 0, out = [], k;
    while (pre < x.length && pre < y.length && x[pre] === y[pre]) pre += 1;
    while (post < x.length - pre && post < y.length - pre && x[x.length - 1 - post] === y[y.length - 1 - post]) post += 1;
    var xs = x.slice(pre, x.length - post), ys = y.slice(pre, y.length - post), mid = [];
    if (xs.length * ys.length > DIFF_CELLS) {
      xs.forEach(function (t) { mid.push({ op: '-', text: t }); });
      ys.forEach(function (t) { mid.push({ op: '+', text: t }); });
    } else {
      var n = xs.length, m = ys.length, L = [];
      for (var i = 0; i <= n; i++) L.push(new Array(m + 1).fill(0));
      for (i = n - 1; i >= 0; i--) {
        for (var j = m - 1; j >= 0; j--) L[i][j] = xs[i] === ys[j] ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1]);
      }
      i = 0; j = 0;
      while (i < n && j < m) {
        if (xs[i] === ys[j]) { mid.push({ op: ' ', text: xs[i] }); i += 1; j += 1; }
        else if (L[i + 1][j] >= L[i][j + 1]) { mid.push({ op: '-', text: xs[i] }); i += 1; }
        else { mid.push({ op: '+', text: ys[j] }); j += 1; }
      }
      for (; i < n; i++) mid.push({ op: '-', text: xs[i] });
      for (; j < m; j++) mid.push({ op: '+', text: ys[j] });
    }
    for (k = 0; k < pre; k++) out.push({ op: ' ', text: x[k] });
    out = out.concat(mid);
    for (k = x.length - post; k < x.length; k++) out.push({ op: ' ', text: x[k] });
    var added = 0, removed = 0;
    out.forEach(function (d) { if (d.op === '+') added += 1; else if (d.op === '-') removed += 1; });
    return { lines: out, added: added, removed: removed };
  }

  /* A file read's lines split from their numbers (`  12→text` or `12\ttext`): [{n, text}]; null
     when the text is not numbered. Lines after the numbered ones (a note) keep n null. */
  function readLines(text) {
    var ls = lines(text), out = [], numbered = 0;
    for (var k = 0; k < ls.length; k++) {
      var m = /^\s*(\d+)(?:→|\t)(.*)$/.exec(ls[k]);
      if (m && numbered === out.length) { out.push({ n: +m[1], text: m[2] }); numbered += 1; }
      else out.push({ n: null, text: ls[k] });
    }
    return numbered ? out : null;
  }

  /* Long text as its first and last lines: {head, tail, hidden}. */
  function clip(ls) {
    if (ls.length <= CLIP_OVER) return { head: ls, tail: [], hidden: 0 };
    return { head: ls.slice(0, HEAD), tail: ls.slice(ls.length - TAIL), hidden: ls.length - HEAD - TAIL };
  }

  /* How a result is shown: image (images only), browser, read, edit, terminal, markdown, text.
     `read` is the text's readLines when already known. */
  function kind(tool, text, images, read) {
    var fam = name(tool).family;
    if (images && images.length && !String(text || '').trim()) return 'image';
    if (fam === 'browser') return 'browser';
    if (tool === 'Read') return (read !== undefined ? read : readLines(text)) ? 'read' : 'text';
    if (tool === 'Edit' || tool === 'MultiEdit' || tool === 'Write') return 'edit';
    if (tool === 'Bash') return 'terminal';
    if (/^#{1,6} \S|^\s*[-*] \S|^```/m.test(text || '')) return 'markdown';
    return 'text';
  }

  /* The edits of an Edit, MultiEdit, or Write use: [{old, new}]. */
  function edits(tool, input) {
    var i = input && typeof input === 'object' ? input : {};
    if (tool === 'MultiEdit' && Array.isArray(i.edits)) {
      return i.edits.map(function (e) { return { old: str(e && e.old_string), new: str(e && e.new_string) }; });
    }
    if (tool === 'Edit') return [{ old: str(i.old_string), new: str(i.new_string) }];
    if (tool === 'Write') return [{ old: '', new: str(i.content) }];
    return [];
  }

  /* --- summaries -------------------------------------------------------------------------------- */

  /* The one-line summary of an action: `a` has tool, input, text (the result's), info (a browser
     result's), record (the result record), url_before (the page before a browser action), and,
     when build() has worked them out, read_lines and the edit's added and removed lines. */
  function summary(a) {
    var i = a.input && typeof a.input === 'object' ? a.input : {}, tool = a.tool, s;
    switch (tool) {
      case 'Bash':
        return oneLine(str(i.description) || lines(str(i.command))[0] || '');
      case 'Read':
        s = base(i.file_path);
        if (typeof i.offset === 'number' || typeof i.limit === 'number') {
          var from = typeof i.offset === 'number' ? i.offset : 1;
          s += ' · lines ' + from + '–' + (typeof i.limit === 'number' ? from + i.limit - 1 : '');
        } else {
          var read = a.read_lines !== undefined ? a.read_lines : a.text != null ? readLines(a.text) : null;
          if (read) s += ' · ' + read.filter(function (l) { return l.n != null; }).length + ' lines';
        }
        return oneLine(s);
      case 'Edit': case 'MultiEdit': case 'Write':
        if (tool === 'Write') return oneLine(base(i.file_path) + ' · ' + lines(str(i.content)).length + ' lines');
        var added = a.added, removed = a.removed;
        if (typeof added !== 'number' || typeof removed !== 'number') {
          added = 0;
          removed = 0;
          edits(tool, i).forEach(function (e) { var d = diff(e.old, e.new); added += d.added; removed += d.removed; });
        }
        s = base(i.file_path) + ' · +' + added + ' −' + removed;
        var patch = a.record && a.record.toolUseResult && a.record.toolUseResult.structuredPatch;
        if (Array.isArray(patch) && patch[0] && typeof patch[0].newStart === 'number') s += ' at line ' + patch[0].newStart;
        return oneLine(s);
      case 'NotebookEdit':
        return oneLine(base(i.notebook_path));
      case 'Grep':
        return oneLine(str(i.pattern) + (i.path || i.glob ? ' in ' + (str(i.path) || str(i.glob)) : ''));
      case 'Glob':
        return oneLine(str(i.pattern) + (i.path ? ' in ' + str(i.path) : ''));
      case 'WebFetch':
        return oneLine(i.url);
      case 'WebSearch': case 'ToolSearch':
        return oneLine(i.query);
      case 'TodoWrite':
        var todos = Array.isArray(i.todos) ? i.todos : [];
        return todos.length + (todos.length === 1 ? ' item, ' : ' items, ') +
          todos.filter(function (t) { return t && t.status === 'completed'; }).length + ' done';
      case 'Agent': case 'Task':
        return oneLine(str(i.description) || str(i.prompt));
    }
    if (name(tool).family === 'browser') return browserSummary(a, i);
    return firstInput(i);
  }

  function browserSummary(a, i) {
    var info = a.info || browserInfo(a.text || ''), action = String(a.tool).split('browser_')[1], s;
    var what = target(info.code) || str(i.element) || target(str(i.target)) || str(i.target);
    switch (action) {
      case 'click': case 'hover': case 'drag':
        s = what; break;
      case 'type':
        s = '"' + str(i.text) + '"' + (what ? ' into ' + what : ''); break;
      case 'fill_form':
        var fields = Array.isArray(i.fields) ? i.fields : [];
        var field = fields[0] && typeof fields[0] === 'object' ? fields[0] : {}; /* model-written: may be anything */
        s = fields.length === 1 && str(field.name) ? str(field.name) + ' = ' + str(field.value) : fields.length + (fields.length === 1 ? ' field' : ' fields'); break;
      case 'select_option':
        s = what + (Array.isArray(i.values) ? ' = ' + i.values.join(', ') : ''); break;
      case 'navigate':
        s = str(i.url); break;
      case 'press_key':
        s = str(i.key); break;
      case 'wait_for':
        s = str(i.text) || str(i.textGone) || (i.time != null ? i.time + ' s' : ''); break;
      case 'snapshot':
        s = info.url ? pathOf(info.url) + (info.title ? ' · ' + info.title : '') : firstInput(i); break;
      case 'take_screenshot':
        var file = str(i.filename);
        s = (i.fullPage ? 'full page' : (what || 'page')) + (file ? ' → ' + file.split('/').slice(-2).join('/') : ''); break;
      case 'evaluate':
        var res = lines(info.result)[0] || '';
        s = oneLine(str(i.function)).slice(0, 80) + (res ? ' → ' + res : ''); break;
      case 'network_requests':
        var reqs = lines(info.result || a.text).map(function (l) { return /=> \[(\d+)\]/.exec(l); }).filter(Boolean);
        var codes = {};
        reqs.forEach(function (m) { codes[m[1]] = 1; });
        var list = Object.keys(codes).sort();
        s = reqs.length + (reqs.length === 1 ? ' request' : ' requests') +
          (list.length === 1 ? (reqs.length > 1 ? ', all ' : ', ') + list[0] : list.length ? ', statuses ' + list.join(', ') : ''); break;
      default:
        s = what || firstInput(i);
    }
    if (action !== 'snapshot' && info.url && a.url_before && pathOf(info.url) !== pathOf(a.url_before)) {
      s = (s ? s + ' ' : '') + '→ ' + pathOf(info.url);
    }
    return oneLine(s);
  }

  /* --- the answer --------------------------------------------------------------------------------- */

  /* The call's answer: the input of its last StructuredOutput use, with its shape. */
  function answer(records) {
    var found = null;
    (records || []).forEach(function (r, rec) {
      blocks(r).forEach(function (b) {
        if (b.type === 'tool_use' && b.name === 'StructuredOutput') found = { rec: rec, input: b.input };
      });
    });
    if (!found || !found.input || typeof found.input !== 'object') return null;
    var i = found.input;
    found.shape = Array.isArray(i.criteria) ? 'criteria' : Array.isArray(i.tasks) ? 'tasks' : 'other';
    return found;
  }

  function role(r) {
    if (!r || typeof r !== 'object' || r.raw != null) return null;
    var m = r.message;
    if (!m || typeof m !== 'object') return null;
    var who = m.role || r.type;
    return who === 'user' || who === 'assistant' ? who : null;
  }

  function blocks(r) {
    if (!role(r)) return [];
    var c = r.message.content;
    if (typeof c === 'string') return [{ type: 'text', text: c }];
    return Array.isArray(c) ? c.filter(function (b) { return b && typeof b === 'object'; }) : [];
  }

  /* --- the model ---------------------------------------------------------------------------------- */

  /* The model of a conversation: {prompt, answer, before, turns, actions, errors, stats, at}.
     `turns` are [{rec, text, elapsed_ms, items}] (the first may have no text), items being actions
     ({kind: 'action', index}) and thoughts ({kind: 'thought', rec, ms, text}) and user texts
     ({kind: 'user', rec, text}) and system records ({kind: 'system', rec}) where they happened;
     `before` holds the system records that came before the prompt (FR-021f); `at[rec]` names what shows a record: {type: 'action', index} |
     {type: 'turn', index} | {type: 'answer'} | {type: 'prompt'} | {type: 'system'}. */
  function build(records) {
    records = records || [];
    var t0 = null, turns = [{ rec: null, text: null, elapsed_ms: null, items: [] }], actions = [], open = {}, at = {};
    var model = { prompt: null, answer: answer(records), before: [], turns: turns, actions: actions, errors: [], at: at,
      stats: { actions: 0, families: {}, errors: 0, files: {} } };
    var prio = { system: 0, turn: 1, prompt: 2, answer: 2, action: 3 };
    function mark(rec, place) { if (!at[rec] || prio[place.type] > prio[at[rec].type]) at[rec] = place; }
    /* a record nothing else shows: in place, before the prompt or in the turn it came in */
    function place(rec) {
      if (at[rec].type !== 'system') return;
      if (!model.prompt) model.before.push(rec);
      else turns[turns.length - 1].items.push({ kind: 'system', rec: rec });
    }
    records.forEach(function (r) { if (t0 == null && r && typeof r === 'object') t0 = time(r.timestamp); });

    records.forEach(function (r, rec) {
      var who = role(r), turn = turns[turns.length - 1], ts = r && typeof r === 'object' ? time(r.timestamp) : null;
      if (!who) { mark(rec, { type: 'system' }); place(rec); return; }
      blocks(r).forEach(function (b) {
        if (b.type === 'text') {
          if (who === 'user') {
            if (!model.prompt) { model.prompt = { rec: rec, text: b.text || '' }; mark(rec, { type: 'prompt' }); }
            else { turn.items.push({ kind: 'user', rec: rec, text: b.text || '' }); mark(rec, { type: 'turn', index: turns.length - 1 }); }
          } else if (String(b.text || '').trim()) {
            turns.push(turn = { rec: rec, text: b.text, elapsed_ms: ts != null && t0 != null ? ts - t0 : null, items: [] });
            mark(rec, { type: 'turn', index: turns.length - 1 });
          }
        } else if (b.type === 'thinking' || b.type === 'redacted_thinking') {
          var text = str(b.thinking), ms = typeof r.thinkingDurationMs === 'number' ? r.thinkingDurationMs : null;
          if (text.trim() || ms != null) turn.items.push({ kind: 'thought', rec: rec, ms: ms, text: text });
          mark(rec, { type: 'turn', index: turns.length - 1 });
        } else if (b.type === 'tool_use') {
          if (b.name === 'StructuredOutput') { mark(rec, { type: 'answer' }); return; }
          var n = name(b.name), a = { kind: 'action', index: actions.length, id: b.id || null, tool: b.name || '?',
            name: n.name, family: n.family, input: b.input, rec: rec, result_rec: null, records: [rec],
            outcome: 'unfinished', duration_ms: null, text: null, images: [], started: ts };
          actions.push(a);
          turn.items.push({ kind: 'action', index: a.index });
          if (a.id) open[a.id] = a;
          mark(rec, { type: 'action', index: a.index });
        } else if (b.type === 'tool_result') {
          var use = b.tool_use_id && open[b.tool_use_id];
          if (!use) {
            use = { kind: 'action', index: actions.length, id: b.tool_use_id || null, tool: '', name: 'Result', family: 'other',
              input: null, rec: rec, records: [], started: null, orphan: true };
            actions.push(use);
            turn.items.push({ kind: 'action', index: use.index });
          }
          delete open[b.tool_use_id];
          var parts = resultParts(b);
          use.result_rec = rec;
          use.record = r;
          use.records.push(rec);
          use.outcome = b.is_error ? 'error' : 'ok';
          use.text = parts.text;
          use.images = parts.images;
          use.duration_ms = use.started != null && ts != null ? Math.max(0, ts - use.started) : null;
          mark(rec, { type: 'action', index: use.index });
        } else {
          mark(rec, { type: 'system' });
        }
      });
      if (!at[rec]) mark(rec, { type: 'system' });
      place(rec);
    });

    var url = '', consoleErrors = 0;
    actions.forEach(function (a) {
      a.console_new = 0;
      if (a.family === 'browser') {
        a.info = browserInfo(a.text || '');
        a.url_before = url;
        if (a.info.url) {
          /* the console count is the page's so far: flag only what this action added */
          a.console_new = Math.max(0, a.info.errors - (pathOf(a.info.url) === pathOf(url) ? consoleErrors : 0));
          url = a.info.url;
          consoleErrors = a.info.errors;
        }
      }
      /* each worked out once: the summary, the kind, and the views read them */
      a.read_lines = a.tool === 'Read' && a.text != null ? readLines(a.text) : null;
      a.added = 0;
      a.removed = 0;
      edits(a.tool, a.input).forEach(function (e) { var d = diff(e.old, e.new); a.added += d.added; a.removed += d.removed; });
      a.kind_of = kind(a.tool, a.text, a.images, a.read_lines);
      a.summary = a.orphan ? '' : summary(a);
      a.failure_lines = a.tool === 'Bash' ? failureLines(a.text || '') : [];
      var code = /^Exit code (\d+)/.exec(a.text || '');
      a.exit_code = a.tool === 'Bash' && a.outcome !== 'unfinished' ? (code ? +code[1] : (a.outcome === 'ok' ? 0 : null)) : null;
      var st = model.stats;
      st.actions += 1;
      st.families[a.family] = (st.families[a.family] || 0) + 1;
      if (a.outcome === 'error') { st.errors += 1; model.errors.push(a.index); }
      var path = a.input && typeof a.input === 'object' ? str(a.input.file_path) || str(a.input.notebook_path) : '';
      if (path && a.family === 'edit') {
        var f = st.files[path] || (st.files[path] = { added: 0, removed: 0 });
        f.added += a.added;
        f.removed += a.removed;
      }
      delete a.started;
    });
    return model;
  }

  /* What shows record `rec`, or null. */
  function actionOf(model, rec) { return (model && model.at[rec]) || null; }

  DL.actions = {
    build: build, name: name, summary: summary, kind: kind, failureLines: failureLines, diff: diff,
    readLines: readLines, clip: clip, answer: answer, actionOf: actionOf,
    known: function (tool) { return Object.prototype.hasOwnProperty.call(BUILTIN, tool) || name(tool).family === 'browser'; },
    browserInfo: browserInfo, target: target, firstInput: firstInput, edits: edits, resultParts: resultParts,
    FAMILIES: FAMILIES
  };
})(window.DL = window.DL || {});
