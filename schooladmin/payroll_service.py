"""
Payroll Service — centralised payroll calculation for Mero Attendance.

Both individual payslip generation (paySlipDetailView) and bulk payslip
generation (BulkPayslipView) call these helpers so the maths is always
identical and maintained in one place.
"""

from decimal import Decimal
import datetime

from django.utils import timezone

from handle.models import (
    AttendanceRecord, PayrollAdjustment, PayrollPolicy,
)
from management.models import LeaveReport, Holiday, Occasion


# ─── tiny utilities ────────────────────────────────────────────────────────────

def time_to_decimal(time_str):
    """'HH:MM' → Decimal hours. Returns 0 on any parse error."""
    if not time_str or time_str == '-':
        return Decimal('0')
    try:
        h, m = map(int, str(time_str).split(':'))
        return Decimal(h) + (Decimal(m) / Decimal('60'))
    except Exception:
        return Decimal('0')


def decimal_money(value):
    return Decimal(str(value or 0)).quantize(Decimal('0.01'))


def duration_to_decimal_hours(delta):
    """timedelta -> Decimal hours, full precision (no minute flooring)."""
    if not delta:
        return Decimal('0')
    return Decimal(str(delta.total_seconds())) / Decimal('3600')


def _sum_adjustments(queryset, adjustment_type):
    from django.db.models import Sum
    total = queryset.filter(adjustment_type=adjustment_type).aggregate(
        t=Sum('amount')
    )['t'] or Decimal('0.00')
    return decimal_money(total)


# ─── per-window shift breakdown ─────────────────────────────────────────────────

