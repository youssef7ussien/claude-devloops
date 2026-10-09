/* charts.js: the bar chart and the trial timeline, built as SVG elements (ports of dashboard.py's
   bar_chart and timeline). The geometry lives in pure functions (_layoutBars, _layoutTimeline) so
   node --test can check it. Tooltips come from `data-tip`: the caller runs DL.tips(container)
   once the chart is in the page. */
(function (DL) {
  'use strict';

  var SVG = 'http://www.w3.org/2000/svg';
  var BARS = { labelW: 170, chartW: 250, rowH: 28, valueW: 64 };
  var LINE = { labelW: 190, chartW: 900, rowH: 30, pad: 40 };

  function svg(tag, attrs, text) {
    var n = document.createElementNS(SVG, tag);
    Object.keys(attrs || {}).forEach(function (k) { n.setAttribute(k, String(attrs[k])); });
    if (text != null) n.textContent = text;
    return n;
  }
  function round1(v) { return Math.round(v * 10) / 10; }

  /* --- bars ------------------------------------------------------------------------------------ */

  /* `{width, height, peak, rows: [{label, value, tip, y, w, labelX, textY, valueX, d}]}`, or null
     when there is nothing to draw (no rows, or no value above 0). */
  function layoutBars(rows) {
    rows = (rows || []).filter(function (r) { return r.value != null; });
    if (!rows.length) return null;
    var peak = Math.max.apply(null, rows.map(function (r) { return r.value; }));
    if (peak <= 0) return null;
    var g = BARS, height = g.rowH * rows.length + 8, width = g.labelW + g.chartW + g.valueW;
    return {
      width: width, height: height, peak: peak,
      rows: rows.map(function (r, i) {
        var y = i * g.rowH + 4, w = Math.max(8, g.chartW * r.value / peak);
        return {
          label: r.label, value: r.value, tip: r.tip, y: y, w: w,
          labelX: g.labelW - 10, textY: y + g.rowH / 2 + 4, valueX: g.labelW + w + 6,
          d: 'M' + g.labelW + ',' + (y + 6) + ' h' + (w - 4) + ' a4,4 0 0 1 4,4 v' + (g.rowH - 20) +
             ' a4,4 0 0 1 -4,4 h' + (-(w - 4)) + ' z'
        };
      })
    };
  }

  /* rows `[{label, value, tip}]`; opts `{format, title, columns: [label, value]}`. */
  function bars(rows, opts) {
    opts = opts || {};
    var format = opts.format || String, title = opts.title || '', cols = opts.columns || ['', ''];
    var lay = layoutBars(rows), box = DL.el('div', 'chart-box');
    if (!lay) { box.appendChild(DL.el('p', 'muted', 'Nothing recorded yet.')); return box; }
    var s = svg('svg', { 'class': 'chart', width: lay.width, viewBox: '0 0 ' + lay.width + ' ' + lay.height,
                         role: 'img', 'aria-label': title });
    lay.rows.forEach(function (r) {
      var g = svg('g', { 'class': 'mark', tabindex: 0, 'data-tip': r.tip == null ? '' : r.tip });
      g.appendChild(svg('rect', { 'class': 'hit', x: 0, y: r.y, width: lay.width, height: BARS.rowH }));
      g.appendChild(svg('text', { 'class': 'axis-label', x: r.labelX, y: r.textY, 'text-anchor': 'end' }, r.label));
      g.appendChild(svg('path', { 'class': 'bar', d: r.d }));
      g.appendChild(svg('text', { 'class': 'value-label', x: r.valueX, y: r.textY }, format(r.value)));
      s.appendChild(g);
    });
    s.appendChild(svg('line', { 'class': 'baseline', x1: BARS.labelW, x2: BARS.labelW, y1: 0, y2: lay.height }));
    box.appendChild(s);
    var t = DL.el('table', 'sr-only'), head = DL.el('thead'), tr = DL.el('tr'), body = DL.el('tbody');
    t.appendChild(DL.el('caption', null, title));
    tr.appendChild(DL.el('th', null, cols[0]));
    tr.appendChild(DL.el('th', null, cols[1]));
    head.appendChild(tr);
    t.appendChild(head);
    lay.rows.forEach(function (r) {
      var row = DL.el('tr');
      row.appendChild(DL.el('td', null, r.label));
      row.appendChild(DL.el('td', null, format(r.value)));
      body.appendChild(row);
    });
    t.appendChild(body);
    box.appendChild(t);
    return box;
  }

  /* --- timeline -------------------------------------------------------------------------------- */

  function time(v) {
    if (!v) return null;
    var t = Date.parse(v);
    return isNaN(t) ? null : t;
  }

  /* The tooltip of one trial segment. */
  function trialTip(t) {
    var s = DL.status(t.status, 'trial'), a = time(t.started_at), b = time(t.ended_at);
    var reason = t.reason || (t.failure || {}).reason;
    return (t.label || '') + ' — ' + s[1] + ' ' + s[0] + (reason ? ': ' + reason : '') + ' · ' +
      DL.fmt.duration(a != null && b != null ? (b - a) / 1000 : null);
  }

  /* rows `[{label, trials: [{status, started_at, ended_at, label, reason, route}]}]` →
     `{width, height, total, grid: [{x, label}], rows: [{label, y, textY, segs: [{x, y, w, h,
     tone, tip, route}]}]}`, or null when no trial has a start. */
  function layoutTimeline(rows) {
    rows = rows || [];
    var spans = [];
    rows.forEach(function (r) {
      (r.trials || []).forEach(function (t) {
        var a = time(t.started_at), b = time(t.ended_at);
        if (a != null) spans.push([a, b != null ? b : a]);
      });
    });
    if (!spans.length) return null;
    var t0 = Math.min.apply(null, spans.map(function (x) { return x[0]; }));
    var t1 = Math.max.apply(null, spans.map(function (x) { return x[1]; }));
    var total = Math.max((t1 - t0) / 1000, 1), g = LINE;
    var height = g.rowH * rows.length + 30, width = g.labelW + g.chartW + g.pad, grid = [];
    for (var k = 0; k < 5; k++) {
      grid.push({ x: g.labelW + g.chartW * k / 4, label: '+' + DL.fmt.duration(total * k / 4) });
    }
    return {
      width: width, height: height, total: total, grid: grid,
      rows: rows.map(function (r, i) {
        var y = i * g.rowH + 4, segs = [];
        (r.trials || []).forEach(function (t) {
          var a = time(t.started_at);
          if (a == null) return;
          var b = time(t.ended_at);
          if (b == null) b = a;
          segs.push({
            x: round1(g.labelW + g.chartW * ((a - t0) / 1000) / total), y: y + 5,
            w: round1(Math.max(6, g.chartW * ((b - a) / 1000) / total - 2)), h: g.rowH - 12,
            tone: DL.status(t.status, 'trial')[2], tip: trialTip(t), route: t.route || null
          });
        });
        return { label: r.label, y: y, textY: y + g.rowH / 2 + 2, segs: segs };
      })
    };
  }

  function timeline(rows) {
    var lay = layoutTimeline(rows), box = DL.el('div', 'chart-box');
    if (!lay) { box.appendChild(DL.el('p', 'muted', 'No trials yet.')); return box; }
    var legend = DL.el('div', 'legend');
    Object.keys(DL.STATUS.trial).forEach(function (k) {
      var s = DL.STATUS.trial[k], item = DL.el('span', 'legend-item'), icon = DL.el('span', null, s[1]);
      icon.setAttribute('aria-hidden', 'true');
      DL.add(item, DL.el('span', 'swatch tone-' + s[2]), icon, ' ' + s[0]);
      legend.appendChild(item);
    });
    box.appendChild(legend);
    var s = svg('svg', { 'class': 'chart', width: lay.width, viewBox: '0 0 ' + lay.width + ' ' + lay.height,
                         role: 'img', 'aria-label': 'Trial timeline' });
    lay.grid.forEach(function (gl) {
      s.appendChild(svg('line', { 'class': 'grid', x1: gl.x, x2: gl.x, y1: 0, y2: lay.height - 22 }));
      s.appendChild(svg('text', { 'class': 'axis-label', x: gl.x, y: lay.height - 6, 'text-anchor': 'middle' }, gl.label));
    });
    lay.rows.forEach(function (r) {
      s.appendChild(svg('text', { 'class': 'axis-label', x: LINE.labelW - 10, y: r.textY, 'text-anchor': 'end' }, r.label));
      r.segs.forEach(function (seg) {
        var g = svg('g', { 'class': 'mark', tabindex: 0, 'data-tip': seg.tip });
        g.appendChild(svg('rect', { 'class': 'seg tone-' + seg.tone, x: seg.x, y: seg.y, width: seg.w, height: seg.h, rx: 4 }));
        if (seg.route) {
          var a = svg('a', { href: seg.route });
          g.removeAttribute('tabindex'); /* the link takes the focus */
          a.appendChild(g);
          s.appendChild(a);
        } else s.appendChild(g);
      });
    });
    box.appendChild(s);
    return box;
  }

  DL.charts = { bars: bars, timeline: timeline, _layoutBars: layoutBars, _layoutTimeline: layoutTimeline,
                _trialTip: trialTip };
})(window.DL = window.DL || {});
