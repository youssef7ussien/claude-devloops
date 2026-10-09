/* now.js: the "now" panel above every view (FR-016, data-model Now). While a Claude call runs:
   its loop, milestone, trial, step, model, the time since it started (ticking every second), and
   the tools it used so far, newest last (the last 20, or all with "Show all"). Otherwise: the
   run's status and its next action or what it waits for. Reloaded on DL.bus 'changed'; while a
   call runs it is also asked for again every 15 seconds, so a command that died stops showing. */
(function (DL) {
  'use strict';

  var SHOWN = 20, RECHECK = 15000;
  var IDLE = { 'not-started': 'Nothing has run in this workspace yet.', completed: 'Every loop is done; no Claude call is running.' };
  var WAITS = { approval: 'Waits for the plan’s approval', questions: 'Waits for answers to its questions', retry: 'Waits for a retry' };
  var box = null, clock = null, recheck = null, showAll = false, drawn = false;

  /* The tools the panel lists: the last SHOWN, or all. */
  function visible(tools, all) {
    tools = tools || [];
    return all || tools.length <= SHOWN ? tools : tools.slice(tools.length - SHOWN);
  }

  /* An ISO time as "12:34:56". */
  function clockTime(iso) {
    var d = new Date(iso);
    return isNaN(d.getTime()) ? '' : d.toISOString().slice(11, 19);
  }

  function fact(label, value) {
    return DL.add(DL.el('span', 'fact'), label + ' ', DL.el('b', null, value == null || value === '' ? '–' : String(value)));
  }

  function stop() {
    if (clock) clearInterval(clock);
    if (recheck) clearTimeout(recheck);
    clock = recheck = null;
  }

  function running(d) {
    var c = d.call || {}, tools = c.tools || [], shown = visible(tools, showAll);
    /* counted from when the answer arrived, so a redraw ("Show all") keeps the time */
    var base = d.elapsed_seconds || 0, at = d.received || Date.now();
    function since() { return base + (Date.now() - at) / 1000; }
    var elapsed = DL.el('b', null, DL.fmt.duration(since()));
    var milestone = c.milestone_id
      ? DL.link(DL.router.href('loop', { loop: c.loop }, { m: c.milestone_id }), c.milestone_id)
      : DL.el('span', null, 'planning');
    var head = DL.add(DL.el('div', 'now-head'), DL.add(DL.el('strong'), DL.el('span', 'pulse'), ' Running'),
      DL.add(DL.el('span', 'fact'), 'loop ', DL.el('b', null, c.loop || '–')),
      DL.add(DL.el('span', 'fact'), 'milestone ', DL.add(DL.el('b'), milestone)),
      fact('trial', c.trial), fact('step', c.step), fact('model', c.model),
      DL.add(DL.el('span', 'fact'), 'elapsed ', elapsed), DL.el('span', 'spacer'),
      DL.el('span', 'small muted', DL.fmt.plural(tools.length, 'tool call')));
    head.firstChild.firstChild.setAttribute('aria-hidden', 'true');
    if (tools.length > SHOWN) {
      head.appendChild(DL.btn(showAll ? 'Show the last ' + SHOWN : 'Show all', {
        cls: 'ghost', on: function () { showAll = !showAll; draw(d); }
      }));
    }
    box.className = 'now';
    DL.add(box, head);
    if (shown.length) {
      var list = DL.el('ol', 'now-tools');
      list.setAttribute('aria-label', 'Tools used so far, newest last');
      shown.forEach(function (t) {
        var time = DL.el('time', null, clockTime(t.at));
        time.dateTime = t.at || '';
        DL.add(list, DL.add(DL.el('li'), time, DL.el('b', null, t.name),
          t.summary && t.summary !== t.name ? DL.el('span', null, t.summary) : null));
      });
      box.appendChild(list);
      list.scrollTop = list.scrollHeight;
    }
    clock = setInterval(function () { elapsed.textContent = DL.fmt.duration(since()); }, 1000);
    if (DL.api.source() === 'api') recheck = setTimeout(function () { load(true); }, RECHECK);
  }

  function idle(d) {
    box.className = 'now idle';
    DL.add(box, DL.pill(d.status, 'run'));
    if (d.busy && d.busy.length) {
      box.appendChild(DL.el('span', null, d.busy.join(', ') + ' running: between Claude calls'));
      return;
    }
    if (d.waiting_for) box.appendChild(DL.el('strong', null, WAITS[d.waiting_for] || d.waiting_for));
    var a = d.next_action;
    if (a) {
      DL.add(box, DL.add(DL.el('span'), DL.ticks(a.text)));
      if (a.route) box.appendChild(DL.link(a.route, 'Open'));
    } else if (!d.waiting_for && IDLE[d.status]) {
      box.appendChild(DL.el('span', 'muted', IDLE[d.status]));
    }
  }

  function draw(d) {
    stop();
    box.textContent = '';
    box.hidden = false;
    drawn = true;
    if (d.running) running(d); else idle(d);
  }

  function load(fresh) {
    return DL.api.get('now', fresh).then(function (d) {
      if (!d.received) d.received = Date.now();
      draw(d);
    }, function () {
      if (drawn) return; /* offline: keep what is shown */
      stop();
      box.hidden = true;
    });
  }

  DL.now = {
    visible: visible,
    start: function (el) {
      box = el;
      if (!box) return;
      DL.bus.on('changed', function () { load(); });
      load();
    }
  };
})(window.DL = window.DL || {});