def compute_shift_breakdown(memb, target_date, grace_minutes=0):
    """
    For a member with an assigned multi-window shift, pair the day's punches to
    each shift window and compute late-in / early-out / overtime PER WINDOW.

    Returns a dict:
        {
          'windows': [ {label, start, end, punch_in, punch_out, attended,
                        late_min, early_min, ot_min, worked_hrs}, ... ],
          'attended_any': bool,
          'late_hours': Decimal, 'early_hours': Decimal,
          'overtime_hours': Decimal, 'worked_hours': Decimal,
        }
    or None if the member has no active assigned shift.
    """
    if not memb.has_active_shift(target_date):
        return None

    windows_detailed = memb.shift_windows_detailed(target_date)  # [{'shift_id','shift_name','start_time','end_time'}, ...]
    windows = [(w['start_time'], w['end_time']) for w in windows_detailed]
    grace = datetime.timedelta(minutes=int(grace_minutes or 0))

    def to_dt(t):
        d = datetime.datetime.combine(target_date, t)
        return d

    # Build window datetime ranges (handle overnight windows).
    win_dts = []
    for start, end in windows:
        s = to_dt(start)
        e = to_dt(end)
        if e <= s:
            e += datetime.timedelta(days=1)
        win_dts.append((s, e))

    # Read the day's punches as sequential IN/OUT pairs:
    #   1st punch = IN, 2nd = OUT, 3rd = IN, 4th = OUT …  (odd last punch = IN only).
    punches = sorted(to_dt(t) for t in memb.day_punch_times(target_date))
    pairs = []
    i = 0
    while i < len(punches):
        pin = punches[i]
        pout = punches[i + 1] if i + 1 < len(punches) else None
        pairs.append([pin, pout])
        i += 2

    # Assign each (in, out) pair to a window by its check-in time: the last window
    # whose start time has passed. So 06:30 → window starting 06:00, 13:00 →
    # window starting 10:30, etc. Multiple pairs on one window merge (earliest in,
    # latest out); a window with no pair is treated as absent for that window.
    win_starts = [wd[0] for wd in win_dts]

    def window_for(pin):
        idx = 0
        for k in range(len(win_starts)):
            if pin >= win_starts[k]:
                idx = k
            else:
                break
        return idx

    assigned = [None] * len(win_dts)   # each entry: [punch_in, punch_out]
    for pin, pout in pairs:
        wi = window_for(pin)
        if assigned[wi] is None:
            assigned[wi] = [pin, pout]
        else:
            if pin < assigned[wi][0]:
                assigned[wi][0] = pin
            if pout and (assigned[wi][1] is None or pout > assigned[wi][1]):
                assigned[wi][1] = pout

    result_windows = []
    total_early_in = datetime.timedelta(0)
    total_late = datetime.timedelta(0)          # actual (displayed) lateness
    total_late_penalized = datetime.timedelta(0)  # grace-adjusted (feeds payroll)
    total_early = datetime.timedelta(0)
    total_late_out = datetime.timedelta(0)
    total_ot = datetime.timedelta(0)
    total_worked = datetime.timedelta(0)
    attended_any = False

    for wi, ((s, e), (raw_start, raw_end)) in enumerate(zip(win_dts, windows)):
        pair = assigned[wi]
        punch_in = pair[0] if pair else None
        punch_out = pair[1] if pair else None
        attended = punch_in is not None
        complete = punch_in is not None and punch_out is not None
        if attended:
            attended_any = True

        early_in = datetime.timedelta(0)     # arrived before the window start
        late = datetime.timedelta(0)         # actual late-in (shown in the report)
        late_penalized = datetime.timedelta(0)  # late-in after the grace window (payroll)
        early = datetime.timedelta(0)        # early-out: left before window end
        late_out = datetime.timedelta(0)     # left after window end
        ot = datetime.timedelta(0)           # overtime = time worked past window end
        worked = datetime.timedelta(0)

        if punch_in:
            if punch_in < s:
                early_in = s - punch_in
            elif punch_in > s:
                late = punch_in - s   # full, actual lateness
                late_penalized = datetime.timedelta(0) if late <= grace else (late - grace)
        if punch_out:
            if punch_out < e:
                early = e - punch_out
            if punch_out > e:
                late_out = punch_out - e
                ot = late_out
            worked = punch_out - punch_in

        total_early_in += early_in
        total_late += late
        total_late_penalized += late_penalized
        total_early += early
        total_late_out += late_out
        total_ot += ot
        total_worked += worked

        result_windows.append({
            'label': f"{raw_start.strftime('%I:%M %p').lstrip('0')}–{raw_end.strftime('%I:%M %p').lstrip('0')}",
            'start': raw_start, 'end': raw_end,
            'shift_id': windows_detailed[wi]['shift_id'],
            'shift_name': windows_detailed[wi]['shift_name'],
            'punch_in': punch_in.time().strftime('%H:%M:%S') if punch_in else '-',
            'punch_out': punch_out.time().strftime('%H:%M:%S') if punch_out else '-',
            'attended': attended,
            'complete': complete,
            'early_in_min': round(early_in.total_seconds() / 60, 1),
            'late_min': round(late.total_seconds() / 60, 1),
            'late_penalized_min': round(late_penalized.total_seconds() / 60, 1),
            'early_min': round(early.total_seconds() / 60, 1),
            'late_out_min': round(late_out.total_seconds() / 60, 1),
            'ot_min': round(ot.total_seconds() / 60, 1),
            'worked_hrs': round(worked.total_seconds() / 3600, 2),
        })

    return {
        'windows': result_windows,
        'attended_any': attended_any,
        'early_in_hours': duration_to_decimal_hours(total_early_in),
        'late_hours': duration_to_decimal_hours(total_late),                    # actual (display)
        'late_hours_penalized': duration_to_decimal_hours(total_late_penalized),  # after grace (payroll)
        'early_hours': duration_to_decimal_hours(total_early),
        'late_out_hours': duration_to_decimal_hours(total_late_out),
        'overtime_hours': duration_to_decimal_hours(total_ot),
        'worked_hours': duration_to_decimal_hours(total_worked),
    }


# ─── attendance stats ──────────────────────────────────────────────────────────

