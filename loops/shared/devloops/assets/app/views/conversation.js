/* views/conversation.js: `#/call/<loop>/<seq>` — one Claude call and its conversation (FR-021,
   002 contracts/full-dashboard.md "Conversation rendering"). The header has the call's facts and
   totals, its prompt and settings files (opened in the viewer) with where each prompt part came
   from, and "N errors" with previous and next buttons (keys `[` and `]`). "Files changed" lists each
   path once, jumping to the tool call that last changed it. The records, in order: the user's text
   (collapsed over 40 lines), Claude's text as Markdown, thinking collapsed, each tool call folded to
   one line "Tool: <name> — <hint>", each result collapsed over 12 lines unless it is an error
   (errors marked), and other records under "System records", hidden until shown. Nothing is
   truncated; folding only hides text until it is opened. `?at=<record>` unfolds that record and
   scrolls to it. */
(function (DL) {
  'use strict';

  var USER_LINES = 40, RESULT_LINES = 12, HINT_CHARS = 160;
  var active = null; /* the mounted conversation: {el, step(d)} for the `[` and `]` keys */
  var keysBound = false;

  /* --- pure helpers (tested under node) ------------------------------------------------------- */

  function oneLine(text) {
    var s = String(text).replace(/\s+/g, ' ').trim();
    return s.length > HINT_CHARS ? s.slice(0, HINT_CHARS - 1) + '…' : s;
  }

  /* The one-line hint of a tool use: its command, path, URL, or pattern; '' when it has none. */
  function hint(block) {
    var i = block && block.input && typeof block.input === 'object' ? block.input : {};
    var keys = ['command', 'file_path', 'notebook_path', 'url', 'pattern', 'path', 'query', 'description', 'prompt'];
    for (var k = 0; k < keys.length; k++) {
      if (typeof i[keys[k]] === 'string' && i[keys[k]].trim()) return oneLine(i[keys[k]]);
    }
    return '';
  }

  function lineCount(text) { return text ? String(text).split('\n').length : 0; }

  /* The text of a message content: a string, or its text parts joined. */
  function contentText(content) {
    if (typeof content === 'string') return content;
    if (!Array.isArray(content)) return content == null ? '' : JSON.stringify(content, null, 2);
    return content.map(function (p) {
      if (typeof p === 'string') return p;
      if (p && p.type === 'text') return p.text || '';
      if (p && p.type === 'image') return '[image]';
      return JSON.stringify(p, null, 2);
    }).join('\n');
  }

  /* A conversation's records as the items the view shows, in order: `{rec, kind, …}` with kind
     user | claude | thinking | tool | result | system. A tool's result names its tool; `folded`
     says whether an item starts collapsed. */
  function fold(records) {
    var out = [], tools = {};
    (records || []).forEach(function (r, rec) {
      if (!r || typeof r !== 'object' || r.raw != null) {
        out.push({ rec: rec, kind: 'system', type: 'not JSON', text: r && r.raw != null ? String(r.raw) : JSON.stringify(r), folded: true });
        return;
      }
      var m = r.message, role = m && typeof m === 'object' ? (m.role || r.type) : null;
      if (!m || typeof m !== 'object' || (role !== 'user' && role !== 'assistant')) {
        out.push({ rec: rec, kind: 'system', type: r.type || 'record', text: JSON.stringify(r, null, 2), folded: true });
        return;
      }
      var content = m.content;
      if (typeof content === 'string' || !Array.isArray(content)) content = [{ type: 'text', text: contentText(content) }];
      content.forEach(function (b) {
        if (!b || typeof b !== 'object') return;
        if (b.type === 'text') {
          var text = b.text || '';
          if (role === 'user') out.push({ rec: rec, kind: 'user', text: text, folded: lineCount(text) > USER_LINES });
          else out.push({ rec: rec, kind: 'claude', text: text, folded: false });
        } else if (b.type === 'thinking' || b.type === 'redacted_thinking') {
          out.push({ rec: rec, kind: 'thinking', text: b.thinking || b.data || '', folded: true });
        } else if (b.type === 'tool_use') {
          tools[b.id] = b.name;
          out.push({ rec: rec, kind: 'tool', id: b.id || null, name: b.name || '?', hint: hint(b), input: b.input, folded: true });
        } else if (b.type === 'tool_result') {
          var t = contentText(b.content), error = !!b.is_error;
          out.push({ rec: rec, kind: 'result', id: b.tool_use_id || null, tool: tools[b.tool_use_id] || null,
            text: t, error: error, folded: !error && lineCount(t) > RESULT_LINES });
        } else {
          out.push({ rec: rec, kind: 'system', type: b.type || 'block', text: JSON.stringify(b, null, 2), folded: true });
        }
      });
    });
    return out;
  }

  /* --- drawing ---------------------------------------------------------------------------------- */

  function pre(text, lang) {
    if (lang && DL.hl && DL.hl.codeView) return DL.add(DL.el('pre'), DL.hl.codeView(text, lang, { ln: false }));
    return DL.el('pre', 'text', text);
  }

  function block(cls, label, body, folded, extra) {
    var det = DL.el('details', 'blk ' + cls), sum = DL.el('summary');
    det.open = !folded;
    DL.add(sum, DL.icon('chev', 'chev'), DL.el('span', 'who', label), extra || null);
    return DL.add(det, sum, body);
  }

  function toolBody(it) {
    var i = it.input && typeof it.input === 'object' ? it.input : {};
    var parts = [], path = i.file_path || i.notebook_path;
    if (path) parts.push(DL.add(DL.el('p', 'small'), 'Path: ', DL.el('code', null, path)));
    if (it.name === 'Bash' && typeof i.command === 'string') parts.push(pre(i.command, 'bash'));
    if (it.name === 'Edit' && (i.old_string != null || i.new_string != null)) {
      parts.push(DL.el('h5', null, 'Old text'), DL.el('pre', 'text old', i.old_string || ''),
        DL.el('h5', null, 'New text'), DL.el('pre', 'text new', i.new_string || ''));
    } else if (it.name === 'MultiEdit' && Array.isArray(i.edits)) {
      i.edits.forEach(function (e, k) {
        parts.push(DL.el('h5', null, 'Edit ' + (k + 1) + ': old text'), DL.el('pre', 'text old', (e && e.old_string) || ''),
          DL.el('h5', null, 'New text'), DL.el('pre', 'text new', (e && e.new_string) || ''));
      });
    } else if (it.name === 'Write' && typeof i.content === 'string') {
      parts.push(DL.el('h5', null, 'Content'), DL.el('pre', 'text new', i.content));
    }
    parts.push(DL.el('h5', null, 'Input'), pre(JSON.stringify(it.input == null ? null : it.input, null, 2), 'json'));
    return parts;
  }

  function item(it) {
    if (it.kind === 'user') return block('user', 'User', pre(it.text), it.folded, it.folded ? DL.el('span', 'muted small', DL.fmt.plural(lineCount(it.text), 'line')) : null);
    if (it.kind === 'claude') return DL.add(DL.el('div', 'blk claude'), DL.el('div', 'who', 'Claude'), DL.md.render(it.text));
    if (it.kind === 'thinking') return block('thinking', 'Thinking', pre(it.text), true);
    if (it.kind === 'tool') {
      return block('tool', 'Tool: ' + it.name, toolBody(it), true,
        it.hint ? DL.el('span', 'hint', '— ' + it.hint) : null);
    }
    if (it.kind === 'result') {
      var mark = it.error ? DL.add(DL.el('span', 'err-mark'), DL.icon('alert-circle'), 'Error') : null;
      return block('result' + (it.error ? ' err' : ''), 'Result' + (it.tool ? ' · ' + it.tool : ''), pre(it.text), it.folded,
        [mark, it.folded ? DL.el('span', 'muted small', DL.fmt.plural(lineCount(it.text), 'line')) : null]);
    }
    return block('system', it.type, pre(it.text, 'json'), true);
  }

  /* Unfold `node` and the blocks around it, scroll it into view, and mark it. */
  function reveal(node, conv) {
    if (!node) return;
    DL.$$('.rec.hit', conv).forEach(function (n) { n.classList.remove('hit'); });
    if (node.classList.contains('sys-only')) conv.classList.add('show-sys');
    DL.$$('details', node).forEach(function (d) { d.open = true; });
    node.classList.add('hit');
    node.scrollIntoView({ block: 'center' });
  }

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
      DL.kpi('Tokens', DL.tokens(t)),
      DL.kpi('Input', DL.fmt.tokens(t.tokens.input)),
      DL.kpi('Output', DL.fmt.tokens(t.tokens.output)),
      DL.kpi('Cache read', DL.fmt.tokens(t.tokens.cache_read))
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

  function changedList(d, go) {
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
      ul.appendChild(DL.add(DL.el('li'), DL.el('code', null, f.path), ' ', DL.el('span', 'muted small', f.tool), ' · ', a));
    });
    return ul;
  }

  function bindKeys() {
    if (keysBound) return;
    keysBound = true;
    document.addEventListener('keydown', function (ev) {
      if (!active || !active.el.isConnected || ev.ctrlKey || ev.metaKey || ev.altKey) return;
      if (ev.target && ev.target.closest && ev.target.closest('input, textarea, select, dialog')) return;
      if (ev.key === ']' || ev.key === '[') { ev.preventDefault(); active.step(ev.key === ']' ? 1 : -1); }
    });
  }

  function render(data, params, el, query, refresh) {
    var d = data[0], items = fold(d.records), errors = d.errors || [], at = -1;
    DL.add(el, DL.head('Call #' + d.seq + ' · ' + d.step, d.failure_class && d.failure_class !== 'none' ? DL.pill('failed', 'trial') : null,
      d.loop + (d.milestone_id ? ' · ' + d.milestone_id + ' trial ' + d.trial : ' · planning')), header(d));
    DL.add(el, DL.el('h3', null, 'Prompt'), prompt(d));

    if (d.conversation === 'unavailable') {
      DL.add(el, DL.el('h3', null, 'Conversation'), DL.add(DL.el('p', 'callout warn'),
        'The conversation is unavailable (' + (d.unavailable_reason || 'unknown') + '). Session ',
        DL.el('code', null, d.session_id || '–'), '.'));
      active = null;
      return;
    }

    var conv = DL.el('div', 'conv'), byRec = {};
    items.forEach(function (it) {
      var node = byRec[it.rec];
      if (!node) {
        node = byRec[it.rec] = DL.el('div', 'rec sys-only');
        node.dataset.rec = it.rec;
        if (errors.indexOf(it.rec) >= 0) node.classList.add('has-err');
        conv.appendChild(node);
      }
      if (it.kind !== 'system') node.classList.remove('sys-only');
      var made = item(it);
      if (it.kind === 'system') made.classList.add('sys');
      node.appendChild(made);
    });

    var count = DL.el('span', 'err-count', errors.length ? DL.fmt.plural(errors.length, 'error') : 'No errors');
    function go(rec) { reveal(byRec[rec], conv); }
    function step(dir) {
      if (!errors.length) return;
      at = at < 0 ? (dir > 0 ? 0 : errors.length - 1) : (at + dir + errors.length) % errors.length;
      count.textContent = 'Error ' + (at + 1) + ' of ' + errors.length;
      go(errors[at]);
    }
    var sys = DL.btn('System records', { cls: 'chip' });
    sys.setAttribute('aria-pressed', 'false');
    sys.dataset.chip = 'system';
    sys.addEventListener('click', function () {
      var on = !conv.classList.contains('show-sys');
      conv.classList.toggle('show-sys', on);
      sys.setAttribute('aria-pressed', String(on));
    });
    var bar = DL.add(DL.el('div', 'toolbar conv-bar'),
      DL.add(DL.el('span', errors.length ? 'errs on' : 'errs'), DL.icon('alert-circle'), count),
      DL.btn('Previous error', { icon: 'prev', iconOnly: true, key: '[', on: function () { step(-1); } }),
      DL.btn('Next error', { icon: 'next', iconOnly: true, key: ']', on: function () { step(1); } }),
      DL.el('span', 'spacer'), sys,
      DL.btn('Expand all', { on: function () { DL.$$('details', conv).forEach(function (x) { x.open = true; }); } }),
      DL.btn('Collapse all', { on: function () { DL.$$('details', conv).forEach(function (x) { x.open = false; }); } }));
    DL.$$('button', bar).slice(0, 2).forEach(function (b) { b.disabled = !errors.length; });

    DL.add(el, DL.el('h3', null, 'Files changed'), changedList(d, go),
      DL.el('h3', null, 'Conversation' + (d.conversation === 'history' ? ' (read from Claude Code’s history)' : '')),
      bar, items.length ? conv : DL.el('p', 'muted', 'The conversation has no records.'));

    active = { el: el, step: step };
    bindKeys();
    var target = query && query.at != null && query.at !== '' ? +query.at : null;
    if (target != null && !refresh) setTimeout(function () { if (el.isConnected) go(target); }, 0);
  }

  DL.conversation = { hint: hint, fold: fold };

  DL.router.register('call', {
    title: function (params) { return params.loop + ' · call #' + params.seq; },
    data: function (params) { return ['calls/' + params.loop + '/' + encodeURIComponent(params.seq)]; },
    render: render
  });
})(window.DL = window.DL || {});
