/* views/events.js: `#/events` — every loop's events, oldest first, filterable. */
(function (DL) {
  'use strict';

  DL.router.register('events', {
    title: function () { return 'Events'; },
    data: function () { return ['events']; },
    render: function (data, params, el) {
      var events = data[0].events;
      var rows = events.map(function (ev) {
        return DL.add(DL.el('tr'), DL.td(DL.fmt.time(ev.at), 'muted small nowrap'), DL.td(ev.loop),
          DL.td(DL.el('span', 'tag', ev.type || '')), DL.td(ev.milestone || ''), DL.td(ev.message || ''));
      });
      DL.add(el, DL.head('Events', null, DL.fmt.plural(events.length, 'event') + ', oldest first'),
        rows.length ? DL.filter(rows, { placeholder: 'Filter events…' }) : null,
        DL.table([['Time'], ['Loop'], ['Type'], ['Milestone'], ['Message']], rows, { empty: 'No events yet.' }));
    }
  });
})(window.DL = window.DL || {});
