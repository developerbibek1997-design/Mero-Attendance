/*
 * Shared "member calendar" grid — used by Monthly Report's Calendar View tab
 * and the Member Gap Report calendar (templates/admin/memberRecord.html).
 *
 * Deliberately not FullCalendar: a plain CSS-grid month view is easier to
 * make print exactly one page (fixed mm heights + equal-fraction rows) and
 * drops the CDN dependency + the BS-day client-side conversion the old
 * per-page implementation relied on (the server already computed each day's
 * BS date, so this just reads it off `day.date_np`).
 *
 * Usage: AttendanceCalendar.render(containerEl, {
 *   days: [...],            // from MemberCalendarDataView JSON
 *   startDate, endDate,     // 'YYYY-MM-DD', the filtered range
 *   onDayClick(dateIso, day) // day is null for out-of-range padding cells
 * });
 */
(function () {
  'use strict';

  var CODE_LABEL = { P: 'Present', A: 'Absent', L: 'Leave', H: 'Holiday', W: 'Weekly Off', F: 'Field Visit' };
  var WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

  function pad(n) { return n < 10 ? '0' + n : '' + n; }

  function parseIso(s) {
    var parts = s.split('-').map(Number);
    return new Date(parts[0], parts[1] - 1, parts[2]);
  }

  function toIso(d) {
    return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate());
  }

  function addDays(d, n) {
    var r = new Date(d.getTime());
    r.setDate(r.getDate() + n);
    return r;
  }

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
    });
  }

  // Server times come through as Python's plain str(time) - "HH:MM:SS" or,
  // when the underlying punch has microseconds, "HH:MM:SS.ffffff". Only
  // HH:MM is ever useful on a compact calendar cell.
  function shortTime(t) {
    var m = /^(\d{1,2}):(\d{2})/.exec(t || '');
    return m ? m[1] + ':' + m[2] : t;
  }

  function buildCell(dateObj, day) {
    var cell = document.createElement('div');
    cell.className = 'ac-cell';

    if (!day) {
      cell.classList.add('ac-cell-empty');
      cell.innerHTML = '<span class="ac-daynum ac-daynum-muted">' + dateObj.getDate() + '</span>';
      return cell;
    }

    cell.classList.add('ac-cell-' + day.code_class);
    cell.dataset.date = day.date;

    var bsDay = day.date_np ? day.date_np.split('-').pop() : '';
    var html = '<div class="ac-cell-head"><span class="ac-daynum">' + dateObj.getDate() + '</span>'
      + (bsDay ? '<span class="ac-bsnum">' + esc(bsDay) + '</span>' : '') + '</div>';

    html += '<span class="ac-status-pill ac-pill-' + day.code_class + '">' + esc(CODE_LABEL[day.code] || day.code) + '</span>';

    if (day.code === 'P') {
      var inT = day.punch_in && day.punch_in !== '-' ? shortTime(day.punch_in) : '--';
      var outT = day.punch_out && day.punch_out !== '-' ? shortTime(day.punch_out) : '--';
      html += '<div class="ac-times">' + esc(inT) + ' &rarr; ' + esc(outT) + '</div>';
      if (day.late_in && day.late_in !== '-') html += '<div class="ac-flag ac-flag-late">Late ' + esc(day.late_in) + '</div>';
      if (day.early_out && day.early_out !== '-') html += '<div class="ac-flag ac-flag-early">Early ' + esc(day.early_out) + '</div>';
    } else if (day.code === 'L') {
      html += '<div class="ac-times">' + esc(day.leave_type || 'Leave') + '</div>';
    }

    if (day.note) {
      html += '<span class="ac-note-flag" title="' + esc(day.note) + '"><i class="fas fa-sticky-note"></i></span>';
    } else {
      html += '<span class="ac-add-hint">+ add</span>';
    }

    cell.innerHTML = html;
    return cell;
  }

  function render(container, opts) {
    container.innerHTML = '';
    if (!opts.startDate || !opts.endDate) return;

    var wrap = document.createElement('div');
    wrap.className = 'ac-wrap';

    var start = parseIso(opts.startDate);
    var end = parseIso(opts.endDate);
    var gridStart = addDays(start, -start.getDay());
    var gridEnd = addDays(end, 6 - end.getDay());

    var dayMap = {};
    (opts.days || []).forEach(function (d) { dayMap[d.date] = d; });

    var head = document.createElement('div');
    head.className = 'ac-weekday-row';
    WEEKDAYS.forEach(function (w) {
      var el = document.createElement('div');
      el.className = 'ac-weekday';
      el.textContent = w;
      head.appendChild(el);
    });
    wrap.appendChild(head);

    var grid = document.createElement('div');
    grid.className = 'ac-grid';
    var cursor = gridStart;
    var rows = 0;
    while (cursor <= gridEnd) {
      var iso = toIso(cursor);
      var inRange = cursor >= start && cursor <= end;
      var day = inRange ? dayMap[iso] : null;
      var cell = buildCell(cursor, day);
      if (day && opts.onDayClick) {
        cell.addEventListener('click', function () {
          opts.onDayClick(this.dataset.date, dayMap[this.dataset.date] || null);
        });
      }
      grid.appendChild(cell);
      cursor = addDays(cursor, 1);
      rows = grid.children.length / 7;
    }
    grid.style.setProperty('--ac-rows', rows);
    wrap.appendChild(grid);
    container.appendChild(wrap);
  }

  window.AttendanceCalendar = { render: render };
})();