def calculate_attendance_stats(memb, start_date, end_date, org, nepali_enabled=False, show_field_visits=False):
    """
    Walk every calendar day in [start_date, end_date] and classify it.

    `show_field_visits` — caller-computed (has_feature + has_perm gate lives
    in the view, not here) — when True, a day that would otherwise be
    unexplained-absent ('A') and has a completed field visit is coded 'F'
    instead. Never overrides a real Present/Leave/Holiday day.

    Returns:
        stats  – dict with counters and totals
        daily_logs – list of per-day dicts (for the payslip preview table)
    """
    try:
        import nepali_datetime
    except ImportError:
        nepali_datetime = None

    holidays = Holiday.objects.filter(org=org)
    # Materialized to plain lists (not left as querysets) so the day-loop
    # below can match each day in Python instead of re-querying the DB on
    # every iteration — `qs.filter(...)` always returns a fresh, uncached
    # queryset even when `qs` itself was already evaluated.
    occasions = list(Occasion.objects.filter(org=org))
    approved_leaves = list(LeaveReport.objects.filter(
        member=memb, approved=True
    ).select_related('leave_type'))

    field_visit_dates = set()
    if show_field_visits:
        from handle.models import AttendanceRecord as _AttendanceRecord
        from handle.models import FieldVisit as _FieldVisit

        def _add_date(ts):
            if ts:
                local_ts = timezone.localtime(ts) if timezone.is_aware(ts) else ts
                field_visit_dates.add(local_ts.date())

        # Source 1: FieldVisit.started_at/scheduled_for — set by the live
        # mobile check-in flow. Lets a visit show as 'F' as soon as the
        # staff completes it in the field, even before an admin reviews it.
        visits = _FieldVisit.objects.filter(
            org=org, member=memb, visit_state='completed'
        ).values_list('started_at', 'scheduled_for')
        for started_at, scheduled_for in visits:
            _add_date(started_at)
            _add_date(scheduled_for)

        # Source 2: the linked AttendanceRecord's scanned_time. Needed for
        # admin-created visits (the "Log a Field Visit Manually" flow,
        # including multi-day backfills) — those never set started_at or
        # scheduled_for, so without this every manually-logged visit was
        # silently invisible to the report regardless of date.
        scan_times = _AttendanceRecord.objects.filter(
            org=org, mem=memb, attendance_method='field_visit',
            field_visit__visit_state='completed',
        ).values_list('scanned_time', flat=True)
        for ts in scan_times:
            _add_date(ts)

    # Org-wide late grace: lateness within this window is not penalized.
    grace_minutes = 0
    try:
        policy = getattr(org, 'payroll_policy', None)
        if policy and policy.late_grace_minutes:
            grace_minutes = int(policy.late_grace_minutes)
    except Exception:
        grace_minutes = 0
    grace_delta = datetime.timedelta(minutes=grace_minutes)

    total_days = (end_date - start_date).days + 1

    stats = {
        'total_days': total_days,
        'days_present': 0,
        'days_leave': 0,
        'days_paid_leave': 0,
        'days_unpaid_leave': 0,
        'days_holiday': 0,
        'days_unpaid_absent': 0,
        'total_hours_worked': Decimal('0'),
        'total_missing_hours': Decimal('0'),
        'total_overtime_hours': Decimal('0'),
    }

    daily_logs = []
    loop_date = start_date
    delta = datetime.timedelta(days=1)

    while loop_date <= end_date:
        is_holiday = any(h.holiday == loop_date.strftime("%A") for h in holidays)
        # end_date/gap_end are nullable (e.g. a single-day leave deliberately
        # has gap_end=None) — guard against None the same way the original
        # `.filter(end_date__gte=...)`/`.filter(gap_end__gte=...)` queries
        # did: a NULL never satisfies a >= comparison in SQL, so it never
        # matched. `None <= x` raises in plain Python, so this has to be
        # explicit here instead of falling out of the comparison for free.
        is_occasion = any(
            o.end_date is not None and o.date <= loop_date <= o.end_date
            for o in occasions
        )

        leave_record = next(
            (
                l for l in approved_leaves
                if l.gap_start is not None and l.gap_end is not None
                and l.gap_start <= loop_date <= l.gap_end
            ),
            None,
        )
        is_leave = leave_record is not None
        # A leave is paid unless the leave_type explicitly marks it unpaid
        is_paid_leave = is_leave and (
            leave_record.leave_type is None or
            getattr(leave_record.leave_type, 'is_paid', True)
        )

        memb.date = loop_date
        aa = memb.first_daily_time()
        try:
            bb = memb.last_daily_time()
        except Exception:
            bb = None

        daily_worked_hrs = Decimal('0')
        overtime_decimal = Decimal('0')
        late_hours_dec = Decimal('0')
        early_hours_dec = Decimal('0')
        status_badge = "Absent"
        late_in_str = "-"
        early_out_str = "-"
        shift_windows_detail = None

        has_shift = memb.has_active_shift()

        # Determine "present" independently of the single-envelope aa/bb pairing:
        # shift members are present if any of their windows was attended.
        breakdown = None
        if has_shift:
            breakdown = compute_shift_breakdown(memb, loop_date, grace_minutes)
            present = bool(breakdown and breakdown['attended_any'])
        else:
            present = bool(aa and bb)

        if present and has_shift:
            status_badge = "Present"
            stats['days_present'] += 1
            daily_worked_hrs = breakdown['worked_hours']
            stats['total_hours_worked'] += daily_worked_hrs

            # Display shows actual lateness; payroll deduction uses the grace-adjusted value.
            late_hours_dec = breakdown['late_hours_penalized']
            late_hours_display = breakdown['late_hours']
            early_hours_dec = breakdown['early_hours']
            overtime_decimal = breakdown['overtime_hours']
            stats['total_missing_hours'] += late_hours_dec + early_hours_dec
            stats['total_overtime_hours'] += overtime_decimal

            shift_windows_detail = breakdown['windows']
            late_in_str = f"{float(late_hours_display)*60:.0f} min" if late_hours_display else "-"
            early_out_str = f"{float(early_hours_dec)*60:.0f} min" if early_hours_dec else "-"

        elif present:
            status_badge = "Present"
            time_1 = memb.parse_time(str(aa))
            time_2 = memb.parse_time(str(bb))
            daily_worked_hrs = Decimal(str((time_2 - time_1).total_seconds())) / Decimal('3600')
            stats['total_hours_worked'] += daily_worked_hrs
            stats['days_present'] += 1

            late_in_str = memb.late_in() or "-"
            early_out_str = memb.early_out() or "-"

            # Precise (sub-minute) late-in / early-out / overtime deltas — computed
            # directly from timedeltas instead of round-tripping through the
            # "HH:MM"-string helpers (which floor to whole minutes).
            # effective_shift_start/end return None on a day with zero shift
            # windows (e.g. an explicit Duty Roster off-duty change) — falls
            # back to the member's own baseline shift time rather than crash,
            # same fallback shift_windows_detailed itself uses when no shift
            # is assigned at all.
            expected_start = memb.effective_shift_start(loop_date) or memb.shift_start_time
            expected_end = memb.effective_shift_end(loop_date) or memb.shift_end_time
            shift_start_dt = datetime.datetime.combine(time_1.date(), expected_start)
            shift_end_dt = datetime.datetime.combine(time_2.date(), expected_end)

            late_in_delta = time_1 - shift_start_dt if time_1 > shift_start_dt else datetime.timedelta(0)
            early_out_delta = shift_end_dt - time_2 if time_2 < shift_end_dt else datetime.timedelta(0)
            overtime_delta = time_2 - shift_end_dt if time_2 > shift_end_dt else datetime.timedelta(0)

            # Apply org-wide late grace: only lateness beyond the grace window is penalized.
            if late_in_delta <= grace_delta:
                late_in_delta = datetime.timedelta(0)
            else:
                late_in_delta = late_in_delta - grace_delta

            late_hours_dec = duration_to_decimal_hours(late_in_delta)
            early_hours_dec = duration_to_decimal_hours(early_out_delta)
            stats['total_missing_hours'] += late_hours_dec + early_hours_dec
            overtime_decimal = duration_to_decimal_hours(overtime_delta)
            stats['total_overtime_hours'] += overtime_decimal

        elif is_holiday or is_occasion:
            status_badge = "Holiday / Occasion"
            stats['days_holiday'] += 1

        elif is_leave:
            if is_paid_leave:
                status_badge = "Paid Leave"
                stats['days_leave'] += 1
                stats['days_paid_leave'] += 1
            else:
                status_badge = "Unpaid Leave"
                stats['days_leave'] += 1
                stats['days_unpaid_leave'] += 1
                stats['days_unpaid_absent'] += 1  # counts toward deduction

        else:
            stats['days_unpaid_absent'] += 1

        np_date_str = ""
        if nepali_enabled and nepali_datetime:
            try:
                np_date_str = str(
                    nepali_datetime.date.from_datetime_date(loop_date)
                )
            except Exception:
                pass

        # Single-letter status code + colour class for the monthly matrix report.
        if status_badge == "Present":
            # A present day whose attendance came from a field visit is
            # coded 'F' instead of plain 'P' so the report visually
            # distinguishes field-visit presence from a normal check-in —
            # it still counts as a present/worked day everywhere above
            # (stats['days_present'], worked hours, overtime); only the
            # display code changes.
            if show_field_visits and loop_date in field_visit_dates:
                code, code_class = 'F', 'f'
            else:
                code, code_class = 'P', 'p'
        elif status_badge == "Holiday / Occasion":
            if is_occasion:
                code, code_class = 'H', 'h'     # date-based holiday / occasion
            else:
                code, code_class = 'W', 'w'     # weekday weekly-off (weekend)
        elif status_badge == "Paid Leave":
            code, code_class = 'L', 'l'
        elif status_badge == "Unpaid Leave":
            code, code_class = 'L', 'l'
        elif show_field_visits and loop_date in field_visit_dates:
            code, code_class = 'F', 'f'         # absent day explained by a field visit
        else:
            code, code_class = 'A', 'a'         # absent

        daily_logs.append({
            'date': loop_date,
            'date_np': np_date_str,
            'punch_in': aa or "-",
            'punch_out': bb or "-",
            'worked_hrs': round(daily_worked_hrs, 2),
            'late_in': late_in_str,
            'early_out': early_out_str,
            'overtime_hrs': round(overtime_decimal, 2),
            'status': status_badge,
            'code': code,
            'code_class': code_class,
            # Raw decimals (full precision) for per-day money calculations,
            # kept separate from the display strings above.
            'late_hours_dec': late_hours_dec,
            'early_hours_dec': early_hours_dec,
            'overtime_hours_dec': overtime_decimal,
            'shift_windows': shift_windows_detail,
        })

        # Reset per-day state on the member object
        memb.first_date = None
        memb.last_date = None
        memb.date = None
        loop_date += delta

    return stats, daily_logs


