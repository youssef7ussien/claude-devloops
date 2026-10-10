/* views/conversation.js: `#/call/<loop>/<seq>` — one Claude call and its conversation, drawn from
   the model of actions.js (User Story 8, FR-021, FR-021a–FR-021f, research R-15).

   The header has the call's facts and totals; then the call's answer as a result card (its tasks,
   or the criteria it checked); its prompt and settings files with where each prompt part came
   from; "Files changed" with lines added and removed, each jumping to the change. The
   conversation starts with a "Prompt" row; each of Claude's messages heads the actions after it,
   with the time since the call started; each action is one row (icon, name, summary, ✓/✕,
   duration, a "failure lines" or console-errors flag) that opens to its input and its result,
   shown by kind (Markdown, images that open in the viewer, a diff, numbered lines, a terminal).
   A summary line counts the actions; chips filter to the failed actions ("Errors only (N)") or to
   one kind; "System records" shows, each in its place, the records that are not messages.
   `?at=<record>` opens and scrolls to whatever shows that record. Nothing is lost: long text
   shows its first and last lines with "Show all". Row bodies are built when first opened. */
(function (DL) {
  'use strict';

  var ICONS = { shell: 'terminal', read: 'file', edit: 'edit', browser: 'browser', web: 'globe', other: 'tool' };
  var filters = {}; /* per call: {errors, family}, kept while the view refreshes */

  /* --- formatting (pure; tested under node) ---------------------------------------------------- */

  /* A duration in milliseconds: "0.4s" under ten seconds, else as DL.fmt.duration. */
  function ms(v) {
    if (v == null) return '';
    return v < 10000 ? (v / 1000).toFixed(1) + 's' : DL.fmt.duration(v / 1000);
  }

  /* Time since the call started: "+1:05". */
  function since(v) {
    if (v == null) return '';
    var s = Math.max(0, Math.round(v / 1000)), m = Math.floor(s / 60);
    return '+' + m + ':' + String(s % 60).padStart(2, '0');
  }

  function lineCount(text) { return text ? String(text).replace(/\n$/, '').split('\n').length : 0; }

  function ext(path) { var m = /\.([a-z0-9]+)$/i.exec(path || ''); return m ? m[1] : ''; }

  function count(n, one, many) { return n + ' ' + (n === 1 ? one : many); }

  /* --- long text ------------------------------------------------------------------------------- */

  /* `lines` drawn by `one(line)` into `box`: the first 15 and last 10 when there are more than
     40, with "Show all" between them. */
  function clipped(box, lines, one) {
    var c = DL.actions.clip(lines);
    c.head.forEach(function (l) { box.appendChild(one(l)); });
    if (!c.hidden) return box;
    var more = DL.el('div', 'more');
    more.appendChild(DL.btn('⋯ ' + count(c.hidden, 'more line', 'more lines') + ' · Show all', { cls: 'ghost small', on: function () {
      var frag = document.createDocumentFragment();
      lines.slice(c.head.length, lines.length - c.tail.length).forEach(function (l) { frag.appendChild(one(l)); });
      box.replaceChild(frag, more);
    } }));
    box.appendChild(more);
    c.tail.forEach(function (l) { box.appendChild(one(l)); });
    return box;
  }

  /* Text as lines; the lines at the indexes `hot` are marked as failures. */
  function textBlock(text, cls, hot) {
    var lines = String(text || '').replace(/\n$/, '').split('\n'), marks = {};
    (hot || []).forEach(function (k) { marks[k] = 1; });
    return clipped(DL.el('div', 'out ' + (cls || '')), lines.map(function (l, k) { return [l, k]; }), function (p) {
      return DL.el('div', 'ln' + (marks[p[1]] ? ' fail' : ''), p[0] || '​');
    });
  }

  function code(text, lang) {
    if (lineCount(text) <= 40 && DL.hl && DL.hl.codeView) return DL.hl.codeView(text, lang, { ln: false });
    return textBlock(text, 'mono');
  }

  /* --- results by kind ---------------------------------------------------------------------------- */

  function images(a, d) {
    if (!a.images.length) return null;
    var row = DL.el('div', 'thumbs');
    var refs = a.images.map(function (img, k) {
      var name = 'call-' + d.seq + '-action-' + (a.index + 1) + (a.images.length > 1 ? '-' + (k + 1) : '') + '.' + img.media_type.split('/')[1];
      return { id: 'inline:' + d.loop + ':' + d.seq + ':' + a.index + ':' + k, kind: 'image', path: name,
        inline: { url: 'data:' + img.media_type + ';base64,' + img.data } };
    });
    refs.forEach(function (ref) {
      var b = DL.el('button', 'thumb');
      b.type = 'button';
      b.title = 'Open ' + ref.path;
      var im = DL.el('img');
      im.alt = ref.path;
      im.loading = 'lazy';
      im.src = ref.inline.url;
      b.appendChild(im);
      b.addEventListener('click', function () { DL.viewer.open(ref, { list: refs, opener: b }); });
      row.appendChild(b);
    });
    return row;
  }

  function pageLine(info) {
    if (!info.url) return null;
    var p = DL.add(DL.el('p', 'page small'), 'Now on ', DL.el('code', null, info.url), info.title ? ' · ' + info.title : '');
    if (info.errors) DL.add(p, ' ', DL.el('span', 'flag bad', 'console ' + count(info.errors, 'error', 'errors')));
    return p;
  }

  function browserResult(a) {
    var info = a.info, parts = [];
    if (info.code) parts.push(DL.add(DL.el('p', 'ran small'), 'Ran ', DL.el('code', null, info.code.replace(/^await /, '').replace(/;$/, ''))));
    if (info.error) parts.push(textBlock(info.error, 'err'));
    if (info.result) parts.push(/^(#|- |\d+\. )/m.test(info.result) ? DL.md.render(info.result) : textBlock(info.result, 'mono'));
    parts.push(pageLine(info));
    if (info.snapshot) {
      var det = DL.el('details', 'snap');
      det.appendChild(DL.el('summary', 'small', 'Page snapshot · ' + count(lineCount(info.snapshot), 'line', 'lines')));
      det.addEventListener('toggle', function once() {
        det.removeEventListener('toggle', once);
        det.appendChild(code(info.snapshot, 'yaml'));
      });
      parts.push(det);
    }
    if (!info.code && !info.error && !info.result && !info.url && !info.snapshot && a.text) parts.push(DL.md.render(a.text));
    return parts;
  }

  /* The language of the file a tool call names, by its extension. */
  function langOfInput(a) { return DL.hl ? DL.hl.langOf(ext(a.input && a.input.file_path)) : 'text'; }

  /* `parent` with one line of code highlighted (FR-033). */
  function codeLine(parent, text, lang) {
    if (!text || !DL.hl || lang === 'text') return DL.add(parent, text);
    DL.hl.tokenize(text, lang).forEach(function (t) { parent.appendChild(t[0] ? DL.el('span', 't-' + t[0], t[1]) : document.createTextNode(t[1])); });
    return parent;
  }

  function readResult(a) {
    var lines = a.read_lines || [], lang = langOfInput(a);
    return clipped(DL.el('div', 'out numbered'), lines, function (l) {
      var text = DL.el('span', 'c');
      if (l.n != null && l.text) codeLine(text, l.text, lang);
      else text.appendChild(document.createTextNode(l.text || '\u200b'));
      return DL.add(DL.el('div', 'ln'), DL.el('span', 'n', l.n == null ? '' : String(l.n)), text);
    });
  }

  /* An edit's diff, with three lines of context around each change; each line's code highlighted
     by the file's language (FR-033). */
  function diffView(a) {
    var box = DL.el('div', 'diffs'), lang = langOfInput(a);
    DL.actions.edits(a.tool, a.input).forEach(function (e) {
      var d = DL.actions.diff(e.old, e.new), keep = {}, rows = [], gap = false;
      d.lines.forEach(function (l, k) { if (l.op !== ' ') for (var j = k - 3; j <= k + 3; j++) keep[j] = 1; });
      d.lines.forEach(function (l, k) {
        if (!keep[k]) { if (!gap) rows.push(null); gap = true; return; }
        gap = false;
        rows.push(l);
      });
      box.appendChild(clipped(DL.el('div', 'out diff'), rows, function (l) {
        if (!l) return DL.el('div', 'ln gap', '⋯');
        return codeLine(DL.el('div', 'ln ' + (l.op === '+' ? 'add' : l.op === '-' ? 'del' : 'ctx'), l.op === ' ' ? '  ' : l.op + ' '), l.text, lang);
      }));
    });
    return box;
  }

  function resultView(a, d) {
    if (a.outcome === 'unfinished') return DL.el('p', 'muted small', 'No result was recorded (the call ended first).');
    var parts = [images(a, d)], text = a.text || '';
    if (a.outcome === 'error' && a.kind_of !== 'terminal' && a.kind_of !== 'browser') { parts.push(textBlock(text, 'err')); return parts; }
    switch (a.kind_of) {
      case 'image': break;
      case 'browser': parts = parts.concat(browserResult(a)); break;
      case 'read': parts.push(readResult(a)); break;
      case 'edit': parts.push(DL.el('p', 'muted small', text.split('\n')[0])); break;
      case 'terminal':
        var shift = /^Exit code \d+\n/.test(text) ? 1 : 0, head = DL.el('p', 'small term-head');
        if (a.exit_code != null) head.appendChild(DL.el('span', 'flag' + (a.exit_code ? ' bad' : ''), 'exit ' + a.exit_code));
        if (a.failure_lines.length) DL.add(head, ' ', DL.el('span', 'flag bad', count(a.failure_lines.length, 'failure line', 'failure lines')));
        parts.push(head, textBlock(shift ? text.replace(/^Exit code \d+\n/, '') : text, 'term',
          a.failure_lines.map(function (k) { return k - shift; })));
        break;
      case 'markdown': parts.push(DL.md.render(text)); break;
      default:
        var pretty = DL.hl ? DL.hl.pretty(text) : text;
        if (!text.trim()) parts.push(DL.el('p', 'muted small', 'No output.'));
        else parts.push(pretty !== text ? code(pretty, 'json') : textBlock(text, 'mono'));
    }
    return parts;
  }

  function inputView(a) {
    var i = a.input && typeof a.input === 'object' ? a.input : {};
    if (a.tool === 'Bash') return code('$ ' + (i.command || ''), 'shell');
    if (a.tool === 'Edit' || a.tool === 'MultiEdit' || a.tool === 'Write') {
      return [DL.add(DL.el('p', 'small'), DL.el('code', null, i.file_path || '')), diffView(a)];
    }
    if (a.tool === 'Read') return DL.add(DL.el('p', 'small'), DL.el('code', null, i.file_path || ''));
    if (a.family === 'browser' && a.info && a.info.code) return null; /* the code it ran says it */
    if (!Object.keys(i).length) return null;
    var det = DL.el('details', 'input');
    DL.add(det, DL.el('summary', 'small', 'Input'), code(JSON.stringify(i, null, 2), 'json'));
    det.open = !DL.actions.known(a.tool); /* a tool with no rule of its own: its input is the summary */
    return det;
  }

  /* --- rows ------------------------------------------------------------------------------------- */

  function mark(ok, label) {
    var m = DL.el('span', 'oc ' + (ok === true ? 'good' : ok === false ? 'bad' : 'muted'), ok === true ? '✓' : ok === false ? '✕' : '…');
    m.setAttribute('role', 'img');
    m.setAttribute('aria-label', label);
    m.title = label;
    return m;
  }

  function lazy(det, make) {
    det.build = function () {
      if (det.built) return;
      det.built = true;
      det.appendChild(DL.add(DL.el('div', 'body'), make()));
    };
    det.addEventListener('toggle', function () { if (det.open) det.build(); });
    return det;
  }

  function actionRow(a, d) {
    var det = DL.el('details', 'act ' + a.family + (a.outcome === 'error' ? ' err' : '')), sum = DL.el('summary');
    det.id = 'act-' + a.index;
    det.dataset.family = a.family;
    det.dataset.outcome = a.outcome;
    var flags = DL.el('span', 'flags');
    if (a.failure_lines.length) flags.appendChild(DL.el('span', 'flag bad', count(a.failure_lines.length, 'failure line', 'failure lines')));
    if (a.console_new) flags.appendChild(DL.el('span', 'flag warn', 'console +' + a.console_new));
    if (a.images.length) flags.appendChild(DL.icon('image'));
    DL.add(sum, DL.icon('chev', 'chev'), DL.icon(ICONS[a.family] || 'tool', 'fam'), DL.el('span', 'name', a.name),
      DL.el('span', 'sum', a.summary || ''), flags,
      mark(a.outcome === 'ok' ? true : a.outcome === 'error' ? false : null, a.outcome === 'ok' ? 'Succeeded' : a.outcome === 'error' ? 'Failed' : 'Unfinished'),
      DL.el('span', 'dur', ms(a.duration_ms)));
    sum.title = a.tool;
    det.appendChild(sum);
    return lazy(det, function () { return [inputView(a), resultView(a, d)]; });
  }

  function promptRow(m, d) {
    var det = DL.el('details', 'act prompt'), sum = DL.el('summary'), text = m.prompt.text;
    det.id = 'prompt';
    DL.add(sum, DL.icon('chev', 'chev'), DL.icon('chat', 'fam'), DL.el('span', 'name', 'Prompt'),
      DL.el('span', 'sum', d.step + ' step · ' + count(lineCount(text), 'line', 'lines') + (d.prompt ? ' · opens in the viewer' : '')),
      DL.el('span', 'dur', '+0:00'));
    det.appendChild(sum);
    if (!d.prompt) return lazy(det, function () { return textBlock(text, 'mono'); });
    sum.addEventListener('click', function (ev) {
      ev.preventDefault();
      DL.viewer.open(d.prompt, { list: [d.prompt, d.settings].filter(Boolean), opener: sum });
    });
    return det;
  }

  function thoughtRow(t) {
    if (!t.text.trim()) return DL.el('div', 'thought', 'thought for ' + ms(t.ms));
    var det = DL.el('details', 'thought');
    DL.add(det, DL.el('summary', null, 'Thinking' + (t.ms != null ? ' · ' + ms(t.ms) : '')), textBlock(t.text, 'mono'));
    return det;
  }

  /* --- the result card ---------------------------------------------------------------------------- */

  /* The call's answer; its plan ids show what they say on hover and focus (`refs`, FR-020d). */
  function resultCard(m, refs) {
    var ans = m.answer, i = ans.input, card = DL.el('section', 'card result-card'), head = DL.el('h3'), ul = DL.el('ul', 'answer');
    card.id = 'answer';
    card.appendChild(head);
    if (ans.shape === 'criteria') {
      var passed = i.criteria.filter(function (c) { return c && c.passed; }).length, all = passed === i.criteria.length;
      DL.add(head, mark(all, all ? 'All passed' : 'Some failed'), ' Call result · ', passed + ' of ' + count(i.criteria.length, 'criterion', 'criteria') + ' passed');
      i.criteria.forEach(function (c) {
        c = c || {};
        ul.appendChild(DL.add(DL.el('li'), mark(!!c.passed, c.passed ? 'Passed' : 'Failed'),
          DL.add(DL.el('div'), DL.add(DL.el('strong'), DL.ref(c.criterion_id || c.id || '', refs)), ' ', c.observed || '')));
      });
      card.appendChild(ul);
      return card;
    }
    if (ans.shape === 'tasks') {
      var done = i.tasks.filter(function (t) { return t && (t.status === 'implemented' || t.status === 'done'); }).length;
      var bits = [done + ' of ' + count(i.tasks.length, 'task', 'tasks') + ' implemented'];
      if (Array.isArray(i.files_changed)) bits.push(count(i.files_changed.length, 'file', 'files') + ' changed');
      if (Array.isArray(i.assumptions) && i.assumptions.length) bits.push(count(i.assumptions.length, 'assumption', 'assumptions'));
      if (Array.isArray(i.needs_input) && i.needs_input.length) bits.push(count(i.needs_input.length, 'question', 'questions'));
      DL.add(head, mark(done === i.tasks.length, done === i.tasks.length ? 'All implemented' : 'Not all implemented'), ' Call result · ', bits.join(' · '));
      i.tasks.forEach(function (t) {
        t = t || {};
        var ok = t.status === 'implemented' || t.status === 'done' ? true : t.status === 'failed' || t.status === 'not-implemented' ? false : null;
        ul.appendChild(DL.add(DL.el('li'), mark(ok, t.status || ''),
          DL.add(DL.el('div'), DL.add(DL.el('strong'), DL.ref(t.task_id || t.id || '', refs)), ' ', t.note || t.status || '')));
      });
      card.appendChild(ul);
      if (Array.isArray(i.files_changed) && i.files_changed.length) {
        card.appendChild(DL.add(DL.el('p', 'small'), DL.el('span', 'muted', 'Files changed: '),
          i.files_changed.map(function (f, k) { return [k ? ', ' : null, DL.el('code', null, String(f))]; })));
      }
      (i.assumptions || []).forEach(function (x) {
        card.appendChild(DL.add(DL.el('p', 'small note'), DL.el('strong', null, 'Assumption '), (x && x.text) || '',
          x && x.affects && x.affects.length ? DL.add(DL.el('span', 'refs'), ' · affects ', DL.refList(x.affects, refs)) : null));
      });
      (i.needs_input || []).forEach(function (q) {
        card.appendChild(DL.add(DL.el('p', 'small note'), DL.el('strong', null, 'Question '), (q && q.question) || '',
          q && q.requirement_refs && q.requirement_refs.length ? DL.add(DL.el('span', 'refs'), ' · ', DL.refList(q.requirement_refs, refs)) : null,
          q && q.suggested_answer ? DL.el('span', 'muted', ' — suggested: ' + q.suggested_answer) : null));
      });
      return card;
    }
    head.appendChild(document.createTextNode('Call result'));
    var dl = DL.el('dl', 'facts');
    Object.keys(i).forEach(function (k) {
      var v = i[k];
      var shown = Array.isArray(v) ? count(v.length, 'item', 'items') : v && typeof v === 'object' ? count(Object.keys(v).length, 'field', 'fields') :
        String(v).length > 200 ? String(v).slice(0, 199) + '…' : String(v);
      DL.add(dl, DL.el('dt', null, k), DL.el('dd', null, shown));
    });
    card.appendChild(dl);
    return card;
  }

  /* --- header ------------------------------------------------------------------------------------- */

  function header(d) {
    var t = d.totals, facts = DL.el('dl', 'facts');
    [['Loop', DL.link(d.routes.loop, d.loop)], ['Step', d.step], ['Milestone', d.milestone_id || 'planning'],
      ['Trial', d.routes.trial ? DL.link(d.routes.trial, String(d.trial)) : (d.trial == null ? '–' : String(d.trial))],
      ['Model', d.model || '–'], ['Session', DL.el('code', null, d.session_id || '–')],
      ['Started', DL.fmt.time(d.started_at)], ['Turns', d.num_turns == null ? '–' : String(d.num_turns)],
      ['Result', d.failure_class && d.failure_class !== 'none' ? DL.pill('failed', 'trial') : (d.subtype || '–')]
    ].forEach(function (f) { DL.add(facts, DL.el('dt', null, f[0]), DL.add(DL.el('dd'), f[1])); });
    return [facts, DL.kpis([
      DL.kpi('Duration', DL.fmt.duration(d.duration_ms == null ? null : d.duration_ms / 1000)),
      DL.kpi('Cost', DL.fmt.money(t.cost)),
      DL.kpi('Tokens', DL.tokens(t))
    ], true, 'Call totals')];
  }

  function prompt(d) {
    var files = [d.prompt, d.settings].filter(Boolean);
    var bar = DL.el('div', 'toolbar');
    if (d.prompt) bar.appendChild(DL.viewer.link(d.prompt, 'Prompt', files));
    if (d.settings) bar.appendChild(DL.viewer.link(d.settings, 'Settings', files));
    DL.$$('a', bar).forEach(function (a) { a.classList.add('btn'); });
    var rows = (d.prompt_sources || []).map(function (p) {
      return DL.add(DL.el('tr'), DL.td(DL.el('code', null, p.part)), DL.td(p.source),
        DL.td(DL.el('code', null, p.path), 'small'));
    });
    return [bar, rows.length ? DL.table([['Prompt part'], ['Source'], ['File']], rows) : null];
  }

  function delta(c) {
    return DL.add(DL.el('span', 'delta'), DL.el('span', 'add', '+' + c.added), ' ', DL.el('span', 'del', '−' + c.removed));
  }

  function changedList(d, m, go) {
    if (!d.files_changed.length) return DL.el('p', 'muted', 'This call changed no file.');
    var ul = DL.el('ul', 'files');
    d.files_changed.forEach(function (f) {
      var href = DL.router.href('call', { loop: d.loop, seq: d.seq }, { at: f.block });
      var a = DL.link(href, 'Go to the change');
      a.addEventListener('click', function (ev) {
        if (ev.button || ev.metaKey || ev.ctrlKey || ev.shiftKey) return;
        ev.preventDefault();
        history.replaceState(null, '', href); /* the address says where the reader is, without a reload */
        go(f.block);
      });
      ul.appendChild(DL.add(DL.el('li'), DL.el('code', null, f.path), ' ', delta(f), /* the server's counts: all its changes */
        ' ', DL.el('span', 'muted small', f.tool), ' · ', a));
    });
    return ul;
  }

  function summaryLine(m, d) {
    var p = DL.el('p', 'conv-sum'), st = m.stats, total = { added: 0, removed: 0 };
    p.appendChild(DL.el('strong', null, count(st.actions, 'action', 'actions')));
    Object.keys(DL.actions.FAMILIES).forEach(function (f) {
      if (st.families[f]) DL.add(p, DL.add(DL.el('span', 'fam-count'), DL.icon(ICONS[f]), st.families[f] + ' ' + DL.actions.FAMILIES[f].toLowerCase()));
    });
    Object.keys(st.files).forEach(function (k) { total.added += st.files[k].added; total.removed += st.files[k].removed; });
    if (total.added || total.removed) p.appendChild(delta(total));
    DL.add(p, DL.el('span', st.errors ? 'bad' : 'muted', count(st.errors, 'error', 'errors')),
      DL.el('span', 'muted', DL.fmt.duration(d.duration_ms == null ? null : d.duration_ms / 1000)));
    return p;
  }

  /* --- the conversation ----------------------------------------------------------------------------- */

  /* A record nothing else shows (FR-021f), folded, in its place; hidden until "System records". */
  function systemRow(d, rec) {
    var r = d.records[rec], det = DL.el('details', 'act sys'), type = r && r.raw != null ? 'not JSON' : (r && r.type) || 'record';
    det.id = 'rec-' + rec;
    DL.add(det, DL.add(DL.el('summary'), DL.icon('chev', 'chev'), DL.el('span', 'name', type), DL.el('span', 'sum', 'record ' + rec)));
    return lazy(det, function () {
      return r && r.raw != null ? textBlock(String(r.raw), 'mono') : code(JSON.stringify(r, null, 2), 'json');
    });
  }

  function render(data, params, el, query, refresh) {
    var d = data[0], key = d.loop + '/' + d.seq, f = filters[key] || (filters[key] = { errors: false, family: null });
    DL.add(el, DL.head('Call #' + d.seq + ' · ' + d.step, d.failure_class && d.failure_class !== 'none' ? DL.pill('failed', 'trial') : null,
      d.loop + (d.milestone_id ? ' · ' + d.milestone_id + ' trial ' + d.trial : ' · planning')), header(d));

    if (d.conversation === 'unavailable') {
      DL.add(el, DL.el('h3', null, 'Prompt'), prompt(d), DL.el('h3', null, 'Conversation'), DL.add(DL.el('p', 'callout warn'),
        'The conversation is unavailable (' + (d.unavailable_reason || 'unknown') + '). Session ',
        DL.el('code', null, d.session_id || '–'), '.'));
      return;
    }

    var m = DL.actions.build(d.records), conv = DL.el('div', 'conv');
    if (m.answer) el.appendChild(resultCard(m, d.refs));
    m.before.forEach(function (rec) { conv.appendChild(systemRow(d, rec)); });
    if (m.prompt) conv.appendChild(promptRow(m, d));
    m.turns.forEach(function (t, k) {
      var box = DL.el('div', 'turn');
      box.id = 'turn-' + k;
      if (t.text != null) {
        box.appendChild(DL.add(DL.el('div', 'said'), DL.add(DL.el('div', 'who'), 'Claude', DL.el('span', 'since', since(t.elapsed_ms))),
          DL.md.render(t.text)));
      }
      t.items.forEach(function (it) {
        if (it.kind === 'action') box.appendChild(actionRow(m.actions[it.index], d));
        else if (it.kind === 'thought') box.appendChild(thoughtRow(it));
        else if (it.kind === 'system') box.appendChild(systemRow(d, it.rec));
        else box.appendChild(DL.add(DL.el('div', 'user-msg'), DL.el('div', 'who', 'User'), textBlock(it.text, 'mono')));
      });
      if (!box.childNodes.length) return;
      /* a turn of system records only shows with them */
      if (!DL.$$(':scope > :not(.sys)', box).length) box.classList.add('sys-only');
      conv.appendChild(box);
    });

    function node(place) {
      if (!place) return null;
      if (place.type === 'action') return DL.$('#act-' + place.index, conv);
      if (place.type === 'turn') return DL.$('#turn-' + place.index, conv);
      if (place.type === 'prompt') return DL.$('#prompt', conv);
      if (place.type === 'answer') return DL.$('#answer', el);
      return null;
    }
    function reveal(n) {
      if (!n) return;
      DL.$$('.hit', el).forEach(function (x) { x.classList.remove('hit'); });
      if (n.tagName === 'DETAILS') { if (n.build) n.build(); n.open = true; }
      n.classList.add('hit');
      n.scrollIntoView({ block: 'center' });
    }

    /* filters */
    var chips = DL.el('div', 'chips'), famChips = {};
    var chipErr = DL.btn('Errors only (' + m.errors.length + ')', { cls: 'chip' });
    chipErr.disabled = !m.errors.length;
    chipErr.addEventListener('click', function () { f.errors = !f.errors; apply(); });
    chips.appendChild(chipErr);
    Object.keys(DL.actions.FAMILIES).forEach(function (fam) {
      if (!m.stats.families[fam]) return;
      var c = DL.btn(DL.actions.FAMILIES[fam], { cls: 'chip', icon: ICONS[fam] });
      c.addEventListener('click', function () { f.family = f.family === fam ? null : fam; apply(); });
      famChips[fam] = c;
      chips.appendChild(c);
    });
    function apply() {
      var on = !!(f.errors || f.family);
      chipErr.setAttribute('aria-pressed', String(f.errors));
      Object.keys(famChips).forEach(function (k) { famChips[k].setAttribute('aria-pressed', String(f.family === k)); });
      conv.classList.toggle('filtered', on);
      DL.$$('.turn', conv).forEach(function (t) {
        var any = false;
        DL.$$('details.act', t).forEach(function (a) {
          var show = (!f.errors || a.dataset.outcome === 'error') && (!f.family || a.dataset.family === f.family);
          a.hidden = !show;
          if (show) any = true;
        });
        t.hidden = on && !any;
      });
    }
    function unfilter(n) {
      if (n && (n.hidden || (n.closest('.turn') && n.closest('.turn').hidden) || n.id === 'prompt')) { f.errors = false; f.family = null; apply(); }
    }

    var sysBtn = DL.btn('System records', { cls: 'chip' });
    function setSys(on) {
      conv.classList.toggle('show-sys', on);
      sysBtn.setAttribute('aria-pressed', String(on));
    }
    setSys(false);
    sysBtn.addEventListener('click', function () { setSys(!conv.classList.contains('show-sys')); });

    function go(rec) {
      var place = DL.actions.actionOf(m, rec);
      if (place && place.type === 'system') { var s = DL.$('#rec-' + rec, conv); setSys(true); unfilter(s); reveal(s); return; }
      var n = node(place);
      unfilter(n);
      reveal(n);
    }
    var bar = DL.add(DL.el('div', 'toolbar conv-bar'),
      chips, DL.el('span', 'spacer'), sysBtn,
      DL.btn('Expand all', { on: function () {
        DL.$$('details.act:not(.sys)', conv).forEach(function (x) { if (!x.hidden && x.id !== 'prompt') { if (x.build) x.build(); x.open = true; } });
      } }),
      DL.btn('Collapse all', { on: function () { DL.$$('details', conv).forEach(function (x) { x.open = false; }); } }));

    DL.add(el, DL.el('h3', null, 'Prompt'), prompt(d), DL.el('h3', null, 'Files changed'), changedList(d, m, go),
      DL.el('h3', null, 'Conversation' + (d.conversation === 'history' ? ' (read from Claude Code’s history)' : '')),
      summaryLine(m, d), bar, d.records.length ? conv : DL.el('p', 'muted', 'The conversation has no records.'));
    apply();

    var target = query && query.at != null && query.at !== '' ? +query.at : null;
    if (target != null && !refresh) setTimeout(function () { if (el.isConnected) go(target); }, 0);
  }

  /* `change(action)`: an Edit, MultiEdit, or Write action's diff, for the trial view's change
     dialog (FR-018d). */
  DL.conversation = { since: since, ms: ms, change: diffView };

  DL.router.register('call', {
    title: function (params) { return params.loop + ' · call #' + params.seq; },
    data: function (params) { return ['calls/' + params.loop + '/' + encodeURIComponent(params.seq)]; },
    render: render
  });
})(window.DL = window.DL || {});
