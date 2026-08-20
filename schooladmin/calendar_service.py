"""
Per-member calendar data for the Monthly Report "Calendar View" tab and the
Member Gap Report calendar — one place both pages pull from instead of two
separately-maintained day-loops.

Reuses `calculate_attendance_stats` for punch times / late / early / worked
hours (that part of the engine is correct and shared with payroll), but
layers on its own leave lookup rather than trusting that function's leave
matching for calendar display purposes. `calculate_attendance_stats` only
matches a leave when *both* `gap_start` and `gap_end` are set, which never
matches a single-day leave (gap_end is deliberately left None for those) —
a known, pre-existing gap that changes payroll numbers if fixed there, so it
is intentionally left alone (see the Mero Attendance project notes). Calendar
display doesn't feed payroll, so it can safely show single-day leaves
correctly without touching that shared function.
"""
import datetime

from management.models import LeaveReport
from handle.models import DailyNote
from schooladmin.payroll_service import calculate_attendance_stats


def _leave_on(approved_leaves, target_date):
    for leave in approved_leaves:
        if leave.gap_start is None:
            continue
        end = leave.gap_end or leave.gap_start
        if leave.gap_start <= target_date <= end:
            return leave
    return None


def build_member_calendar(memb, start_date, end_date, org, nepali_enabled=False):
    """Returns a list of per-day dicts (one per calendar day in range),
    each a superset of `calculate_attendance_stats`'s daily_logs dict plus
    `leave_type`, `leave_reason` and `note`/`note_id`."""
    _, daily_logs = calculate_attendance_stats(
        memb, start_date, end_date, org, nepali_enabled=nepali_enabled,
    )

    approved_leaves = list(LeaveReport.objects.filter(
        member=memb, approved=True,
    ).select_related('leave_type'))

    notes = {
        n.date: n for n in DailyNote.objects.filter(
            member=memb, date__range=(start_date, end_date),
        )
    }

    days = []
    for log in daily_logs:
        d = log['date']
        leave = _leave_on(approved_leaves, d)
        status, code, code_class = log['status'], log['code'], log['code_class']

        # calculate_attendance_stats already correctly prioritizes
        # Present/Holiday/Occasion over Leave — only step in for the one
        # case its leave matching misses: an otherwise-unexplained absence
        # that a single-day leave (or its own multi-day matching) actually
        # covers.
        if leave and code == 'A':
            paid = leave.leave_type is None or getattr(leave.leave_type, 'is_paid', True)
            status = 'Paid Leave' if paid else 'Unpaid Leave'
            code, code_class = 'L', 'l'

        note = notes.get(d)
        days.append({
            **log,
            'status': status,
            'code': code,
            'code_class': code_class,
            'leave_type': leave.leave_type.name if (leave and leave.leave_type) else ('Leave' if leave else ''),
            'leave_reason': leave.reason if leave else '',
            'note': note.text if note else '',
            'note_id': note.id if note else None,
        })
    return days


def serialize_day(day):
    """JSON-safe copy of one `build_member_calendar` day dict."""
    out = dict(day)
    out['date'] = day['date'].isoformat()
    for key in ('worked_hrs', 'overtime_hrs', 'late_hours_dec', 'early_hours_dec', 'overtime_hours_dec'):
        if key in out and out[key] is not None:
            out[key] = float(out[key])
    out.pop('shift_windows', None)
    return out