# ─── payroll component calculation ────────────────────────────────────────────

def calculate_payroll_components(
    memb, stats, org, policy, end_date, daily_logs=None,
    extra_allowance=Decimal('0'), extra_bonus=Decimal('0'), extra_deduction=Decimal('0'),
    pf_employee_pct_override=None, ssf_employee_pct_override=None, tds_pct_override=None,
):
    """
    Given attendance stats for a period, compute every payroll component.

    Returns a dict with all earnings, deductions, and net payable.
    Policy is a PayrollPolicy instance.

    `extra_allowance`/`extra_bonus`/`extra_deduction` add on top of whatever
    active `PayrollAdjustment` rows already total (e.g. a one-time bulk-run
    top-up that isn't worth its own adjustment record). `*_pct_override`
    replace the member's/policy's own percentage for THIS calculation only —
    neither `memb` nor `policy` is ever saved here, so an override never
    changes anyone's actual stored settings; it only affects the numbers
    returned (and, when the caller persists them, the resulting PaySlip
    snapshot). This is what lets the Bulk Payslip preview show "what if"
    numbers per row without a risk of one row's tweak leaking into another's,
    or into the member's permanent profile.

    If `daily_logs` (the list from calculate_attendance_stats) is passed,
    each entry is mutated in place with an 'amount' key — that day's
    contribution to gross pay, for display/editing in the payslip UI.
    """
    base_salary = Decimal(str(memb.salary_amount or 0))
    sal_type = (memb.salary_type or 'monthly').lower()

    base_earnings = Decimal('0')
    gross_salary = Decimal('0')
    absent_deduction = Decimal('0')
    penalty_deduction = Decimal('0')
    per_day_rate = Decimal('0')
    hourly_rate = Decimal('0')
    total_days = stats['total_days']

    if sal_type == 'monthly':
        base_earnings = base_salary
        per_day_rate = base_earnings / Decimal(total_days) if total_days > 0 else Decimal('0')
        hourly_rate = per_day_rate / Decimal('8')
        # Holidays are normally a paid non-working day, but if the employee had
        # zero attendance the entire period, they shouldn't be paid for the
        # holidays either — treat those days as unpaid too.
        unpaid_days = stats['days_unpaid_absent']
        if stats['days_present'] == 0:
            unpaid_days += stats['days_holiday']
        absent_deduction = Decimal(unpaid_days) * per_day_rate
        penalty_deduction = stats['total_missing_hours'] * hourly_rate

    elif sal_type == 'daily':
        paid_days = stats['days_present'] + stats['days_paid_leave']
        # Same zero-attendance rule: holidays only count as paid days if the
        # employee was actually present at least once in the period.
        if stats['days_present'] > 0:
            paid_days += stats['days_holiday']
        per_day_rate = base_salary
        hourly_rate = per_day_rate / Decimal('8')
        base_earnings = Decimal(paid_days) * per_day_rate
        penalty_deduction = stats['total_missing_hours'] * hourly_rate

    elif sal_type == 'hourly':
        hourly_rate = base_salary
        shift_hours = duration_to_decimal_hours(
            datetime.datetime.combine(datetime.date.min, memb.shift_end_time)
            - datetime.datetime.combine(datetime.date.min, memb.shift_start_time)
        )
        paid_leave_earnings = Decimal(stats['days_paid_leave']) * shift_hours * hourly_rate
        base_earnings = stats['total_hours_worked'] * hourly_rate + paid_leave_earnings
        penalty_deduction = stats['total_missing_hours'] * hourly_rate

    # ── Overtime — hours worked past shift end, paid at a multiplier of the
    # employee's hourly rate (org default from PayrollPolicy, or a per-member
    # override). Folded into gross alongside the other worked-time-derived
    # components, before probation proration.
    effective_ot_multiplier = (
        memb.overtime_rate_multiplier_override
        if memb.overtime_rate_multiplier_override is not None
        else policy.overtime_rate_multiplier
    )
    overtime_amount = (
        stats['total_overtime_hours'] * hourly_rate * effective_ot_multiplier
    ).quantize(Decimal('0.01'))

    # ── Per-day amount breakdown (informational + editable in the UI) ──
    # A day only "earns" its base rate if it's a paid day (present, paid
    # leave, or a holiday — unless the employee had zero attendance the
    # whole period, matching the absent_deduction/paid_days rule above).
    if daily_logs is not None:
        paid_statuses = {'Present', 'Paid Leave', 'Holiday / Occasion'}
        holiday_paid = stats['days_present'] > 0
        for day in daily_logs:
            day_status = day.get('status')
            is_paid_day = day_status in paid_statuses and (
                day_status != 'Holiday / Occasion' or holiday_paid
            )
            if is_paid_day:
                day_base = (
                    day.get('worked_hrs', Decimal('0')) * hourly_rate
                    if sal_type == 'hourly' else per_day_rate
                )
                day_penalty = (
                    day.get('late_hours_dec', Decimal('0')) + day.get('early_hours_dec', Decimal('0'))
                ) * hourly_rate
                day_overtime = day.get('overtime_hours_dec', Decimal('0')) * hourly_rate * effective_ot_multiplier
                day_amount = day_base - day_penalty + day_overtime
            else:
                day_amount = Decimal('0')
            if day_amount < 0:
                day_amount = Decimal('0')
            day['amount'] = decimal_money(day_amount)

    gross_salary = base_earnings - absent_deduction - penalty_deduction + overtime_amount

    if gross_salary < 0:
        gross_salary = Decimal('0')

    # ── Active adjustments ──
    active_adjustments = PayrollAdjustment.objects.filter(
        org=org, member=memb, status='active', effective_date__lte=end_date,
    )
    allowance_total = _sum_adjustments(active_adjustments, 'allowance') + decimal_money(extra_allowance)
    bonus_total     = _sum_adjustments(active_adjustments, 'bonus') + decimal_money(extra_bonus)
    other_deduction = _sum_adjustments(active_adjustments, 'deduction') + decimal_money(extra_deduction)
    advance_deduction = _sum_adjustments(active_adjustments, 'advance')
    loan_deduction    = _sum_adjustments(active_adjustments, 'loan')

    # ── Also pull from dedicated AdvanceSalary model if it exists ──
    try:
        from handle.models import AdvanceSalary
        active_advances = AdvanceSalary.objects.filter(
            org=org, member=memb, status='active'
        )
        for adv in active_advances:
            advance_deduction += decimal_money(adv.installment_amount)
    except ImportError:
        pass

    # ── Probation ──
    gross_salary_dec = decimal_money(gross_salary)
    probation_adjustment = Decimal('0.00')
    is_on_probation = memb.is_on_probation(end_date)
    if is_on_probation:
        prob_pct = decimal_money(
            memb.probation_salary_percentage or policy.probation_salary_percentage
        )
        probation_salary = (
            gross_salary_dec * prob_pct / Decimal('100')
        ).quantize(Decimal('0.01'))
        probation_adjustment = gross_salary_dec - probation_salary
        gross_salary_dec = probation_salary

    # ── Add allowances, bonuses; subtract other deductions ──
    gross_salary_dec = gross_salary_dec + allowance_total + bonus_total - other_deduction
    if gross_salary_dec < Decimal('0.00'):
        gross_salary_dec = Decimal('0.00')

    # ── Statutory deductions ──
    tax_pct = decimal_money(tds_pct_override) if tds_pct_override is not None else decimal_money(memb.tax_percentage)
    pf_employee_pct = decimal_money(pf_employee_pct_override) if pf_employee_pct_override is not None else policy.pf_employee_percentage
    ssf_employee_pct = decimal_money(ssf_employee_pct_override) if ssf_employee_pct_override is not None else policy.ssf_employee_percentage

    tax_amount  = (gross_salary_dec * tax_pct / Decimal('100')).quantize(Decimal('0.01'))
    pf_employee = (
        (gross_salary_dec * pf_employee_pct / Decimal('100')).quantize(Decimal('0.01'))
        if memb.pf_enabled else Decimal('0.00')
    )
    pf_employer = (
        (gross_salary_dec * policy.pf_employer_percentage / Decimal('100')).quantize(Decimal('0.01'))
        if memb.pf_enabled else Decimal('0.00')
    )
    ssf_employee = (
        (gross_salary_dec * ssf_employee_pct / Decimal('100')).quantize(Decimal('0.01'))
        if memb.ssf_enabled else Decimal('0.00')
    )
    ssf_employer = (
        (gross_salary_dec * policy.ssf_employer_percentage / Decimal('100')).quantize(Decimal('0.01'))
        if memb.ssf_enabled else Decimal('0.00')
    )

    net_payable = (
        gross_salary_dec
        - tax_amount - pf_employee - ssf_employee
        - advance_deduction - loan_deduction
    )
    if net_payable < Decimal('0.00'):
        net_payable = Decimal('0.00')

    return {
        # Attendance summary
        'base_earnings': round(base_earnings, 2),
        'per_day_rate': round(per_day_rate, 2),
        'hourly_rate': round(hourly_rate, 2),
        'absent_deduction': round(absent_deduction, 2),
        'penalty_deduction': round(penalty_deduction, 2),
        'overtime_hours': round(stats['total_overtime_hours'], 4),
        'effective_ot_multiplier': effective_ot_multiplier,

        # Earnings
        'gross_salary': gross_salary_dec,
        'overtime_amount': overtime_amount,
        'allowance_total': allowance_total,
        'bonus_total': bonus_total,
        'probation_adjustment': probation_adjustment,
        'is_on_probation': is_on_probation,

        # Deductions
        'advance_deduction': advance_deduction,
        'loan_deduction': loan_deduction,
        'other_deduction': other_deduction,
        'tax_amount': tax_amount,
        'tax_pct': tax_pct,
        'pf_employee': pf_employee,
        'pf_employer': pf_employer,
        'pf_employee_pct': pf_employee_pct,
        'ssf_employee': ssf_employee,
        'ssf_employer': ssf_employer,
        'ssf_employee_pct': ssf_employee_pct,

        # Final
        'net_payable': net_payable,

        # References for marking applied
        'active_adjustments': active_adjustments,
    }


def get_or_create_policy(org):
    """Return the PayrollPolicy for this org, creating defaults if needed."""
    policy, _ = PayrollPolicy.objects.get_or_create(org=org)
    return policy
