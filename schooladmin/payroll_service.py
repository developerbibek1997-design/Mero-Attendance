"""
Payroll Service — centralised payroll calculation for Mero Attendance.

Both individual payslip generation (paySlipDetailView) and bulk payslip
generation (BulkPayslipView) call these helpers so the maths is always
identical and maintained in one place.
"""

from decimal import Decimal
import datetime

from handle.models import (
    AttendanceRecord, PayrollAdjustment, PayrollPolicy,
)
from management.models import LeaveReport, Holiday, Occasion


# ─── tiny utilities ────────────────────────────────────────────────────────────

def time_to_decimal(time_str):
    """'HH:MM' → float hours. Returns 0.0 on any parse error."""
    if not time_str or time_str == '-':
        return 0.0
    try:
        h, m = map(int, str(time_str).split(':'))
        return h + (m / 60.0)
    except Exception:
        return 0.0


def decimal_money(value):
    return Decimal(str(value or 0)).quantize(Decimal('0.01'))


def _sum_adjustments(queryset, adjustment_type):
    from django.db.models import Sum
    total = queryset.filter(adjustment_type=adjustment_type).aggregate(
        t=Sum('amount')
    )['t'] or Decimal('0.00')
    return decimal_money(total)


# ─── attendance stats ──────────────────────────────────────────────────────────

def calculate_attendance_stats(memb, start_date, end_date, org, nepali_enabled=False):
    """
    Walk every calendar day in [start_date, end_date] and classify it.

    Returns:
        stats  – dict with counters and totals
        daily_logs – list of per-day dicts (for the payslip preview table)
    """
    try:
        import nepali_datetime
    except ImportError:
        nepali_datetime = None

    holidays = Holiday.objects.filter(org=org)
    occasions = Occasion.objects.filter(org=org)
    approved_leaves = LeaveReport.objects.filter(
        member=memb, approved=True
    ).select_related('leave_type')

    total_days = (end_date - start_date).days + 1

    stats = {
        'total_days': total_days,
        'days_present': 0,
        'days_leave': 0,
        'days_paid_leave': 0,
        'days_unpaid_leave': 0,
        'days_holiday': 0,
        'days_unpaid_absent': 0,
        'total_hours_worked': 0.0,
        'total_missing_hours': 0.0,
    }

    daily_logs = []
    loop_date = start_date
    delta = datetime.timedelta(days=1)

    while loop_date <= end_date:
        is_holiday = any(h.holiday == loop_date.strftime("%A") for h in holidays)
        is_occasion = occasions.filter(
            date__lte=loop_date, end_date__gte=loop_date
        ).exists()

        leave_record = approved_leaves.filter(
            gap_start__lte=loop_date, gap_end__gte=loop_date
        ).first()
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

        daily_worked_hrs = 0.0
        status_badge = "Absent"
        late_in_str = "-"
        early_out_str = "-"

        if aa and bb:
            status_badge = "Present"
            time_1 = memb.parse_time(str(aa))
            time_2 = memb.parse_time(str(bb))
            daily_worked_hrs = (time_2 - time_1).total_seconds() / 3600
            stats['total_hours_worked'] += daily_worked_hrs
            stats['days_present'] += 1

            late_in_str = memb.late_in() or "-"
            early_out_str = memb.early_out() or "-"
            stats['total_missing_hours'] += (
                time_to_decimal(late_in_str) + time_to_decimal(early_out_str)
            )

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

        daily_logs.append({
            'date': loop_date,
            'date_np': np_date_str,
            'punch_in': aa or "-",
            'punch_out': bb or "-",
            'worked_hrs': round(daily_worked_hrs, 2),
            'late_in': late_in_str,
            'early_out': early_out_str,
            'status': status_badge,
        })

        # Reset per-day state on the member object
        memb.first_date = None
        memb.last_date = None
        memb.date = None
        loop_date += delta

    return stats, daily_logs


# ─── payroll component calculation ────────────────────────────────────────────

def calculate_payroll_components(memb, stats, org, policy, end_date):
    """
    Given attendance stats for a period, compute every payroll component.

    Returns a dict with all earnings, deductions, and net payable.
    Policy is a PayrollPolicy instance.
    """
    base_salary_float = float(memb.salary_amount or 0)
    sal_type = (memb.salary_type or 'monthly').lower()

    base_earnings = 0.0
    gross_salary = 0.0
    absent_deduction = 0.0
    penalty_deduction = 0.0
    per_day_rate = 0.0
    hourly_rate = 0.0
    total_days = stats['total_days']

    if sal_type == 'monthly':
        base_earnings = base_salary_float
        per_day_rate = base_earnings / total_days if total_days > 0 else 0
        hourly_rate = per_day_rate / 8.0
        absent_deduction = stats['days_unpaid_absent'] * per_day_rate
        penalty_deduction = stats['total_missing_hours'] * hourly_rate
        gross_salary = base_earnings - absent_deduction - penalty_deduction

    elif sal_type == 'daily':
        paid_days = (
            stats['days_present'] + stats['days_paid_leave'] + stats['days_holiday']
        )
        per_day_rate = base_salary_float
        hourly_rate = per_day_rate / 8.0
        base_earnings = paid_days * per_day_rate
        penalty_deduction = stats['total_missing_hours'] * hourly_rate
        gross_salary = base_earnings - penalty_deduction

    elif sal_type == 'hourly':
        hourly_rate = base_salary_float
        base_earnings = stats['total_hours_worked'] * hourly_rate
        gross_salary = base_earnings

    if gross_salary < 0:
        gross_salary = 0.0

    # ── Active adjustments ──
    active_adjustments = PayrollAdjustment.objects.filter(
        org=org, member=memb, status='active', effective_date__lte=end_date,
    )
    allowance_total = _sum_adjustments(active_adjustments, 'allowance')
    bonus_total     = _sum_adjustments(active_adjustments, 'bonus')
    other_deduction = _sum_adjustments(active_adjustments, 'deduction')
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
    tax_amount  = (gross_salary_dec * decimal_money(memb.tax_percentage) / Decimal('100')).quantize(Decimal('0.01'))
    pf_employee = (
        (gross_salary_dec * policy.pf_employee_percentage / Decimal('100')).quantize(Decimal('0.01'))
        if memb.pf_enabled else Decimal('0.00')
    )
    pf_employer = (
        (gross_salary_dec * policy.pf_employer_percentage / Decimal('100')).quantize(Decimal('0.01'))
        if memb.pf_enabled else Decimal('0.00')
    )
    ssf_employee = (
        (gross_salary_dec * policy.ssf_employee_percentage / Decimal('100')).quantize(Decimal('0.01'))
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

        # Earnings
        'gross_salary': gross_salary_dec,
        'allowance_total': allowance_total,
        'bonus_total': bonus_total,
        'probation_adjustment': probation_adjustment,
        'is_on_probation': is_on_probation,

        # Deductions
        'advance_deduction': advance_deduction,
        'loan_deduction': loan_deduction,
        'other_deduction': other_deduction,
        'tax_amount': tax_amount,
        'pf_employee': pf_employee,
        'pf_employer': pf_employer,
        'ssf_employee': ssf_employee,
        'ssf_employer': ssf_employer,

        # Final
        'net_payable': net_payable,

        # References for marking applied
        'active_adjustments': active_adjustments,
    }


def get_or_create_policy(org):
    """Return the PayrollPolicy for this org, creating defaults if needed."""
    policy, _ = PayrollPolicy.objects.get_or_create(org=org)
    return policy
