/* md.js: Markdown → a plain tree → DOM. `DL.md.parse(src)` builds the tree without the DOM (so it
   is tested under node); `DL.md.render(src, opts)` turns it into elements. Model-written text only
   ever becomes text nodes, never HTML.

   Tree: a node is `{t: tag, c: [children], a: {attrs}}`; text is a plain string. Tags: md (the
   root), p, h1–h6, hr, blockquote, ul, ol (a.start), li (a.task, a.checked), table, thead, tbody,
   tr, th, td (a.align), pre (a.lang; c: [code text]), code, strong, em, del, link (a.url),
   img (a.alt, a.url), autolink (a.url). */
(function (DL) {
  'use strict';

  function node(t, c, a) { return { t: t, c: c || [], a: a || {} }; }

  /* --- inline ------------------------------------------------------------------------------- */
  var INLINE = /(`+)([^`]|[^`][\s\S]*?[^`])\1(?!`)|\*\*(?=\S)([\s\S]*?\S)\*\*|__(?=\S)([\s\S]*?\S)__|\*(?=[^\s*])([\s\S]*?[^\s*])\*|(?<![\w])_(?=[^\s_])([\s\S]*?[^\s_])_(?![\w])|~~([\s\S]+?)~~|!\[([^\]]*)\]\(([^)\s]*)[^)]*\)|\[([^\]]+)\]\(([^)\s]*)[^)]*\)|<(https?:\/\/[^>\s]+)>/g;

  function inline(text, out) {
    out = out || [];
    var last = 0, m, re = new RegExp(INLINE.source, 'g');
    while ((m = re.exec(text))) {
      if (m.index > last) out.push(text.slice(last, m.index));
      if (m[1]) out.push(node('code', [m[2]]));
      else if (m[3] || m[4]) out.push(node('strong', inline(m[3] || m[4])));
      else if (m[5] || m[6]) out.push(node('em', inline(m[5] || m[6])));
      else if (m[7]) out.push(node('del', inline(m[7])));
      else if (m[9] !== undefined) out.push(node('img', [], { alt: m[8], url: m[9] }));
      else if (m[10]) out.push(node('link', inline(m[10]), { url: m[11] }));
      else if (m[12]) out.push(node('autolink', [m[12]], { url: m[12] }));
      last = re.lastIndex;
    }
    if (last < text.length) out.push(text.slice(last));
    return out;
  }

  /* --- blocks ------------------------------------------------------------------------------- */
  var RE = {
    fence: /^\s{0,3}(`{3,}|~{3,})\s*([\w+#.-]*)/, head: /^\s{0,3}(#{1,6})\s+(.*?)(?:\s+#+)?\s*$/,
    hr: /^\s{0,3}([-*_])(?:\s*\1){2,}\s*$/, quote: /^\s{0,3}>\s?/, item: /^(\s*)([-*+]|\d{1,9}[.)])\s+(.*)$/,
    tsep: /^\s*\|?\s*:?-{2,}:?\s*(?:\|\s*:?-{2,}:?\s*)*\|?\s*$/
  };
  function cells(line) {
    return line.trim().replace(/^\||\|$/g, '').split(/(?<!\\)\|/).map(function (c) { return c.trim().replace(/\\\|/g, '|'); });
  }
  function isBlockStart(l, next) {
    return RE.fence.test(l) || RE.head.test(l) || RE.hr.test(l) || RE.quote.test(l) || RE.item.test(l) ||
      (l.indexOf('|') >= 0 && next !== undefined && RE.tsep.test(next));
  }

  function blocks(lines, out) {
    var i = 0;
    while (i < lines.length) {
      var l = lines[i], m;
      if (!l.trim()) { i++; continue; }
      if ((m = RE.fence.exec(l))) {
        var fence = m[1], body = [];
        i++;
        while (i < lines.length && lines[i].trim().indexOf(fence) !== 0) body.push(lines[i++]);
        i++;
        out.push(node('pre', [body.join('\n')], { lang: m[2] || '' }));
        continue;
      }
      if ((m = RE.head.exec(l))) { out.push(node('h' + m[1].length, inline(m[2]))); i++; continue; }
      if (RE.hr.test(l)) { out.push(node('hr')); i++; continue; }
      if (RE.quote.test(l)) {
        var q = [];
        while (i < lines.length && lines[i].trim() && (RE.quote.test(lines[i]) || q.length)) q.push(lines[i++].replace(RE.quote, ''));
        out.push(node('blockquote', blocks(q, [])));
        continue;
      }
      if (l.indexOf('|') >= 0 && RE.tsep.test(lines[i + 1] || '')) {
        var aligns = cells(lines[i + 1]).map(function (c) { return /:$/.test(c) ? (/^:/.test(c) ? 'center' : 'right') : ''; });
        var row = function (line, tag) {
          return node('tr', cells(line).map(function (c, k) { return node(tag, inline(c), aligns[k] ? { align: aligns[k] } : {}); }));
        };
        var head = node('thead', [row(l, 'th')]), tbody = node('tbody');
        i += 2;
        while (i < lines.length && lines[i].trim() && lines[i].indexOf('|') >= 0) tbody.c.push(row(lines[i++], 'td'));
        out.push(node('table', [head, tbody]));
        continue;
      }
      if (RE.item.test(l)) { i = list(lines, i, out); continue; }
      var para = [];
      while (i < lines.length && lines[i].trim() && !(para.length && isBlockStart(lines[i], lines[i + 1]))) para.push(lines[i++].trim());
      var p = node('p');
      para.forEach(function (x, k) { if (k) p.c.push(' '); inline(x, p.c); });
      out.push(p);
    }
    return out;
  }

  function list(lines, i, out) {
    var first = RE.item.exec(lines[i]), indent = first[1].length, ordered = /\d/.test(first[2]);
    var ul = node(ordered ? 'ol' : 'ul');
    if (ordered && parseInt(first[2], 10) !== 1) ul.a.start = parseInt(first[2], 10);
    while (i < lines.length) {
      var m = RE.item.exec(lines[i]);
      if (!m || m[1].length !== indent || /\d/.test(m[2]) !== ordered) break;
      var body = [m[3]];
      i++;
      while (i < lines.length) {
        var l = lines[i];
        if (!l.trim()) {
          if (i + 1 < lines.length && /^\s/.test(lines[i + 1]) && (lines[i + 1].match(/^\s*/)[0].length > indent)) { body.push(''); i++; continue; }
          break;
        }
        var lead = l.match(/^\s*/)[0].length;
        if (lead <= indent && (RE.item.test(l) || isBlockStart(l))) break;
        body.push(lead > indent ? l.slice(Math.min(lead, indent + 2)) : l.trim());
        i++;
      }
      var li = node('li'), task = /^\[([ xX])\]\s+/.exec(body[0]);
      if (task) { li.a.task = true; li.a.checked = task[1] !== ' '; body[0] = body[0].slice(task[0].length); }
      if (body.length === 1) inline(body[0], li.c);
      else blocks(body, li.c);
      /* A one-paragraph item holds the paragraph's content directly: all of it (FR-025: it used
         to keep only the first child, dropping every line after the first). */
      if (li.c.length === 1 && li.c[0] && li.c[0].t === 'p') li.c = li.c[0].c;
      ul.c.push(li);
    }
    out.push(ul);
    return i;
  }

  function parse(src) {
    return node('md', blocks(String(src == null ? '' : src).replace(/\r\n?/g, '\n').split('\n'), []));
  }

  /* --- DOM ---------------------------------------------------------------------------------- */
  function toDom(n, opts) {
    if (typeof n === 'string') return document.createTextNode(n);
    var el = DL.el, e;
    function kids(target) { n.c.forEach(function (c) { target.appendChild(toDom(c, opts)); }); return target; }
    switch (n.t) {
      case 'md': return kids(el('div', opts.cls === undefined ? 'md' : opts.cls));
      case 'pre':
        e = el('pre');
        if (DL.hl) e.appendChild(DL.hl.codeView(n.c[0], DL.hl.langOf(n.a.lang), { ln: false }));
        else e.appendChild(el('code', null, n.c[0]));
        return e;
      case 'img': return el('span', 'muted', '[image: ' + (n.a.alt || n.a.url) + ']');
      case 'link': case 'autolink': {
        var href = opts.resolve ? opts.resolve(n.a.url) : null;
        if (href) { e = el('a'); e.href = href; return kids(e); }
        e = el('span', 'link');
        e.title = n.a.url + ' (links are not followed from the dashboard)';
        return kids(e);
      }
      case 'ol': e = kids(el('ol')); if (n.a.start) e.start = n.a.start; return e;
      case 'li':
        e = el('li');
        if (n.a.task) {
          e.className = 'task';
          var cb = el('input');
          cb.type = 'checkbox'; cb.disabled = true; cb.checked = !!n.a.checked;
          e.appendChild(cb);
        }
        return kids(e);
      case 'th': case 'td':
        e = kids(el(n.t));
        if (n.a.align) e.style.textAlign = n.a.align;
        return e;
      default: return kids(el(n.t));
    }
  }

  /* `opts.resolve(url)`: an app href for a link (e.g. a file of the workspace), or null; `opts.cls`:
     the root's class (default "md"). */
  function render(src, opts) { return toDom(parse(src), opts || {}); }

  DL.md = { parse: parse, render: render, toDom: toDom, inline: inline };
})(window.DL = window.DL || {});
