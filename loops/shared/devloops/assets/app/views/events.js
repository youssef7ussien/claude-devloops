/* views/events.js: `#/events` — every loop's events, oldest first, filterable;
   `?loop=<loop>&at=<n>` scrolls to that loop's n-th event and marks it (a search result). */
(function (DL) {
  'use strict';

  DL.router.register('events', {
    title: function () { return 'Events'; },
    data: function () { return ['events']; },
    render: function (data, params, el, query, refresh) {
      var events = data[0].events, target = null;
      query = query || {};
      var rows = events.map(function (ev) {
        var tr = DL.add(DL.el('tr'), DL.td(DL.fmt.time(ev.at), 'muted small nowrap'), DL.td(ev.loop),
          DL.td(DL.el('span', 'tag', ev.type || '')), DL.td(ev.milestone || ''), DL.td(ev.message || ''));
        if (ev.loop === query.loop && String(ev.n) === String(query.at)) target = tr;
        return tr;
      });
      DL.add(el, DL.head('Events', null, DL.fmt.plural(events.length, 'event') + ', oldest first'),
        rows.length ? DL.filter(rows, { placeholder: 'Filter events…' }) : null,
        DL.table([['Time'], ['Loop'], ['Type'], ['Milestone'], ['Message']], rows, { empty: 'No events yet.' }));
      if (target && !refresh) {
        target.classList.add('hit');
        setTimeout(function () { if (el.isConnected) target.scrollIntoView({ block: 'center' }); }, 0);
      }
    }
  });
})(window.DL = window.DL || {});
