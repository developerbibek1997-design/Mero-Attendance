from decimal import Decimal
import csv
import io
import json
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment

from django.http import HttpResponseRedirect, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
import nepali_datetime
from handle.models import AttendingClassification, member
from django.views.generic.list import ListView
from handle.models import AttendanceRecord
import datetime
from datetime import datetime as dt
from handle.models import Classification, PaySlip
from handle.models import Device
from management.models import CustomUser, LeaveReport, LeaveType, WifiBased
from handle.forms import PayrollAdjustmentForm, PayrollPolicyForm, PaySlipForm, ProbationReviewForm
from django.urls import reverse
from django.contrib import messages
from .forms import OrgFormSchool
from handle.models import (
    PayrollAdjustment,
    PayrollPolicy,
    ProvidentFundRecord,
    ProbationReview,
    SocialSecurityFundRecord,
    Staff,
    member,
    Classification,
    Branch,
    Section,
    Course,
    CourseAttendance,
    AttendanceGap,
    FinancialTransaction,
    TransactionCategory,
    StockItem,
    StockMovement,
    StockCategory,
    Subject,
    ExamTerm,
    ResultRecord,
    Event,
    EventStockUsage,
    Complaint,
    ResignationRecord,
    StaffDocument,
)
from management.models import Holiday, Occasion
from django.conf import settings
from collections import defaultdict
from django.db.models.functions import TruncDate
from datetime import timedelta
from django.utils import timezone
from django.db.models import Min, Max, Sum, Count, Q, F
import nepali_datetime
from django.core.mail import send_mail
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.template.loader import render_to_string
from management.models import LocationBased, QRCode, AutoCheckin

from .forms import LocationForm, QRCodeForm, AutoCheckinForm


def _require_admin(request):
    """Return an error response if the user is not a schooladmin (user_type=2).
    Returns None if access is allowed.
    Usage: err = _require_admin(request); if err: return err
    """
    if not request.user.is_authenticated:
        from django.contrib.auth.views import redirect_to_login
        return redirect_to_login(request.get_full_path())
    if request.user.user_type not in ('1', '2'):
        messages.error(request, "You do not have permission to access this page.")
        return redirect('management:login')
    return None


class AdminRequiredMixin:
    """Mixin that blocks non-admin users from any admin view."""
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('management:login')
        if request.user.user_type not in ('1', '2'):
            messages.error(request, "Access denied. Admins only.")
            return redirect('management:login')
        return super().dispatch(request, *args, **kwargs)


class PayrollSettingsView(View):
    template_name = 'admin/payroll_settings.html'

    def get_org(self, request):
        if request.user.user_type == "2":
            return request.user.schooladmin.org
        if request.user.user_type == "3":
            return request.user.staff.org
        return None

    def get(self, request, *args, **kwargs):
        org = self.get_org(request)
        policy, _ = PayrollPolicy.objects.get_or_create(org=org)
        today = timezone.localdate()
        reminders_until = today + timedelta(days=policy.probation_reminder_days)
        probation_members = member.objects.filter(
            org=org,
            probation_end_date__isnull=False,
            probation_end_date__gte=today,
            probation_end_date__lte=reminders_until,
        ).order_by('probation_end_date')

        context = {
            'org': org,
            'policy': policy,
            'policy_form': PayrollPolicyForm(instance=policy),
            'adjustment_form': PayrollAdjustmentForm(org=org),
            'review_form': ProbationReviewForm(org=org),
            'adjustments': PayrollAdjustment.objects.filter(org=org).select_related('member', 'created_by')[:30],
            'probation_reviews': ProbationReview.objects.filter(org=org).select_related('member', 'reviewer')[:30],
            'probation_members': probation_members,
            'pf_records': ProvidentFundRecord.objects.filter(org=org).select_related('member', 'payslip')[:20],
            'ssf_records': SocialSecurityFundRecord.objects.filter(org=org).select_related('member', 'payslip')[:20],
        }
        return render(request, self.template_name, context)

    def post(self, request, *args, **kwargs):
        org = self.get_org(request)
        action = request.POST.get('action')
        policy, _ = PayrollPolicy.objects.get_or_create(org=org)

        if action == 'policy':
            form = PayrollPolicyForm(request.POST, instance=policy)
            if form.is_valid():
                form.save()
                messages.success(request, "Payroll policy updated successfully.")
            else:
                messages.error(request, "Could not update payroll policy: " + form.errors.as_text())

        elif action == 'adjustment':
            form = PayrollAdjustmentForm(request.POST, org=org)
            if form.is_valid():
                adjustment = form.save(commit=False)
                adjustment.org = org
                adjustment.created_by = request.user
                adjustment.save()
                messages.success(request, "Payroll adjustment saved successfully.")
            else:
                messages.error(request, "Could not save adjustment: " + form.errors.as_text())

        elif action == 'review':
            form = ProbationReviewForm(request.POST, org=org)
            if form.is_valid():
                review = form.save(commit=False)
                review.org = org
                review.reviewer = request.user
                review.save()
                review.member.probation_review_status = review.status
                if review.status == 'passed':
                    review.member.status = 'active'
                    review.member.staff_type = 'permanent'
                elif review.status == 'extended':
                    review.member.status = 'probation'
                    review.member.staff_type = 'probation'
                review.member.save(update_fields=['probation_review_status', 'status', 'staff_type'])
                messages.success(request, "Probation review saved successfully.")
            else:
                messages.error(request, "Could not save review: " + form.errors.as_text())

        else:
            messages.error(request, "Invalid payroll settings action.")

        return HttpResponseRedirect(reverse('schooladmin:payroll_settings'))


class ManageLeaveTypesView(View):
    template_name = 'admin/manage_leave_types.html'

    def get(self, request, *args, **kwargs):
        org = request.user.schooladmin.org
        # Fetch all leave policies for this organization
        leave_types = LeaveType.objects.filter(org=org).order_by('-id')
        
        dist = {
            'leave_types': leave_types
        }
        return render(request, self.template_name, dist)

    def post(self, request, *args, **kwargs):
        org = request.user.schooladmin.org
        action = request.POST.get('action')

        try:
            # ACTION 1: Create New Leave Policy
            if action == 'add':
                name = request.POST.get('name')
                allocation = request.POST.get('annual_allocation')
                
                LeaveType.objects.create(
                    org=org,
                    name=name,
                    annual_allocation=allocation,
                    is_paid=request.POST.get('is_paid') == 'on',
                )
                messages.success(request, f"Policy '{name}' created successfully.")

            # ACTION 2: Edit Existing Policy
            elif action == 'edit':
                leave_id = request.POST.get('leave_id')
                name = request.POST.get('name')
                allocation = request.POST.get('annual_allocation')

                l_type = LeaveType.objects.get(id=leave_id, org=org)
                l_type.name = name
                l_type.annual_allocation = allocation
                l_type.is_paid = request.POST.get('is_paid') == 'on'
                l_type.save()
                messages.success(request, f"Policy '{name}' updated successfully.")

            # ACTION 3: Delete Policy
            elif action == 'delete':
                leave_id = request.POST.get('leave_id')
                l_type = LeaveType.objects.get(id=leave_id, org=org)
                policy_name = l_type.name
                l_type.delete()
                messages.warning(request, f"Policy '{policy_name}' has been permanently deleted.")

        except Exception as e:
            messages.error(request, f"An error occurred: {str(e)}")

        return redirect('schooladmin:manage_leave_types')
    
class MasterLeaveReportView(View):
    template_name = 'admin/master_leave_report.html'

    def get(self, request, *args, **kwargs):
        org = request.user.schooladmin.org
        members = member.objects.filter(org=org)
        leave_types = LeaveType.objects.filter(org=org)

        master_data = []
        for mem in members:
            # Gather balance for every policy for this specific member
            balances = []
            for l_type in leave_types:
                balances.append({
                    'type_name': l_type.name,
                    'data': mem.get_leave_balance(l_type.id)
                })
            
            master_data.append({
                'member': mem,
                'balances': balances
            })

        dist = {
            'leave_types': leave_types,
            'master_data': master_data
        }
        return render(request, self.template_name, dist)



class AdminLogLeaveView(View):
    template_name = 'admin/log_leave.html'

    def get(self, request, *args, **kwargs):
        org = request.user.schooladmin.org
        dist = {
            'members': member.objects.filter(org=org),
            'leave_types': LeaveType.objects.filter(org=org),
            'today': datetime.date.today().strftime('%Y-%m-%d')
        }
        return render(request, self.template_name, dist)

    def post(self, request, *args, **kwargs):
        org = request.user.schooladmin.org
        member_id = request.POST.get('member_id')
        leave_type_id = request.POST.get('leave_type_id')
        start_date_str = request.POST.get('start_date')
        end_date_str = request.POST.get('end_date')
        reason = request.POST.get('reason', 'Admin assigned leave.')

        if not all([member_id, leave_type_id, start_date_str, end_date_str]):
            messages.error(request, "All fields are required.")
            return redirect('schooladmin:log_leave')

        mem = member.objects.get(id=member_id, org=org)
        l_type = LeaveType.objects.get(id=leave_type_id, org=org)
        
        start_date = datetime.datetime.strptime(start_date_str, "%Y-%m-%d").date()
        end_date = datetime.datetime.strptime(end_date_str, "%Y-%m-%d").date()

        # 1. Validation Check
        requested_days = (end_date - start_date).days + 1
        if requested_days <= 0:
            messages.error(request, "End date must be after or equal to Start date.")
            return redirect('schooladmin:log_leave')

        # 2. Balance Check
        balance = mem.get_leave_balance(l_type.id)
        if requested_days > balance['remaining']:
            messages.error(
                request, 
                f"Action Denied: {mem.name} only has {balance['remaining']} days of {l_type.name} left. "
                f"(Requested: {requested_days} days)"
            )
            return redirect('schooladmin:log_leave')

        # 3. Create the Leave Record (Auto-Approved)
        LeaveReport.objects.create(
            member=mem,
            org=org,
            leave_type=l_type,
            gap_start=start_date,
            gap_end=end_date,
            reason=reason,
            approved=True,  # Auto-approved because Admin logged it
            seen=True
        )

        messages.success(request, f"Successfully logged {requested_days} days of {l_type.name} for {mem.name}.")
        return redirect('schooladmin:log_leave')

def location_list(request):
    org = request.user.schooladmin.org
    locations = LocationBased.objects.filter(org = org)
    return render(request, 'admin/location_list.html', {'locations': locations})

def location_add(request):
    org = request.user.schooladmin.org
    print(org.id)

    if request.method == 'POST':
        form = LocationForm(request.POST)
        form.initial['org'] = org.id
        if form.is_valid():
            location = form.save(commit=False) 
            location.org = org  
            location.save()
            messages.success(request, "Succesfully added location data")
            return redirect('schooladmin:location_list')
    else:
        form = LocationForm()
    return render(request, 'admin/add_location.html', {'form': form})

def location_edit(request, id):
    location = get_object_or_404(LocationBased, id=id)
    form = LocationForm(request.POST or None, instance=location)
    if form.is_valid():
        form.save()
        messages.success(request, "Succesfully edited location details")
        return redirect('schooladmin:location_list')
    return render(request, 'admin/add_location.html', {'form': form})

def location_delete(request, id):
    location = get_object_or_404(LocationBased, id=id)
    location.delete()
    messages.success(request, "Succesfully deleted location details")
    return redirect('schooladmin:location_list')


def qrcode_list(request):
    org = request.user.schooladmin.org
    qrcodes = QRCode.objects.filter(org = org)
    return render(request, 'admin/qrcode_list.html', {'qrcodes': qrcodes})

def qrcode_add(request):

    org = request.user.schooladmin.org
   
    if request.method == 'POST':
        form = QRCodeForm(request.POST, request.FILES)
        form.initial['org'] = org.id
        if form.is_valid():
            location = form.save(commit=False) 
            location.org = org  
            location.save()
            messages.success(request, "Succesfully added QR code data")
            return redirect('schooladmin:qrcode_list')
    else:
        form = QRCodeForm()
    return render(request, 'admin/add_qrcode.html', {'form': form})

def qrcode_edit(request, id):
    qrcode = get_object_or_404(QRCode, id=id)
    form = QRCodeForm(request.POST or None, request.FILES or None, instance=qrcode)
    if form.is_valid():
        form.save()
        messages.success(request, "Succesfully edited qr code")
        return redirect('schooladmin:qrcode_list')
        
    return render(request, 'admin/add_qrcode.html', {'form': form})

def qrcode_delete(request, id):
    qrcode = get_object_or_404(QRCode, id=id)
    qrcode.delete()
    messages.success(request, "Succesfully deleted QR code")
    return redirect('schooladmin:qrcode_list')

def auto_checkin_list(request):
    org = request.user.schooladmin.org
    records = AutoCheckin.objects.filter(org = org)
    return render(request, 'admin/autocheckin_list.html', {'records': records})


# Helper to sync AutoCheckin with AttendanceRecord
def sync_attendance_records(auto_obj, action='create'):
    # Remove old attendance records linked to this specific AutoCheckin record
    AttendanceRecord.objects.filter(mem=auto_obj.member, scanned_time=auto_obj.checkin_time).delete()
    AttendanceRecord.objects.filter(mem=auto_obj.member, scanned_time=auto_obj.checkout_time).delete()
    
    if action == 'create' or action == 'edit':
        # Create new ones directly. Do NOT use timezone.make_aware() 
        # because auto_obj.checkin_time is already timezone-aware.
        AttendanceRecord.objects.create(
            mem=auto_obj.member, 
            org=auto_obj.org, 
            scanned_time=auto_obj.checkin_time
        )
        AttendanceRecord.objects.create(
            mem=auto_obj.member, 
            org=auto_obj.org, 
            scanned_time=auto_obj.checkout_time
        )

def auto_checkin_add(request):
    org = request.user.schooladmin.org
    if request.method == 'POST':
        form = AutoCheckinForm(request.POST, org=org)
        if form.is_valid():
            auto = form.save(commit=False)
            auto.org = org
            auto.save()
            sync_attendance_records(auto, action='create')
            messages.success(request, "Auto-check-in log created successfully.")
            return redirect('schooladmin:auto_checkin_list')
    else:
        form = AutoCheckinForm(org=org)
    return render(request, 'admin/add_autocheckin.html', {'form': form})

def auto_checkin_edit(request, id):
    record = get_object_or_404(AutoCheckin, id=id)
    if request.method == 'POST':
        form = AutoCheckinForm(request.POST, instance=record)
        if form.is_valid():
            # Update the AutoCheckin instance
            updated_record = form.save()
            # Re-sync with AttendanceRecords
            sync_attendance_records(updated_record, action='edit')
            messages.success(request, "Auto-check-in log updated.")
            return redirect('schooladmin:auto_checkin_list')
    else:
        form = AutoCheckinForm(instance=record)
    return render(request, 'admin/add_autocheckin.html', {'form': form})

def auto_checkin_delete(request, id):
    record = get_object_or_404(AutoCheckin, id=id)
    # Cleanup AttendanceRecords
    sync_attendance_records(record, action='delete')
    record.delete()
    messages.success(request, "Auto-check-in log removed.")
    return redirect('schooladmin:auto_checkin_list')


def attendance_analytics(request):
    org = request.user.schooladmin.org if hasattr(request.user, 'schooladmin') else None
    nepali_enabled = getattr(org, 'nepali_date', False)

    # --- 1. DATE RANGE LOGIC ---
    end_date = timezone.now()
    start_date = end_date - timedelta(days=30)
    
    date_range = request.GET.get('date_range', '30days')
    custom_start = request.GET.get('custom_start')
    custom_end = request.GET.get('custom_end')
    classification_id = request.GET.get('classification')

    custom_start_np = request.GET.get('custom_start_np')
    custom_end_np = request.GET.get('custom_end_np')
    
    if date_range == 'custom':
        if nepali_enabled and custom_start_np and custom_end_np:
            try:
                y1, m1, d1 = map(int, custom_start_np.replace('/', '-').strip().split('-'))
                start_date_obj = nepali_datetime.date(y1, m1, d1).to_datetime_date()
                start_date = timezone.make_aware(datetime.datetime.combine(start_date_obj, datetime.datetime.min.time()))
                
                y2, m2, d2 = map(int, custom_end_np.replace('/', '-').strip().split('-'))
                end_date_obj = nepali_datetime.date(y2, m2, d2).to_datetime_date()
                end_date = timezone.make_aware(datetime.datetime.combine(end_date_obj, datetime.datetime.max.time()))
            except Exception:
                pass 
        elif custom_start and custom_end:
            try:
                start_date = timezone.make_aware(datetime.datetime.strptime(custom_start, '%Y-%m-%d'))
                end_date = timezone.make_aware(datetime.datetime.strptime(custom_end, '%Y-%m-%d').replace(hour=23, minute=59, second=59))
            except Exception:
                pass
                
    elif date_range == '7days':
        start_date = end_date - timedelta(days=7)
    elif date_range == 'month':
        start_date = end_date.replace(day=1)
    elif date_range == 'year':
        start_date = end_date.replace(month=1, day=1)
    
    total_days = (end_date - start_date).days + 1
    if total_days <= 0: total_days = 1

    # --- 2. SUPER-FAST AGGREGATED QUERY ---
    records = AttendanceRecord.objects.filter(org=org, scanned_time__range=[start_date, end_date])
    if classification_id and classification_id != 'all':
        records = records.filter(mem__classification_id=classification_id)

    daily_stats = records.annotate(date=TruncDate('scanned_time')).values('mem', 'date').annotate(
        first_in=Min('scanned_time'),
        last_out=Max('scanned_time')
    )

    # --- 3. DATA PROCESSING & ANOMALY DETECTION ---
    raw_stats = defaultdict(lambda: {'days_present': 0, 'total_seconds': 0, 'incomplete_logs': 0})
    
    for stat in daily_stats:
        mem_id = stat['mem']
        raw_stats[mem_id]['days_present'] += 1
        
        # Check for Check-out Gaps
        if stat['last_out'] > stat['first_in']:
            delta = stat['last_out'] - stat['first_in']
            raw_stats[mem_id]['total_seconds'] += delta.total_seconds()
        else:
            # They punched in, but never punched out
            raw_stats[mem_id]['incomplete_logs'] += 1

    member_qs = member.objects.filter(org=org).select_related('classification')
    if classification_id and classification_id != 'all':
        member_qs = member_qs.filter(classification_id=classification_id)
    
    member_dict = {m.id: m for m in member_qs}
    member_stats = []
    attendance_summary = defaultdict(lambda: defaultdict(int))
    total_org_missed_punches = 0

    def format_time(seconds):
        hours, remainder = divmod(int(seconds), 3600)
        minutes, _ = divmod(remainder, 60)
        return f"{hours}h {minutes}m"

    for mem_id, m in member_dict.items():
        data = raw_stats.get(mem_id, {'days_present': 0, 'total_seconds': 0, 'incomplete_logs': 0})
        
        days_present = data['days_present']
        days_absent = total_days - days_present
        if days_absent < 0: days_absent = 0
        
        total_seconds = data['total_seconds']
        incomplete_logs = data['incomplete_logs']
        total_org_missed_punches += incomplete_logs
        
        avg_seconds = total_seconds / days_present if days_present > 0 else 0
        
        attendance_percentage = round((days_present / total_days) * 100, 1)
        if attendance_percentage > 100: attendance_percentage = 100
        
        absence_percentage = round((days_absent / total_days) * 100, 1)
        if absence_percentage > 100: absence_percentage = 100

        dept_name = m.classification.name if m.classification else "Unclassified"
        if days_present > 0:
            attendance_summary[dept_name][m.name] = days_present

        member_stats.append({
            'member': m,
            'days_present': days_present,
            'days_absent': days_absent,
            'percentage': attendance_percentage,
            'absence_percentage': absence_percentage,
            'total_seconds': total_seconds,
            'formatted_total': format_time(total_seconds),
            'avg_seconds': avg_seconds,
            'formatted_avg': format_time(avg_seconds),
            'incomplete_logs': incomplete_logs
        })

    attendance_summary = {
        cls: dict(sorted(members_dict.items(), key=lambda item: item[1], reverse=True))
        for cls, members_dict in attendance_summary.items()
    }

    # --- 4. RANKING & SORTING ---
    most_present = sorted(member_stats, key=lambda x: x['days_present'], reverse=True)[:5]
    most_absent = sorted(member_stats, key=lambda x: x['days_absent'], reverse=True)[:5] # GAP ANALYSIS
    most_time_spent = sorted(member_stats, key=lambda x: x['total_seconds'], reverse=True)[:5]
    most_incomplete = sorted([m for m in member_stats if m['incomplete_logs'] > 0], key=lambda x: x['incomplete_logs'], reverse=True)[:5] # MISSED PUNCHES
    
    start_date_np_display = ""
    end_date_np_display = ""
    if nepali_enabled:
        try:
            start_date_np_display = str(nepali_datetime.date.from_datetime_date(start_date.date()))
            end_date_np_display = str(nepali_datetime.date.from_datetime_date(end_date.date()))
        except:
            pass
    
    # --- 5. ALL MEMBERS SORTED (for full absent leaderboard) ---
    all_absent_sorted = sorted(member_stats, key=lambda x: x['days_absent'], reverse=True)

    # --- 6. STUDY GAPS (AttendanceGap model) ---
    from django.db.models.functions import TruncMonth
    gap_qs = AttendanceGap.objects.filter(org=org, date__range=[start_date.date(), end_date.date()])
    if classification_id and classification_id != 'all':
        gap_qs = gap_qs.filter(classification_id=classification_id)
    top_gap_members = (
        gap_qs.values('member__id', 'member__name', 'member__classification__name')
        .annotate(gap_count=Count('id'))
        .order_by('-gap_count')[:10]
    )

    # --- 7. FINANCIAL SUMMARY ---
    sd_date = start_date.date() if hasattr(start_date, 'date') else start_date
    ed_date = end_date.date() if hasattr(end_date, 'date') else end_date
    fin_qs = FinancialTransaction.objects.filter(org=org, transaction_date__range=[sd_date, ed_date])
    total_income  = fin_qs.filter(transaction_type='income').aggregate(t=Sum('amount'))['t'] or 0
    total_expense = fin_qs.filter(transaction_type='expense').aggregate(t=Sum('amount'))['t'] or 0

    # Monthly income/expense for chart (last 6 months)
    import calendar as _cal
    today = datetime.date.today()
    monthly_finance = []
    for i in range(5, -1, -1):
        month_dt = today.replace(day=1) - timedelta(days=i * 30)
        month_dt = month_dt.replace(day=1)
        last_day = _cal.monthrange(month_dt.year, month_dt.month)[1]
        month_end = month_dt.replace(day=last_day)
        inc = FinancialTransaction.objects.filter(
            org=org, transaction_type='income',
            transaction_date__range=[month_dt, month_end]
        ).aggregate(t=Sum('amount'))['t'] or 0
        exp = FinancialTransaction.objects.filter(
            org=org, transaction_type='expense',
            transaction_date__range=[month_dt, month_end]
        ).aggregate(t=Sum('amount'))['t'] or 0
        monthly_finance.append({
            'month': month_dt.strftime('%b %Y'),
            'income': float(inc),
            'expense': float(exp),
        })

    # --- 8. PAYSLIP SUMMARY ---
    payslip_qs = PaySlip.objects.filter(org=org, from_date__gte=sd_date, to_date__lte=ed_date)
    total_salary_paid = payslip_qs.filter(status='paid').aggregate(t=Sum('net_payable'))['t'] or 0
    total_payslips    = payslip_qs.count()

    # --- 9. LEAVE SUMMARY ---
    leave_qs = LeaveReport.objects.filter(org=org, gap_start__gte=sd_date, gap_start__lte=ed_date)
    total_leaves   = leave_qs.count()
    approved_leaves= leave_qs.filter(approved=True).count()
    pending_leaves = leave_qs.filter(approved=False, rejected=False).count()

    # Top leave takers
    top_leave_members = (
        leave_qs.filter(approved=True)
        .values('member__id', 'member__name', 'member__classification__name')
        .annotate(leave_count=Count('id'))
        .order_by('-leave_count')[:8]
    )

    # Dept-wise absent for chart
    dept_absent_chart = {}
    for stat in member_stats:
        dept = stat['member'].classification.name if stat['member'].classification else 'Unclassified'
        dept_absent_chart[dept] = dept_absent_chart.get(dept, 0) + stat['days_absent']

    context = {
        'org': org,
        'classifications': Classification.objects.filter(org=org),
        'most_present': most_present,
        'most_absent': most_absent,
        'most_time_spent': most_time_spent,
        'most_incomplete': most_incomplete,
        'all_absent_sorted': all_absent_sorted[:20],
        'total_org_missed_punches': total_org_missed_punches,
        'total_days': total_days,
        'start_date': start_date,
        'end_date': end_date,
        'start_date_np': start_date_np_display,
        'end_date_np': end_date_np_display,
        'custom_start_np': custom_start_np,
        'custom_end_np': custom_end_np,
        'nepali_enabled': nepali_enabled,
        'selected_range': date_range,
        'selected_classification': classification_id,
        'custom_start': custom_start,
        'custom_end': custom_end,
        'classifi': dict(attendance_summary),
        # gaps
        'top_gap_members': list(top_gap_members),
        'total_gaps': gap_qs.count(),
        # finance
        'total_income': total_income,
        'total_expense': total_expense,
        'net_balance': float(total_income) - float(total_expense),
        'monthly_finance_json': json.dumps(monthly_finance),
        # payroll
        'total_salary_paid': total_salary_paid,
        'total_payslips': total_payslips,
        # leave
        'total_leaves': total_leaves,
        'approved_leaves': approved_leaves,
        'pending_leaves': pending_leaves,
        'top_leave_members': list(top_leave_members),
        # charts
        'dept_absent_json': json.dumps([
            {'dept': k, 'absent': v} for k, v in sorted(dept_absent_chart.items(), key=lambda x: x[1], reverse=True)[:8]
        ]),
        'absent_chart_json': json.dumps([
            {'name': s['member'].name, 'absent': s['days_absent'], 'pct': s['absence_percentage']}
            for s in all_absent_sorted[:10]
        ]),
    }

    return render(request, 'admin/highest.html', context)
class AllRecord(ListView):
    model = AttendanceRecord
    paginate_by = 100
    template_name = 'admin/allReport.html'

    def get_context_data(self, request, **kwargs):
        today_date = datetime.date.today()
        context = super().get_context_data(**kwargs)
        context["daily"] = self.model.objects.filter(scanned_time__date = today_date)
        context['member'] = member.objects.filter(org=org)
        auser = request.user
        org =  auser.schooladmin.org
        context['org'] = org
        return context



def getMember(request):
    qid = request.GET.get('questionid', None)




def orgDetail(request):
    user = request.user
    org = user.schooladmin.org
    form = OrgFormSchool(instance=org)
    holiday = Holiday.objects.filter(org = org)
    print(holiday)
    existing_holidays = [holiday.holiday for holiday in holiday]
    occasion = Occasion.objects.filter(org =org)
    dist = {
        'form':form,
        'org':org,
        'holiday':existing_holidays,
        'occasions':occasion

    }
    if request.method == 'POST':
        org.name = request.POST.get('name', org.name)
        try:
            org.image = request.FILES['image'] or None
        except Exception:
            pass
        org.serial_key = request.POST.get('serial_key', org.serial_key)
        org.address = request.POST.get('address', org.address)
        org.nepali_date = request.POST.get('nepali_date') == 'on'
        org.save()
        messages.success(request, "Organization profile updated successfully.")
        return HttpResponseRedirect(reverse('schooladmin:orgDetail'))
   

    return render(request, "admin/orgDetail.html", dist)



class Dashboard(View):
    template_name = 'admin/Adashboard.html'

    def get(self, request, *args, **kwargs):
        user = request.user
        org = user.schooladmin.org
        if not org.activate:
            return render(request, 'admin/activate.html')

        today_date = datetime.date.today()
        member.date = today_date
        
        tm = member.objects.filter(org=org)
        total_member = tm.count()
        leave = LeaveReport.objects.filter(org=org).count()
        unseen_leave = LeaveReport.objects.filter(seen=False, org=org).count()
        
        absent = 0
        present = 0
        for i in tm:
            if i.first_daily_time() == None:
                absent += 1
            else:
                present += 1

        # 🔥 NEW: Critical Attendance Gap Logic (Last 7 Days)
        last_7_days = today_date - timedelta(days=7)
        
        # Members with at least one scan in last 7 days
        recent_active_ids = AttendanceRecord.objects.filter(
            org=org, scanned_time__gte=last_7_days
        ).values_list('mem_id', flat=True).distinct()

        # Members NOT seen in 7 days are "Critical Absentees"
        critical_absentees = tm.exclude(id__in=recent_active_ids).filter(status='active')[:5]

        today = datetime.date.today()
        month_start = today.replace(day=1)

        # ── Feature-sensitive dashboard queries ───────────────────────────────
        # Only run queries for enabled modules to avoid wasted DB load and to
        # ensure disabled modules return zero rather than stale data.

        total_income = total_expense = Decimal("0.00")
        if org.feature_finance:
            total_income  = FinancialTransaction.objects.filter(org=org, transaction_type='income',  transaction_date__gte=month_start).aggregate(t=Sum('amount'))['t'] or 0
            total_expense = FinancialTransaction.objects.filter(org=org, transaction_type='expense', transaction_date__gte=month_start).aggregate(t=Sum('amount'))['t'] or 0

        low_stock_count = 0
        if org.feature_stock:
            low_stock_count = StockItem.objects.filter(org=org, status='active', quantity__lte=F('low_stock_threshold')).count()

        pending_complaints = 0
        if org.feature_complaints:
            pending_complaints = Complaint.objects.filter(org=org, status='pending').count()

        upcoming_events = 0
        if org.feature_events:
            upcoming_events = Event.objects.filter(org=org, start_date__gte=today, status='upcoming').count()

        pending_resignations = 0
        if org.feature_hrms:
            pending_resignations = ResignationRecord.objects.filter(org=org, status='pending').count()

        # Task stats
        from handle.models import TaskInstance
        task_total = task_pending = task_overdue = task_today = task_pending_approval = 0
        if org.feature_tasks:
            task_inst_qs = TaskInstance.objects.filter(task__org=org)
            task_total            = task_inst_qs.count()
            task_pending          = task_inst_qs.filter(status='pending').count()
            task_overdue          = task_inst_qs.filter(status__in=['overdue', 'missed_absence']).count()
            task_today            = task_inst_qs.filter(due_date=today).exclude(status='cancelled').count()
            task_pending_approval = task_inst_qs.filter(approval_status='pending_approval').count()

        # Payroll stats
        from handle.models import AdvanceSalary
        advance_total_outstanding = advance_count = draft_payslips = 0
        month_payroll_total = Decimal("0.00")
        if org.feature_payroll:
            active_advances = AdvanceSalary.objects.filter(org=org, status='active')
            advance_total_outstanding = active_advances.aggregate(t=Sum('remaining_balance'))['t'] or 0
            advance_count = active_advances.count()
            draft_payslips = PaySlip.objects.filter(org=org, status='draft', from_date__gte=month_start).count()
            month_payroll_total = PaySlip.objects.filter(org=org, from_date__gte=month_start).aggregate(t=Sum('net_payable'))['t'] or 0

        # Billing / student stats
        student_qs = member.objects.filter(org=org, member_type='student')
        expected_monthly_billing = paid_this_month = Decimal("0.00")
        bills_generated_this_month = bills_not_sent = 0
        pending_due = Decimal("0.00")
        recent_payments = recent_sent_bills = class_income = []
        results_published = results_pending_publish = 0
        if org.feature_billing:
            active_student_qs = student_qs.filter(status='active')
            expected_monthly_billing = sum((_compute_final_fee(m) for m in active_student_qs), Decimal("0.00"))
            this_month_bills = Bill.objects.filter(org=org, billing_month=today.month, billing_year=today.year)
            paid_this_month = this_month_bills.aggregate(t=Sum('amount_paid'))['t'] or 0
            bills_generated_this_month = this_month_bills.count()
            bills_not_sent = this_month_bills.filter(is_sent=False).count()
            bill_totals = Bill.objects.filter(org=org).exclude(status='Cancelled').aggregate(total=Sum('total_amount'), paid=Sum('amount_paid'))
            pending_due = max(Decimal("0.00"), _money(bill_totals.get('total')) - _money(bill_totals.get('paid')))
            recent_payments = Bill.objects.filter(org=org, amount_paid__gt=0).select_related('member').order_by('-issue_date')[:5]
            recent_sent_bills = BillSendLog.objects.filter(bill__org=org).select_related('bill', 'bill__member')[:5]
            class_income = (Bill.objects.filter(org=org).values('classification__name').annotate(total=Sum('total_amount'), paid=Sum('amount_paid')).order_by('-total')[:6])

        if org.feature_results:
            results_published       = ExamTerm.objects.filter(org=org, is_published=True).count()
            results_pending_publish = ExamTerm.objects.filter(org=org, is_published=False).exclude(status='archived').count()

        # Leave
        pending_leave_requests = 0
        if org.feature_leave:
            pending_leave_requests = LeaveReport.objects.filter(org=org, approved=False, rejected=False).count()

        # Branches
        total_branches = 0
        if org.feature_branches:
            total_branches = Branch.objects.filter(org=org, status='active').count()

        dist = {
            'org': org,
            'tm': total_member,
            'absent': absent,
            'present': present,
            'leave': leave,
            'unseen_leave': unseen_leave,
            'pending_leave_requests': pending_leave_requests,
            'devices': Device.objects.filter(org=org),
            'critical_absentees': critical_absentees,
            'month_income': total_income,
            'month_expense': total_expense,
            'net_balance': total_income - total_expense,
            'low_stock_count': low_stock_count,
            'pending_complaints': pending_complaints,
            'upcoming_events': upcoming_events,
            'pending_resignations': pending_resignations,
            'total_branches': total_branches,
            'task_total': task_total,
            'task_pending': task_pending,
            'task_overdue': task_overdue,
            'task_today': task_today,
            'task_pending_approval': task_pending_approval,
            'advance_total_outstanding': advance_total_outstanding,
            'advance_count': advance_count,
            'draft_payslips': draft_payslips,
            'month_payroll_total': month_payroll_total,
            'total_students': student_qs.count() if org.feature_student_mgmt else 0,
            'expected_monthly_billing': expected_monthly_billing,
            'paid_this_month': paid_this_month,
            'pending_due': pending_due,
            'bills_generated_this_month': bills_generated_this_month,
            'bills_not_sent': bills_not_sent,
            'results_pending_publish': results_pending_publish,
            'results_published': results_published,
            'recent_payments': recent_payments,
            'recent_sent_bills': recent_sent_bills,
            'class_income': class_income,
        }
        return render(request, self.template_name, dist)


class ManualAttendance(View):
    template_name = 'admin/manual_attendance.html'

    def get(self, request, *args, **kwargs):
        org = request.user.schooladmin.org
        today_date = datetime.date.today()
        
        # Set the class variable so first_daily_time works for today
        member.date = today_date 
        members = member.objects.filter(org=org)
        
        dist = {
            'members': members,
            'today_display': today_date.strftime('%A, %d %B %Y'),
            'today_val': today_date.strftime('%Y-%m-%d'),
        }
        return render(request, self.template_name, dist)

    def post(self, request, *args, **kwargs):
        org = request.user.schooladmin.org
        member_id = request.POST.get('member_id')
        action = request.POST.get('action') 
        
        if not member_id:
            messages.error(request, "Error: No member selected.")
            return redirect('schooladmin:manual_attendance')
            
        mem = member.objects.get(id=member_id, org=org)
        today_date = datetime.date.today()

        # Get all records for today, ordered from earliest to latest
        # (Replace 'member_record' if your related name is different, e.g., 'attendancerecord_set')
        records_today = mem.member_record.filter(scanned_time__date=today_date).order_by('scanned_time')

        # ACTION 1: 1-Click Mark Present
        if action == 'mark_present':
            # Use timezone.now() to respect Asia/Kathmandu
            aware_now = timezone.now() 
            mem.member_record.create(scanned_time=aware_now, org=org)
            messages.success(request, f"Marked {mem.name} as Present!")

        # ACTION 2: Update Exact Times
        elif action == 'update_times':
            in_time = request.POST.get('in_time')
            out_time = request.POST.get('out_time')
            
            if in_time:
                # 1. Create native time, 2. Make it timezone aware for Nepal
                naive_in = datetime.datetime.strptime(f"{today_date} {in_time}", "%Y-%m-%d %H:%M")
                aware_in = timezone.make_aware(naive_in)
                
                if records_today.exists():
                    # UPDATE the first punch of the day
                    first_rec = records_today.first()
                    first_rec.scanned_time = aware_in
                    first_rec.save()
                else:
                    # CREATE if they have no punches yet
                    mem.member_record.create(scanned_time=aware_in, org=org)
            
            # Refresh the records list in case we just created the first one above
            records_today = mem.member_record.filter(scanned_time__date=today_date).order_by('scanned_time')
            
            if out_time:
                naive_out = datetime.datetime.strptime(f"{today_date} {out_time}", "%Y-%m-%d %H:%M")
                aware_out = timezone.make_aware(naive_out)
                
                if records_today.count() > 1:
                    # UPDATE the last punch of the day
                    last_rec = records_today.last()
                    last_rec.scanned_time = aware_out
                    last_rec.save()
                elif records_today.count() == 1:
                    # If they only had a Check-In, CREATE this as the Check-Out
                    mem.member_record.create(scanned_time=aware_out, org=org)
                else:
                    # Fallback
                    mem.member_record.create(scanned_time=aware_out, org=org)
                    
            messages.success(request, f"Successfully updated time logs for {mem.name}.")

        return redirect('schooladmin:manual_attendance')

class DailyReport(ListView):
    template_name = 'admin/dailyReport.html'

    def get(self, request, *args, **kwargs):
        user = request.user
        org = user.schooladmin.org
        tm = member.objects.filter(org=org)
        classifi = Classification.objects.filter(org=org)
        today_date = datetime.date.today()
        
        # 🔥 Check if Nepali date is enabled for this organization
        # Assuming the boolean field on Organization is called 'nepali_date_enabled'
        nepali_enabled = getattr(org, 'nepali_date', False)
        date_np = None

        if nepali_enabled:
            # Convert AD today to BS today and format as YYYY-MM-DD for the input field
            date_np = str(nepali_datetime.date.from_datetime_date(today_date))

        dist = {
            'date': today_date,     # Standard AD date
            'date_np': date_np,     # Formatted BS date (if enabled)
            'tm': tm,
            'org': org,
            'thisone': 'All',
            'clas': classifi,
            'nepali_enabled': nepali_enabled # Pass flag to template
        }
        return render(request, self.template_name, dist)

    def post(self, request, *args, **kwargs):
        today_date = datetime.date.today()
        user = request.user
        org = user.schooladmin.org
        name = request.POST.get('filter', 'All')
        
        # दुवै अंग्रेजी र नेपाली मिति फर्मबाट तान्ने
        date_ad_str = request.POST.get('date', '')
        date_np_str = request.POST.get('date_np', '')
        nepali_enabled = getattr(org, 'nepali_date', False)
        
        classifi = Classification.objects.filter(org=org)
        target_date_ad = today_date # Default to today
        
        # 🔥 १. नेपाली मिति कन्भर्सन (Robust Method)
        if nepali_enabled and date_np_str:
            try:
                # यदि JS Plugin ले '2080/12/05' पठाएको छ भने त्यसलाई '2080-12-05' बनाउने
                clean_np_str = date_np_str.replace('/', '-').strip()
                
                # वर्ष, महिना, दिन छुट्टाएर सिधै integer मा बदल्ने (यो तरिका कहिल्यै फेल हुँदैन)
                year, month, day = map(int, clean_np_str.split('-'))
                
                # BS लाई AD मा कन्भर्ट गर्ने
                np_date_obj = nepali_datetime.date(year, month, day)
                target_date_ad = np_date_obj.to_datetime_date()
                
              
                
            except Exception as e:
            
                if date_ad_str:
                    target_date_ad = datetime.datetime.strptime(date_ad_str, '%Y-%m-%d').date()
        
        # 🔥 २. यदि नेपाली मिति बन्द छ भने (अथवा अंग्रेजी मात्र चलाउँदा)
        elif date_ad_str:
            try:
                target_date_ad = datetime.datetime.strptime(date_ad_str, '%Y-%m-%d').date()
            except ValueError:
                target_date_ad = today_date

        # तपाइको मोडलको लजिक अनुसार मिति सेट गर्ने
        member.date = target_date_ad

        # फिल्टर गर्ने लजिक
        if name != 'All':
            tm = member.objects.filter(org=org, classification=name)
            try:
                sn = Classification.objects.get(id=name).name
            except Classification.DoesNotExist:
                sn = 'Unknown'
        else:
            tm = member.objects.filter(org=org)
            sn = 'All'

        dist = {
            'date': target_date_ad, 
            'date_np': date_np_str if nepali_enabled else None, 
            'tm': tm,
            'thisone': sn,
            'org': org,
            'clas': classifi,
            'nepali_enabled': nepali_enabled
        }
        return render(request, self.template_name, dist)

class PresentToday(ListView):
    template_name = 'admin/presentToday.html'

    def get(self, request, *args, **kwargs):
        user = request.user
        org = user.schooladmin.org
        today_date = datetime.date.today()
        
        # Set class variable so model properties format correctly
        member.date = today_date

        tm = member.objects.filter(org=org)
        today_attendance_data = AttendanceRecord.objects.filter(org=org, scanned_time__date=today_date)
        classifi = Classification.objects.filter(org=org)
        
        member_data = []
        for j in tm:
            for i in today_attendance_data:
                if i.mem == j:
                    member_data.append(j)
                    break
        
        nepali_enabled = getattr(org, 'nepali_date', False)
        
        dist = {
            'date': today_date,
            'date_np': '',  # Prevents template crash on initial load
            'tm': member_data,
            'org': org,
            'thisone': 'All',
            'clas': classifi,
            'nepali_enabled': nepali_enabled
        }
        return render(request, self.template_name, dist)

    def post(self, request, *args, **kwargs):
        today_date = datetime.date.today()
        user = request.user
        org = user.schooladmin.org
        
        # Safely extract POST data
        name = request.POST.get('filter', 'All')
        date = request.POST.get('date')
        date_np = request.POST.get('date_np', '')
        
        if not date:
            date = today_date
            
        # Set class variable for the requested date
        member.date = date

        classifi = Classification.objects.filter(org=org)
        today_attendance_data = AttendanceRecord.objects.filter(org=org, scanned_time__date=date)
        
        member_data = []
        nepali_enabled = getattr(org, 'nepali_date', False)

        # Filter by classification or show All
        if name != 'All':
            tm = member.objects.filter(org=org, classification=name)
            sn = Classification.objects.get(id=name).name
        else:
            tm = member.objects.filter(org=org)
            sn = 'All'

        for j in tm:
            for i in today_attendance_data:
                if i.mem == j:
                    member_data.append(j)
                    break

        dist = {
            'date': date,
            'date_np': date_np,  # Passes the Nepali date string back to the form
            'tm': member_data,
            'thisone': sn,
            'org': org,
            'clas': classifi,
            'nepali_enabled': nepali_enabled
        }
        return render(request, self.template_name, dist)


class AbsentToday(ListView):
    template_name = 'admin/absentToday.html'

    def get(self, request, *args, **kwargs):
        user = request.user
        org = user.schooladmin.org
        today_date = datetime.date.today()
        
        # Set class variable
        member.date = today_date

        tm = member.objects.filter(org=org)
        today_attendance_data = AttendanceRecord.objects.filter(org=org, scanned_time__date=today_date)
        classifi = Classification.objects.filter(org=org)
        
        member_data = []
        nepali_enabled = getattr(org, 'nepali_date', False)
        
        for j in tm:
            for i in today_attendance_data:
                if i.mem == j:
                    member_data.append(j)
                    break
                    
        # Calculate who is absent
        new = list(set(member_data).symmetric_difference(set(tm)))
        
        dist = {
            'date': today_date,
            'date_np': '',  # Prevents template crash on initial load
            'tm': new,
            'org': org,
            'thisone': 'All',
            'clas': classifi,
            'nepali_enabled': nepali_enabled
        }
        return render(request, self.template_name, dist)

    def post(self, request, *args, **kwargs):
        today_date = datetime.date.today()
        user = request.user
        org = user.schooladmin.org
        
        # Safely extract POST data
        name = request.POST.get('filter', 'All')
        date = request.POST.get('date')
        date_np = request.POST.get('date_np', '')
        
        if not date:
            date = today_date
            
        # Set class variable for the requested date
        member.date = date
            
        classifi = Classification.objects.filter(org=org)
        today_attendance_data = AttendanceRecord.objects.filter(org=org, scanned_time__date=date)
        
        member_data = []
        nepali_enabled = getattr(org, 'nepali_date', False)

        # Filter by classification or show All
        if name != 'All':
            tm = member.objects.filter(org=org, classification=name)
            sn = Classification.objects.get(id=name).name
        else:
            tm = member.objects.filter(org=org)
            sn = 'All'

        for j in tm:
            for i in today_attendance_data:
                if i.mem == j:
                    member_data.append(j)
                    break
                    
        # Calculate who is absent
        new = list(set(member_data).symmetric_difference(set(tm)))

        dist = {
            'date': date,
            'date_np': date_np,  # Passes the Nepali date string back to the form
            'tm': new,
            'thisone': sn,
            'org': org,
            'clas': classifi,
            'nepali_enabled': nepali_enabled
        }
        return render(request, self.template_name, dist)






def parse_time(time_string):
    try:
        # Try parsing with microseconds
        return dt.strptime(time_string, '%H:%M:%S.%f')
    except ValueError:
        # Fallback to parsing without microseconds
        return dt.strptime(time_string.split('.')[0], '%H:%M:%S')
    


class GapReport(View):
    template_name = "admin/gapReport.html"
    
    def get(self, request, *args, **kwargs):
        user = request.user
        org = user.schooladmin.org
        tm = None
        today_date = datetime.date.today()
        clas = Classification.objects.filter(org=org)
        
        # 🔥 नयाँ मोडल फिल्ड org.nepali_date तान्ने
        nepali_enabled = org.nepali_date 
        
        today_np = str(nepali_datetime.date.from_datetime_date(today_date)) if nepali_enabled else ""

        dist = {
            'first_date': today_date,
            'last_date': today_date,
            'first_date_np': today_np,
            'last_date_np': today_np,
            'tm': tm,
            'org': org,
            'thisone': 'All',
            'clas': clas,
            'nepali_enabled': nepali_enabled
        }
        return render(request, self.template_name, dist)
    
    def post(self, request, *args, **kwargs):
        user = request.user
        org = user.schooladmin.org
        clas = Classification.objects.filter(org=org)
        name = request.POST.get('classification', 'All')
        
        # 🔥 नयाँ मोडल फिल्ड
        nepali_enabled = org.nepali_date

        first_date_str = request.POST.get('first_date', '')
        last_date_str = request.POST.get('last_date', '')
        first_date_np_str = request.POST.get('first_date_np', '')
        last_date_np_str = request.POST.get('last_date_np', '')

        # 1. First Date कन्भर्सन
        if nepali_enabled and first_date_np_str:
            try:
                y, m, d = map(int, first_date_np_str.replace('/', '-').strip().split('-'))
                start_date = nepali_datetime.date(y, m, d).to_datetime_date()
            except Exception:
                start_date = datetime.datetime.strptime(first_date_str, "%Y-%m-%d").date()
        else:
            start_date = datetime.datetime.strptime(first_date_str, "%Y-%m-%d").date()

        # 2. Last Date कन्भर्सन
        if nepali_enabled and last_date_np_str:
            try:
                y, m, d = map(int, last_date_np_str.replace('/', '-').strip().split('-'))
                end_date = nepali_datetime.date(y, m, d).to_datetime_date()
            except Exception:
                end_date = datetime.datetime.strptime(last_date_str, "%Y-%m-%d").date()
        else:
            end_date = datetime.datetime.strptime(last_date_str, "%Y-%m-%d").date()

        delta = datetime.timedelta(days=1)
        later_date = start_date

        if name == 'All':
            mem = member.objects.filter(org=org)
            th = 'All' 
        else:
            mem = member.objects.filter(org=org).filter(classification=name)
            th = Classification.objects.get(id=name).name
            
        member_data = []
        holiday = Holiday.objects.filter(org=org)
        occasion = Occasion.objects.filter(org=org)
        
        for i in mem:
            current_loop_date = later_date 
            while current_loop_date <= end_date:
                i.date = current_loop_date
                aa = i.first_daily_time()
                try:
                    bb = i.last_daily_time()
                except:
                    bb = None
                    
                time_interval = None
                
                if aa is not None:
                    time_1 = i.parse_time(str(aa)) # member model function
                if bb:
                    time_2 = i.parse_time(str(bb))
                    time_interval = time_2 - time_1
                    
                holi = False
                oca = None
              
                for p in holiday:
                    if p.holiday == current_loop_date.strftime("%A"):
                        holi = True
                        break
                
                for n in occasion:
                    if not n.end_date:
                        if n.date == current_loop_date:
                            oca = n.name
                    else:
                        temp_date = n.date
                        while temp_date <= n.end_date:
                            if temp_date == current_loop_date:
                                oca = n.name
                                break
                            temp_date += datetime.timedelta(days=1)

                # 🔥 हरेक दिनको मितिलाई नेपालीमा बदल्ने
                loop_date_np = ""
                if nepali_enabled:
                    loop_date_np = str(nepali_datetime.date.from_datetime_date(current_loop_date))

                # 🔥 i.7 मा नेपाली मिति पठाउने (loop_date_np)
                member_data.append([current_loop_date, i.name, aa, bb, time_interval, holi, oca, loop_date_np])
                
                i.first_date = None
                i.last_date = None
                i.ft = None
                i.tt = None
                i.date = None
              
                current_loop_date += delta
      
        dist = {
            'first_date': start_date,
            'last_date': end_date,
            'first_date_np': first_date_np_str if nepali_enabled else None,
            'last_date_np': last_date_np_str if nepali_enabled else None,
            'tm': member_data,
            'thisone': th,
            'org': org,
            'clas': clas,
            'nepali_enabled': nepali_enabled
        }
        return render(request, self.template_name, dist)
class MemberGapReport(View):
    template_name = "admin/memberRecord.html"
    
    def get(self, request, *args, **kwargs):
        id = self.kwargs['id']
        user = request.user
        org = user.schooladmin.org
        memb = get_object_or_404(member, id=id, org=org)
        today_date = datetime.date.today()
        memb.date = today_date
        member_data = []

        nepali_enabled = getattr(org, 'nepali_date', False)
        today_np = str(nepali_datetime.date.from_datetime_date(today_date)) if nepali_enabled else ""

        time_interval = None
        aa = memb.first_daily_time()
        try:
            bb = memb.last_daily_time()
        except:
            bb = None
     
        if aa is not None:
            time_1 = memb.parse_time(str(aa))
        if bb:
            time_2 = memb.parse_time(str(bb))
            time_interval = time_2 - time_1
      
        # 🔥 NEW: Calculate today's late in / early out for the GET request
        late_in = memb.late_in()
        early_out = memb.early_out()

        # Added late_in as index 9 and early_out as index 10
        member_data.append([today_date, memb.name, aa, bb, time_interval, False, None, None, today_np, late_in, early_out])

        dist = {
            'date': today_date,
            'tm': member_data,
            'org': org,
            'thisone': memb.name,
            'nepali_enabled': nepali_enabled,
            'first_date_np': today_np,
            'last_date_np': today_np,
            'total_late_in': late_in if late_in else "00:00",
            'total_early_out': early_out if early_out else "00:00",
        }
        return render(request, self.template_name, dist)
    
    def post(self, request, *args, **kwargs):
        id = self.kwargs['id']
        user = request.user
        org = user.schooladmin.org
        mem = get_object_or_404(member, id=id, org=org)
        nepali_enabled = getattr(org, 'nepali_date', False)

        first_date_str = request.POST.get('first_date', '')
        last_date_str = request.POST.get('last_date', '')
        first_date_np_str = request.POST.get('first_date_np', '')
        last_date_np_str = request.POST.get('last_date_np', '')

        # 1. First Date Conversion
        if nepali_enabled and first_date_np_str:
            try:
                y, m, d = map(int, first_date_np_str.replace('/', '-').strip().split('-'))
                start_date = nepali_datetime.date(y, m, d).to_datetime_date()
            except Exception:
                start_date = datetime.datetime.strptime(first_date_str, "%Y-%m-%d").date()
        else:
            start_date = datetime.datetime.strptime(first_date_str, "%Y-%m-%d").date()

        # 2. Last Date Conversion
        if nepali_enabled and last_date_np_str:
            try:
                y, m, d = map(int, last_date_np_str.replace('/', '-').strip().split('-'))
                end_date = nepali_datetime.date(y, m, d).to_datetime_date()
            except Exception:
                end_date = datetime.datetime.strptime(last_date_str, "%Y-%m-%d").date()
        else:
            end_date = datetime.datetime.strptime(last_date_str, "%Y-%m-%d").date()

        delta = datetime.timedelta(days=1)
        member_data = []
        holiday = Holiday.objects.filter(org=org)
        occasion = Occasion.objects.filter(org=org)
        
        total_days, total_absent_days, total_present_days = 0, 0, 0
        total_holidays, total_occasion_holidays, total_leave_days = 0, 0, 0
        
        # 🔥 NEW: Variables to sum up the total late and early hours
        total_late_seconds = 0
        total_early_out_seconds = 0
        
        total_leave = LeaveReport.objects.filter(member=mem).filter(approved=True)
        leave_date = []

        for leave_report in total_leave:
            total_leave_days += leave_report.total_leave_days()
                
        for i in total_leave:
            if not i.gap_end:
                leave_date.append(i.gap_start)
            else:
                current_date = i.gap_start
                while current_date <= i.gap_end:
                    leave_date.append(current_date)
                    current_date += datetime.timedelta(days=1)

        # To avoid altering the loop variable
        loop_date = start_date

        while loop_date <= end_date:
            total_days += 1
            i = mem
            i.date = loop_date
            aa = i.first_daily_time()
            bb = i.last_daily_time()
            time_interval = None
            if aa:
                time_1 = i.parse_time(str(aa))
            if bb:
                time_2 = i.parse_time(str(bb))
                time_interval = time_2 - time_1

            # 🔥 NEW: Calculate Late In and Early Out for this specific day
            late_in_time = i.late_in()
            early_out_time = i.early_out()

            # Add to total seconds for the summary cards
            if late_in_time:
                h, m = map(int, late_in_time.split(':'))
                total_late_seconds += (h * 3600 + m * 60)
            
            if early_out_time:
                h, m = map(int, early_out_time.split(':'))
                total_early_out_seconds += (h * 3600 + m * 60)

            holi = False
            for p in holiday:
                if p.holiday == loop_date.strftime("%A"):
                    total_holidays += 1
                    holi = True
                    break
            
            oca = None
            for n in occasion:
                if not n.end_date:
                    if n.date == loop_date:
                        oca = n.name
                        total_occasion_holidays += 1
                        break
                else:
                    current_date = n.date
                    while current_date <= n.end_date:
                        if current_date == loop_date:
                            oca = n.name
                            total_occasion_holidays += 1
                            break
                        current_date += datetime.timedelta(days=1)

            if aa:
                total_present_days += 1
            else:
                if not holi and not oca:
                    total_absent_days += 1

            leave_status = 'On Leave' if loop_date in leave_date else None

            # Nepali date logic
            loop_date_np = ""
            if nepali_enabled:
                loop_date_np = str(nepali_datetime.date.from_datetime_date(loop_date))

            # 🔥 NEW: Appended late_in_time as i.9 and early_out_time as i.10
            member_data.append([loop_date, i.name, aa, bb, time_interval, holi, oca, leave_status, loop_date_np, late_in_time, early_out_time])
            
            i.first_date = None
            i.last_date = None
            i.ft = None
            i.tt = None
            i.date = None
              
            loop_date += delta

        # Convert total accumulated seconds back to HH:MM string format
        total_late_str = f"{total_late_seconds // 3600:02d}:{(total_late_seconds % 3600) // 60:02d}"
        total_early_out_str = f"{total_early_out_seconds // 3600:02d}:{(total_early_out_seconds % 3600) // 60:02d}"

        dist = {
            'first_date': start_date,
            'last_date': end_date,
            'first_date_np': first_date_np_str if nepali_enabled else None,
            'last_date_np': last_date_np_str if nepali_enabled else None,
            'tm': member_data,
            'org': org,
            'thisone': mem.name,
            'total_days': total_days,
            'total_absent_days': total_absent_days,
            'total_present_days': total_present_days,
            'total_holidays': total_holidays,
            'total_occasion_holidays': total_occasion_holidays,
            'total_leave_days': total_leave_days,
            'total_late_in': total_late_str,        # 🔥 Passed to template
            'total_early_out': total_early_out_str, # 🔥 Passed to template
            'nepali_enabled': nepali_enabled
        }
        return render(request, self.template_name, dist)
    

class salaryReport(View):
    template_name = "admin/salaryReport.html"
    
    def get(self, request, *args, **kwargs):
        id = self.kwargs['id']
        user = request.user
        org = user.schooladmin.org
        memb = get_object_or_404(member, id=id, org=org)

        nepali_enabled = getattr(org, 'nepali_date', False)
        today_date = datetime.date.today()
        today_np = str(nepali_datetime.date.from_datetime_date(today_date)) if nepali_enabled else ""
        
        memb.date = today_date
        aa = memb.first_daily_time()
        try:
            bb = memb.last_daily_time()
        except:
            bb = None
            
        time_interval = None
        time_interval_cost = 0
        total_hour = 0
        total_cost = 0
        
        if aa and bb:
            time_1 = memb.parse_time(str(aa))
            time_2 = memb.parse_time(str(bb))
            time_interval = time_2 - time_1
            tim = (time_interval.total_seconds() / 60) / 60
            times = float("{:.2f}".format(tim))
            time_interval_cost = times * memb.salary_per_hour
            total_cost += time_interval_cost

        # लिस्टको 6th Index मा नेपाली मिति पठाउँदै
        member_data = [[today_date, memb.name, aa, bb, time_interval, time_interval_cost, today_np]]
        
        dist = {
            'first_date': today_date.strftime("%Y-%m-%d"),
            'last_date': today_date.strftime("%Y-%m-%d"),
            'first_date_np': today_np,
            'last_date_np': today_np,
            'tm': member_data,
            'org': org,
            'thisone': memb.name,
            'mem_id': memb.id, # Payslip बटनको लागि
            'total_hour': total_hour,
            'total_cost': round(total_cost, 2),
            'allMember': member.objects.filter(org=org),
            'nepali_enabled': nepali_enabled
        }
        return render(request, self.template_name, dist)

    def post(self, request, *args, **kwargs):
        id = self.kwargs['id']
        user = request.user
        org = user.schooladmin.org
        
        # यदि ड्रपडाउनबाट अर्को मेम्बर छानेको छ भने
        selected_member_id = request.POST.get('member', id)
        mem = member.objects.get(id=selected_member_id)
        
        nepali_enabled = getattr(org, 'nepali_date', False)

        first_date_str = request.POST.get('first_date', '')
        last_date_str = request.POST.get('last_date', '')
        first_date_np_str = request.POST.get('first_date_np', '')
        last_date_np_str = request.POST.get('last_date_np', '')

        # 1. First Date कन्भर्सन
        if nepali_enabled and first_date_np_str:
            try:
                y, m, d = map(int, first_date_np_str.replace('/', '-').strip().split('-'))
                start_date = nepali_datetime.date(y, m, d).to_datetime_date()
            except Exception:
                start_date = datetime.datetime.strptime(first_date_str, "%Y-%m-%d").date()
        else:
            start_date = datetime.datetime.strptime(first_date_str, "%Y-%m-%d").date()

        # 2. Last Date कन्भर्सन
        if nepali_enabled and last_date_np_str:
            try:
                y, m, d = map(int, last_date_np_str.replace('/', '-').strip().split('-'))
                end_date = nepali_datetime.date(y, m, d).to_datetime_date()
            except Exception:
                end_date = datetime.datetime.strptime(last_date_str, "%Y-%m-%d").date()
        else:
            end_date = datetime.datetime.strptime(last_date_str, "%Y-%m-%d").date()

        delta = datetime.timedelta(days=1)
        member_data = []
        total_hour_in_sec = 0.0
        total_cost = 0
        
        loop_date = start_date
        while loop_date <= end_date:
            time_interval = None
            time_interval_cost = 0
            
            mem.date = loop_date
            aa = mem.first_daily_time()
            try:
                bb = mem.last_daily_time()
            except:
                bb = None
           
            if aa and bb:
                time_1 = mem.parse_time(str(aa))
                time_2 = mem.parse_time(str(bb))
                time_interval = time_2 - time_1
                
                tim = (time_interval.total_seconds() / 60) / 60
                total_hour_in_sec += tim
                time_interval_cost = tim * mem.salary_per_hour
                total_cost += round(time_interval_cost)

            # हरेक दिनको नेपाली मिति
            loop_date_np = str(nepali_datetime.date.from_datetime_date(loop_date)) if nepali_enabled else ""
            
            member_data.append([loop_date, mem.name, aa, bb, time_interval, round(time_interval_cost), loop_date_np])
            
            mem.first_date = None
            mem.last_date = None
            mem.ft = None
            mem.tt = None
            mem.date = None
            loop_date += delta
            
        dist = {
            'first_date': start_date.strftime("%Y-%m-%d"),
            'last_date': end_date.strftime("%Y-%m-%d"),
            'first_date_np': first_date_np_str if nepali_enabled else None,
            'last_date_np': last_date_np_str if nepali_enabled else None,
            'tm': member_data,
            'org': org,
            'allMember': member.objects.filter(org=org),
            'thisone': mem.name,
            'mem_id': mem.id, # Payslip बटनको लागि
            'total_hour': int(total_hour_in_sec),
            'total_cost': total_cost,
            'nepali_enabled': nepali_enabled
        }
        return render(request, self.template_name, dist)

class salaryReportAll(View):
    template_name = 'admin/salaryReportAll.html'

    def get(self, request, *args, **kwargs):
        auser = request.user
        if auser.user_type == "2":
            org =  auser.schooladmin.org
        elif auser.user_type == "3":
            org =  auser.staff.org
        else:
            org = None
  
        memb = member.objects.filter(org=org).order_by('-id')

        dist = {
            'mem':memb,
            'org':org,
            'clas':Classification.objects.filter(org=org),
            'thisone':'All'
        }
        return render(request, self.template_name, dist)

    def post(self, request, *agrs, **kwargs):
        clas = request.POST['classification']
        print('class', clas)
        auser = request.user
        if auser.user_type == "2":
            org =  auser.schooladmin.org
        elif auser.user_type == "3":
            org =  auser.staff.org
      
        cl=Classification.objects.filter(org=org)
        if clas == 'All':
            mem = member.objects.filter(org = org)
            th = 'All' 
        else:
            mem = member.objects.filter(org = org).filter(classification=clas)
            th = Classification.objects.get(id = clas).name
        dist = {
            'mem':mem,
            'clas':cl,
            'org':org,
            'thisone': th
        }
        return render(request, self.template_name, dist)



class leaveReportView(View):
    template_name = "admin/leaveReportView.html"

    def get(self, request, *args, **kwargs):
        from django.core.paginator import Paginator
        user = request.user
        org = user.schooladmin.org
        nepali_enabled = getattr(org, 'nepali_date', False)
        today_date = datetime.date.today()

        # Filters
        status_filter = request.GET.get('status', 'all')
        leave_reports = LeaveReport.objects.filter(org=org).select_related(
            'member', 'leave_type'
        ).order_by('-gap_start')

        if status_filter == 'pending':
            leave_reports = leave_reports.filter(approved=False, rejected=False, seen=False)
        elif status_filter == 'approved':
            leave_reports = leave_reports.filter(approved=True)
        elif status_filter == 'rejected':
            leave_reports = leave_reports.filter(rejected=True)

        for leave in leave_reports:
            if nepali_enabled:
                leave.start_display = str(nepali_datetime.date.from_datetime_date(leave.gap_start)) if leave.gap_start else ""
                leave.end_display   = str(nepali_datetime.date.from_datetime_date(leave.gap_end))   if leave.gap_end   else ""
            else:
                leave.start_display = leave.gap_start.strftime("%Y-%m-%d") if leave.gap_start else ""
                leave.end_display   = leave.gap_end.strftime("%Y-%m-%d")   if leave.gap_end   else ""
            leave.is_paid_leave = getattr(leave.leave_type, 'is_paid', True) if leave.leave_type else True

        paginator = Paginator(leave_reports, 30)
        page_obj  = paginator.get_page(request.GET.get('page'))

        today_np = str(nepali_datetime.date.from_datetime_date(today_date)) if nepali_enabled else today_date.strftime("%Y-%m-%d")
        dist = {
            'org': org,
            'leave': page_obj,
            'page_obj': page_obj,
            'status_filter': status_filter,
            'nepali_enabled': nepali_enabled,
            'date': today_np if nepali_enabled else today_date.strftime("%Y-%m-%d"),
            'total_pending': LeaveReport.objects.filter(org=org, approved=False, rejected=False).count(),
        }
        return render(request, self.template_name, dist)
    


def leaveStatus(request, id, status):
    leve = LeaveReport.objects.get(id=id)
    
    # 1. Format the Date String cleanly
    if not leve.gap_end:
        date_str = str(leve.gap_start)
    else:
        date_str = f"{leve.gap_start} to {leve.gap_end}"

    # 2. Setup Context for the HTML Email
    # Note: Email clients require full URLs for images (https://...)
    domain = 'https://meroattendance.com' # Change this if your domain is different
    
    context = {
        'org_name': leve.org.name,
        'member_name': leve.member.name,
        'date_str': date_str,
        'domain': domain,
    }

    # Safely attach the absolute logo URL if the organization has one
    if leve.org.image:
        context['org_logo'] = f"{domain}{leve.org.image.url}"
    else:
        context['org_logo'] = None

    # 3. Handle Status Logic
    if status == "accept":
        leve.approved = True
        leve.seen = True
        leve.save()
        
        subject = f'Leave Approved - {leve.org.name}'
        context['status'] = 'Approved'
        context['status_color'] = '#16a34a' # Success Green
        context['message'] = 'Great news! Your leave request has been approved by the administration.'
        
        success_msg = "Successfully approved the leave. Member has received the mail."
        error_msg = "Leave approved, but failed to send email. Please check member email."

    elif status == "reject":
        leve.rejected = True
        leve.seen = True
        leve.save()
        
        subject = f'Leave Rejected - {leve.org.name}'
        context['status'] = 'Rejected'
        context['status_color'] = '#e11d48' # Danger Red
        context['message'] = 'Your leave request has been declined. Please contact administration for further details.'
        
        success_msg = "Successfully rejected the leave. Member has received the mail."
        error_msg = "Leave rejected, but failed to send email. Please check member email."

    # 4. Generate the Emails
    html_email = render_to_string("basic/leave_status_email.html", context)
    text_fallback = f"{leve.org.name}: Your leave for {date_str} has been {context['status']}."
    
    # 5. Send Email securely
    try:
        send_mail(
            subject=subject,
            message=text_fallback,
            from_email=settings.EMAIL_HOST_USER,
            recipient_list=[leve.member.email],
            fail_silently=False,
            html_message=html_email
        )
        messages.success(request, success_msg)
    except Exception as e:
        print(f"Mail Error: {e}") # Prints error to terminal for debugging
        messages.error(request, error_msg) 
        
    return HttpResponseRedirect(reverse('schooladmin:dashboard'))

   
def playSlipView(request):
    auser = request.user
    if auser.user_type == "2":
        org =  auser.schooladmin.org
    elif auser.user_type == "3":
        org =  auser.staff.org
    else:
        org = None

    memb = member.objects.filter(org=org).order_by('-id')

    dist = {
        'mem':memb,
        'org':org,
        'clas':Classification.objects.filter(org=org),
        'thisone':'All'
    }
    return render(request, "admin/payslip.html", dist)


# Helper to convert "HH:MM" string to decimal hours for precise penalty math
from schooladmin.payroll_service import (
    calculate_attendance_stats,
    calculate_payroll_components,
    get_or_create_policy,
    time_to_decimal,
    decimal_money,
)

def sum_adjustments(queryset, adjustment_type):
    total = queryset.filter(adjustment_type=adjustment_type).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    return decimal_money(total)

def paySlipDetailView(request, id):
    auser = request.user
    org = auser.schooladmin.org if auser.user_type == "2" else auser.staff.org
        
    memb = get_object_or_404(member, id=id, org=org)
    nepali_enabled = getattr(org, 'nepali_date', False)
    payroll_policy, _ = PayrollPolicy.objects.get_or_create(org=org)

    dist = {
        'mem': memb,
        'org': org,
        'clas': Classification.objects.filter(org=org),
        'paySlip': PaySlip.objects.filter(member__id=id).order_by('-id'),
        'nepali_enabled': nepali_enabled,
        'payroll_policy': payroll_policy,
        'is_generated': False
    }
    
    if request.method == 'POST':
        first_date_str = request.POST.get('first_date', '')
        last_date_str = request.POST.get('last_date', '')
        first_date_np_str = request.POST.get('first_date_np', '')
        last_date_np_str = request.POST.get('last_date_np', '')

        # Date Parsing
        if nepali_enabled and first_date_np_str:
            try:
                y, m, d = map(int, first_date_np_str.replace('/', '-').strip().split('-'))
                start_date = nepali_datetime.date(y, m, d).to_datetime_date()
            except:
                start_date = datetime.datetime.strptime(first_date_str, "%Y-%m-%d").date()
        else:
            start_date = datetime.datetime.strptime(first_date_str, "%Y-%m-%d").date()

        if nepali_enabled and last_date_np_str:
            try:
                y, m, d = map(int, last_date_np_str.replace('/', '-').strip().split('-'))
                end_date = nepali_datetime.date(y, m, d).to_datetime_date()
            except:
                end_date = datetime.datetime.strptime(last_date_str, "%Y-%m-%d").date()
        else:
            end_date = datetime.datetime.strptime(last_date_str, "%Y-%m-%d").date()

        # ── Attendance stats via payroll service ──────────────────────────
        stats, daily_logs = calculate_attendance_stats(
            memb, start_date, end_date, org, nepali_enabled=nepali_enabled
        )

        # ── Payroll components via payroll service ────────────────────────
        comps = calculate_payroll_components(memb, stats, org, payroll_policy, end_date)

        month_name = f"{start_date.strftime('%B')} - {end_date.strftime('%B %Y')}"

        dist.update({
            'start_date': start_date.strftime("%Y-%m-%d"),
            'end_date': end_date.strftime("%Y-%m-%d"),
            'first_date_np': first_date_np_str,
            'last_date_np': last_date_np_str,
            'month_name': month_name,
            'daily_logs': daily_logs,
            'stats': stats,
            **comps,
            'active_adjustments': comps['active_adjustments'],
            'is_generated': True,
        })
       
    return render(request, "admin/generate_payslip.html", dist)

def generate(request, id):
    if request.method == 'POST':
        # 1. Identify the Organization of the logged-in user
        auser = request.user
        if auser.user_type == "2":
            org = auser.schooladmin.org
        elif auser.user_type == "3":
            org = auser.staff.org
        else:
            org = None

        form = PaySlipForm(request.POST)
        
        if form.is_valid():
            # 2. Use commit=False to pause the save process
            payslip = form.save(commit=False)
            
            # 3. Inject the missing Organization data securely
            payslip.org = org
            
            # 4. Now save it permanently to the database
            payslip.save()

            if payslip.pf_employee or payslip.pf_employer:
                ProvidentFundRecord.objects.create(
                    org=org,
                    member=payslip.member,
                    payslip=payslip,
                    month_name=payslip.month_name or '',
                    employee_contribution=payslip.pf_employee,
                    employer_contribution=payslip.pf_employer,
                )

            if payslip.ssf_employee or payslip.ssf_employer:
                SocialSecurityFundRecord.objects.create(
                    org=org,
                    member=payslip.member,
                    payslip=payslip,
                    month_name=payslip.month_name or '',
                    employee_contribution=payslip.ssf_employee,
                    employer_contribution=payslip.ssf_employer,
                )

            # Auto-log net salary as Finance expense
            if org and payslip.net_payable:
                sal_cat, _ = TransactionCategory.objects.get_or_create(
                    org=org, name='Salary Payment', transaction_type='expense'
                )
                FinancialTransaction.objects.create(
                    org=org,
                    transaction_type='expense',
                    title=f"Salary — {payslip.member.name} ({payslip.month_name or 'Payslip'})",
                    amount=payslip.net_payable,
                    category=sal_cat,
                    reference_number=str(payslip.id),
                    note=f"Auto-linked from payslip #{payslip.id}",
                    created_by=request.user,
                )

            # Mark advance/loan adjustments that fed this payslip as 'applied'
            if org and (payslip.advance_deduction or payslip.loan_deduction):
                PayrollAdjustment.objects.filter(
                    org=org,
                    member=payslip.member,
                    status='active',
                    adjustment_type__in=['advance', 'loan'],
                    effective_date__lte=payslip.to_date,
                ).update(status='applied')

            messages.success(request, "Successfully saved and generated Payslip!")
            return HttpResponseRedirect(reverse('schooladmin:play-slip-detail', args=(id,)))
        else:
            print(form.errors) # This will print exact form errors in your terminal if it fails
            messages.error(request, "Failed to save salary data. Please check the calculation.")
            return HttpResponseRedirect(reverse('schooladmin:play-slip-detail', args=(id,)))
            
    return HttpResponseRedirect(reverse('schooladmin:play-slip-detail', args=(id,)))


def finalize_payslip(request, pk):
    """Toggle a payslip between draft → finalized → paid, or reset."""
    org = _get_org(request)
    slip = get_object_or_404(PaySlip, pk=pk, org=org)
    if request.method == 'POST':
        new_status = request.POST.get('status', 'finalized')
        slip.status = new_status
        slip.finalized_by = request.user
        slip.save(update_fields=['status', 'finalized_by', 'updated_at'])

        # When finalising, apply AdvanceSalary installments
        if new_status == 'finalized' and slip.advance_deduction:
            from handle.models import AdvanceSalary as _AdvSal
            for adv in _AdvSal.objects.filter(org=org, member=slip.member, status='active'):
                adv.apply_installment()

        messages.success(request, f"Payslip marked as {new_status}.")
        return redirect('schooladmin:play-slip-detail', id=slip.member.id)
    return redirect('schooladmin:play-slip-detail', id=slip.member.id)


def addHoliday(request):
    org =  request.user.schooladmin.org
    if request.method == 'POST':
        days = request.POST.getlist('day')
        for i in days:
            Holiday.objects.create(holiday = i, org = org)
        print(days)
        messages.success(request,"Successfully added holiday")
    return HttpResponseRedirect(reverse('schooladmin:orgDetail'))


def updateHoliday(request):
    org = request.user.schooladmin.org
    if request.method == 'POST':
        current_holidays = Holiday.objects.filter(org=org)
        selected_days = request.POST.getlist('day')

        # Convert the selected days and current holidays to sets for easier comparison
        selected_days_set = set(selected_days)
        current_holidays_set = set(holiday.holiday for holiday in current_holidays)

        # Holidays to add
        holidays_to_add = selected_days_set - current_holidays_set
        for day in holidays_to_add:
            # Check if the holiday already exists to avoid duplicates
            if not Holiday.objects.filter(holiday=day, org=org).exists():
                Holiday.objects.create(holiday=day, org=org)
                print(f"Adding holiday: {day}")

        # Holidays to remove
        holidays_to_remove = current_holidays_set - selected_days_set
        for day in holidays_to_remove:
            holiday_to_delete = Holiday.objects.filter(holiday=day, org=org).first()
            if holiday_to_delete:
                holiday_to_delete.delete()
                print(f"Deleting holiday: {day}")

        messages.success(request, "Successfully updated holidays")
        return HttpResponseRedirect(reverse('schooladmin:orgDetail'))


def addOccasion(request):
    org = request.user.schooladmin.org

    if request.method == 'POST':
        name = request.POST['occasion']
        start_date = request.POST['ocDate']
        holiday_type = request.POST['holidayType']
        end_date = request.POST.get('ocEndDate', None)

        if holiday_type == 'gap' and end_date:
            Occasion.objects.create(org=org, date=start_date, end_date=end_date, name=name)
        else:
            Occasion.objects.create(org=org, date=start_date, name=name)

        messages.success(request, "Successfully added occasion")
        return HttpResponseRedirect(reverse('schooladmin:orgDetail'))


def staffMake(request):
    auser = request.user
    if auser.user_type == "2":
        org = auser.schooladmin.org
    elif auser.user_type == "3":
        org = auser.staff.org
    else:
        org = None
    memb = member.objects.filter(org=org)

    dist = {
        'member': memb,
        'classifications': Classification.objects.filter(org=org),
        'courses': Course.objects.filter(org=org, status='active').prefetch_related('classifications'),
        'org': org,
    }
    if request.method == 'POST':
        classification_ids = request.POST.getlist('classifications')
        course_ids = request.POST.getlist('courses')
        memId = request.POST['member']
        memb_obj = member.objects.get(id=memId)
        classifications = Classification.objects.filter(id__in=classification_ids)

        if not CustomUser.objects.filter(email=memb_obj.email).exists():
            TypeOne = CustomUser.objects.create_user(
                first_name=memb_obj.name,
                last_name=memb_obj.name,
                email=memb_obj.email,
                username=memb_obj.email,
                password=str(memb_obj.phone)
            )
            TypeOne.user_type = "3"
            TypeOne.save()
            Staff.objects.create(member=memb_obj, admin=TypeOne, org=org, number=memb_obj.phone)
            for classification in classifications:
                AttendingClassification.objects.create(staff=TypeOne, classification=classification)
            # Assign teacher to selected courses
            if course_ids:
                Course.objects.filter(id__in=course_ids, org=org).update(teacher=TypeOne)
        else:
            existing_user = CustomUser.objects.get(email=memb_obj.email)
            for classification in classifications:
                AttendingClassification.objects.get_or_create(staff=existing_user, classification=classification)
            if course_ids:
                Course.objects.filter(id__in=course_ids, org=org).update(teacher=existing_user)

        messages.success(request, f"Portal access granted for {memb_obj.name}.")

    return render(request, "admin/addStaff.html", dist)
    


def updateClass(request, id):
    mem = member.objects.get(id=id)
    staf = Staff.objects.get(admin__email=mem.email)
    org = mem.org
    current_classifications = AttendingClassification.objects.filter(staff=staf.admin)

    if request.method == 'POST':
        selected_classifications = request.POST.getlist('classifications')
        selected_courses = request.POST.getlist('courses')

        current_classifications = AttendingClassification.objects.filter(staff=staf.admin)
        current_classification_ids = [str(c.classification.id) for c in current_classifications]

        to_add = set(selected_classifications) - set(current_classification_ids)
        to_remove = set(current_classification_ids) - set(selected_classifications)

        for classification_id in to_add:
            classification = Classification.objects.get(id=classification_id)
            AttendingClassification.objects.create(staff=staf.admin, classification=classification)

        for classification_id in to_remove:
            AttendingClassification.objects.filter(
                staff=staf.admin, classification__id=classification_id
            ).delete()

        # Unassign this teacher from all courses in the org, then reassign selected
        Course.objects.filter(org=org, teacher=staf.admin).update(teacher=None)
        if selected_courses:
            Course.objects.filter(id__in=selected_courses, org=org).update(teacher=staf.admin)

        messages.success(request, "Classifications and courses updated successfully.")
        return HttpResponseRedirect(reverse('schooladmin:updateClass', args=(mem.id,)))

    clas = Classification.objects.filter(org=org)
    current_class_ids = [c.classification.id for c in current_classifications]
    all_courses = Course.objects.filter(org=org, status='active').prefetch_related('classifications')
    assigned_course_ids = list(Course.objects.filter(org=org, teacher=staf.admin).values_list('id', flat=True))

    dist = {
        'clas': clas,
        'staf': staf,
        'cas': current_classifications,
        'mem': mem,
        'holiday': current_class_ids,
        'courses': all_courses,
        'assigned_course_ids': assigned_course_ids,
        'org': org,
    }

    return render(request, "admin/updateClass.html", dist)




class AdminWifiManageView(LoginRequiredMixin, View):
    template_name = 'admin/wifi_manage.html' # Adjust path to match your folder structure

    def get(self, request, *args, **kwargs):
        # Security: Ensure only Admins (type "2") can access this
        if request.user.user_type != "2":
            messages.error(request, "Access Denied. Only Administrators can manage WiFi networks.")
            return redirect('dashboard') # Redirect to their respective dashboard

        org = request.user.schooladmin.org
        networks = WifiBased.objects.filter(org=org)
        
        return render(request, self.template_name, {
            'networks': networks, 
            'org': org
        })

    def post(self, request, *args, **kwargs):
        if request.user.user_type != "2":
            return redirect('dashboard')

        org = request.user.schooladmin.org
        
        # Handle Delete Action
        if 'delete_id' in request.POST:
            WifiBased.objects.filter(id=request.POST.get('delete_id'), org=org).delete()
            messages.success(request, "Authorized WiFi network removed successfully.")
            return redirect('schooladmin:admin_wifi_manage') # Adjust namespace to match your urls.py

        # Handle Add Action
        name = request.POST.get('name')
        ssid = request.POST.get('ssid')
        bssid = request.POST.get('bssid', '').strip().upper() # Clean up BSSID format

        if name and ssid and bssid:
            # Prevent duplicates
            if WifiBased.objects.filter(org=org, bssid=bssid).exists():
                messages.warning(request, "This BSSID is already registered to your organization.")
            else:
                WifiBased.objects.create(org=org, name=name, ssid=ssid, bssid=bssid)
                messages.success(request, f"Network '{name}' is now authorized for mobile check-ins.")
        else:
            messages.error(request, "All fields (Location Name, SSID, BSSID) are required.")

        return redirect('schooladmin:admin_wifi_manage')


# =============================================================
# FINANCE MODULE
# =============================================================

def _get_org(request):
    if request.user.user_type == "2":
        return request.user.schooladmin.org
    if request.user.user_type == "3":
        return request.user.staff.org
    return None


class FinanceDashboardView(View):
    template_name = 'admin/finance/dashboard.html'

    def get(self, request):
        org = _get_org(request)
        today = datetime.date.today()
        month_start = today.replace(day=1)

        income_qs = FinancialTransaction.objects.filter(org=org, transaction_type='income')
        expense_qs = FinancialTransaction.objects.filter(org=org, transaction_type='expense')

        total_income = income_qs.aggregate(t=Sum('amount'))['t'] or 0
        total_expense = expense_qs.aggregate(t=Sum('amount'))['t'] or 0
        today_income = income_qs.filter(transaction_date=today).aggregate(t=Sum('amount'))['t'] or 0
        today_expense = expense_qs.filter(transaction_date=today).aggregate(t=Sum('amount'))['t'] or 0
        month_income = income_qs.filter(transaction_date__gte=month_start).aggregate(t=Sum('amount'))['t'] or 0
        month_expense = expense_qs.filter(transaction_date__gte=month_start).aggregate(t=Sum('amount'))['t'] or 0

        recent_transactions = FinancialTransaction.objects.filter(org=org).select_related('branch', 'category').order_by('-transaction_date')[:10]
        categories = TransactionCategory.objects.filter(org=org)
        branches = Branch.objects.filter(org=org, status='active')

        context = {
            'org': org,
            'total_income': total_income,
            'total_expense': total_expense,
            'net_balance': total_income - total_expense,
            'today_income': today_income,
            'today_expense': today_expense,
            'month_income': month_income,
            'month_expense': month_expense,
            'recent_transactions': recent_transactions,
            'categories': categories,
            'branches': branches,
        }
        return render(request, self.template_name, context)


class IncomeListView(View):
    template_name = 'admin/finance/income_list.html'

    def get(self, request):
        org = _get_org(request)
        qs = FinancialTransaction.objects.filter(org=org, transaction_type='income').select_related('branch', 'category', 'created_by').order_by('-transaction_date')

        branch_id = request.GET.get('branch')
        category_id = request.GET.get('category')
        date_from = request.GET.get('date_from')
        date_to = request.GET.get('date_to')
        payment_method = request.GET.get('payment_method')

        if branch_id:
            qs = qs.filter(branch_id=branch_id)
        if category_id:
            qs = qs.filter(category_id=category_id)
        if date_from:
            qs = qs.filter(transaction_date__gte=date_from)
        if date_to:
            qs = qs.filter(transaction_date__lte=date_to)
        if payment_method:
            qs = qs.filter(payment_method=payment_method)

        total = qs.aggregate(t=Sum('amount'))['t'] or 0
        context = {
            'org': org,
            'transactions': qs,
            'total': total,
            'branches': Branch.objects.filter(org=org, status='active'),
            'categories': TransactionCategory.objects.filter(org=org, transaction_type='income'),
            'selected_branch': branch_id,
            'selected_category': category_id,
            'date_from': date_from,
            'date_to': date_to,
            'payment_method': payment_method,
        }
        return render(request, self.template_name, context)


class AddIncomeView(View):
    template_name = 'admin/finance/add_income.html'

    def get(self, request):
        org = _get_org(request)
        context = {
            'org': org,
            'branches': Branch.objects.filter(org=org, status='active'),
            'categories': TransactionCategory.objects.filter(org=org, transaction_type='income'),
            'today': datetime.date.today().strftime('%Y-%m-%d'),
        }
        return render(request, self.template_name, context)

    def post(self, request):
        org = _get_org(request)
        try:
            title = request.POST.get('title', '').strip()
            amount = request.POST.get('amount')
            category_id = request.POST.get('category')
            branch_id = request.POST.get('branch')
            transaction_date = request.POST.get('transaction_date')
            payment_method = request.POST.get('payment_method', 'cash')
            note = request.POST.get('note', '')
            reference = request.POST.get('reference_number', '')

            if not all([title, amount, transaction_date]):
                messages.error(request, "Title, amount, and date are required.")
                return redirect('schooladmin:add_income')

            FinancialTransaction.objects.create(
                org=org,
                transaction_type='income',
                title=title,
                amount=amount,
                category_id=category_id if category_id else None,
                branch_id=branch_id if branch_id else None,
                transaction_date=transaction_date,
                payment_method=payment_method,
                note=note,
                reference_number=reference,
                created_by=request.user,
            )
            messages.success(request, f"Income '{title}' added successfully.")
            return redirect('schooladmin:income_list')
        except Exception as e:
            messages.error(request, f"Error: {e}")
            return redirect('schooladmin:add_income')


class EditIncomeView(View):
    def get(self, request, pk):
        org = _get_org(request)
        tx = get_object_or_404(FinancialTransaction, pk=pk, org=org, transaction_type='income')
        context = {
            'org': org,
            'tx': tx,
            'branches': Branch.objects.filter(org=org, status='active'),
            'categories': TransactionCategory.objects.filter(org=org, transaction_type='income'),
        }
        return render(request, 'admin/finance/edit_income.html', context)

    def post(self, request, pk):
        org = _get_org(request)
        tx = get_object_or_404(FinancialTransaction, pk=pk, org=org, transaction_type='income')
        tx.title = request.POST.get('title', tx.title)
        tx.amount = request.POST.get('amount', tx.amount)
        tx.category_id = request.POST.get('category') or None
        tx.branch_id = request.POST.get('branch') or None
        tx.transaction_date = request.POST.get('transaction_date', tx.transaction_date)
        tx.payment_method = request.POST.get('payment_method', tx.payment_method)
        tx.note = request.POST.get('note', '')
        tx.reference_number = request.POST.get('reference_number', '')
        tx.save()
        messages.success(request, "Income updated successfully.")
        return redirect('schooladmin:income_list')


def delete_income(request, pk):
    org = _get_org(request)
    tx = get_object_or_404(FinancialTransaction, pk=pk, org=org, transaction_type='income')
    tx.delete()
    messages.success(request, "Income deleted.")
    return redirect('schooladmin:income_list')


class ExpenseListView(View):
    template_name = 'admin/finance/expense_list.html'

    def get(self, request):
        org = _get_org(request)
        qs = FinancialTransaction.objects.filter(org=org, transaction_type='expense').select_related('branch', 'category', 'created_by').order_by('-transaction_date')

        branch_id = request.GET.get('branch')
        category_id = request.GET.get('category')
        date_from = request.GET.get('date_from')
        date_to = request.GET.get('date_to')
        payment_method = request.GET.get('payment_method')

        if branch_id:
            qs = qs.filter(branch_id=branch_id)
        if category_id:
            qs = qs.filter(category_id=category_id)
        if date_from:
            qs = qs.filter(transaction_date__gte=date_from)
        if date_to:
            qs = qs.filter(transaction_date__lte=date_to)
        if payment_method:
            qs = qs.filter(payment_method=payment_method)

        total = qs.aggregate(t=Sum('amount'))['t'] or 0
        context = {
            'org': org,
            'transactions': qs,
            'total': total,
            'branches': Branch.objects.filter(org=org, status='active'),
            'categories': TransactionCategory.objects.filter(org=org, transaction_type='expense'),
            'selected_branch': branch_id,
            'selected_category': category_id,
            'date_from': date_from,
            'date_to': date_to,
            'payment_method': payment_method,
        }
        return render(request, self.template_name, context)


class AddExpenseView(View):
    def get(self, request):
        org = _get_org(request)
        context = {
            'org': org,
            'branches': Branch.objects.filter(org=org, status='active'),
            'categories': TransactionCategory.objects.filter(org=org, transaction_type='expense'),
            'today': datetime.date.today().strftime('%Y-%m-%d'),
        }
        return render(request, 'admin/finance/add_expense.html', context)

    def post(self, request):
        org = _get_org(request)
        try:
            title = request.POST.get('title', '').strip()
            amount = request.POST.get('amount')
            category_id = request.POST.get('category')
            branch_id = request.POST.get('branch')
            transaction_date = request.POST.get('transaction_date')
            payment_method = request.POST.get('payment_method', 'cash')
            note = request.POST.get('note', '')
            reference = request.POST.get('reference_number', '')

            if not all([title, amount, transaction_date]):
                messages.error(request, "Title, amount, and date are required.")
                return redirect('schooladmin:add_expense')

            FinancialTransaction.objects.create(
                org=org,
                transaction_type='expense',
                title=title,
                amount=amount,
                category_id=category_id if category_id else None,
                branch_id=branch_id if branch_id else None,
                transaction_date=transaction_date,
                payment_method=payment_method,
                note=note,
                reference_number=reference,
                created_by=request.user,
            )
            messages.success(request, f"Expense '{title}' added successfully.")
            return redirect('schooladmin:expense_list')
        except Exception as e:
            messages.error(request, f"Error: {e}")
            return redirect('schooladmin:add_expense')


class EditExpenseView(View):
    def get(self, request, pk):
        org = _get_org(request)
        tx = get_object_or_404(FinancialTransaction, pk=pk, org=org, transaction_type='expense')
        context = {
            'org': org,
            'tx': tx,
            'branches': Branch.objects.filter(org=org, status='active'),
            'categories': TransactionCategory.objects.filter(org=org, transaction_type='expense'),
        }
        return render(request, 'admin/finance/edit_expense.html', context)

    def post(self, request, pk):
        org = _get_org(request)
        tx = get_object_or_404(FinancialTransaction, pk=pk, org=org, transaction_type='expense')
        tx.title = request.POST.get('title', tx.title)
        tx.amount = request.POST.get('amount', tx.amount)
        tx.category_id = request.POST.get('category') or None
        tx.branch_id = request.POST.get('branch') or None
        tx.transaction_date = request.POST.get('transaction_date', tx.transaction_date)
        tx.payment_method = request.POST.get('payment_method', tx.payment_method)
        tx.note = request.POST.get('note', '')
        tx.reference_number = request.POST.get('reference_number', '')
        tx.save()
        messages.success(request, "Expense updated successfully.")
        return redirect('schooladmin:expense_list')


def delete_expense(request, pk):
    org = _get_org(request)
    tx = get_object_or_404(FinancialTransaction, pk=pk, org=org, transaction_type='expense')
    tx.delete()
    messages.success(request, "Expense deleted.")
    return redirect('schooladmin:expense_list')


class FinanceCategoryView(View):
    template_name = 'admin/finance/categories.html'

    def get(self, request):
        org = _get_org(request)
        context = {
            'org': org,
            'categories': TransactionCategory.objects.filter(org=org).order_by('transaction_type', 'name'),
        }
        return render(request, self.template_name, context)

    def post(self, request):
        org = _get_org(request)
        action = request.POST.get('action')
        if action == 'add':
            name = request.POST.get('name', '').strip()
            tx_type = request.POST.get('transaction_type', 'income')
            if name:
                TransactionCategory.objects.get_or_create(org=org, name=name, transaction_type=tx_type)
                messages.success(request, f"Category '{name}' added.")
            else:
                messages.error(request, "Category name is required.")
        elif action == 'delete':
            cat_id = request.POST.get('cat_id')
            TransactionCategory.objects.filter(pk=cat_id, org=org).delete()
            messages.success(request, "Category deleted.")
        return redirect('schooladmin:finance_categories')


# =============================================================
# STOCK MODULE
# =============================================================

class StockDashboardView(View):
    template_name = 'admin/stock/dashboard.html'

    def get(self, request):
        org = _get_org(request)
        items = StockItem.objects.filter(org=org, status='active').select_related('category', 'branch')
        low_stock = [i for i in items if i.is_low_stock]
        total_items = items.count()
        total_value = sum((i.quantity * (i.purchase_cost or 0)) for i in items)
        recent_movements = StockMovement.objects.filter(org=org).select_related('item', 'branch').order_by('-movement_date')[:10]
        categories = StockCategory.objects.filter(org=org)
        branches = Branch.objects.filter(org=org, status='active')
        context = {
            'org': org,
            'items': items,
            'low_stock': low_stock,
            'low_stock_count': len(low_stock),
            'total_items': total_items,
            'total_value': total_value,
            'recent_movements': recent_movements,
            'categories': categories,
            'branches': branches,
        }
        return render(request, self.template_name, context)


class StockItemListView(View):
    template_name = 'admin/stock/item_list.html'

    def get(self, request):
        org = _get_org(request)
        qs = StockItem.objects.filter(org=org).select_related('category', 'branch').order_by('name')
        branch_id = request.GET.get('branch')
        category_id = request.GET.get('category')
        status = request.GET.get('status')
        search = request.GET.get('search', '')
        if branch_id:
            qs = qs.filter(branch_id=branch_id)
        if category_id:
            qs = qs.filter(category_id=category_id)
        if status:
            qs = qs.filter(status=status)
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(sku__icontains=search))
        context = {
            'org': org,
            'items': qs,
            'branches': Branch.objects.filter(org=org, status='active'),
            'categories': StockCategory.objects.filter(org=org),
            'selected_branch': branch_id,
            'selected_category': category_id,
            'selected_status': status,
            'search': search,
        }
        return render(request, self.template_name, context)


class AddStockItemView(View):
    template_name = 'admin/stock/add_item.html'

    def get(self, request):
        org = _get_org(request)
        context = {
            'org': org,
            'branches': Branch.objects.filter(org=org, status='active'),
            'categories': StockCategory.objects.filter(org=org),
        }
        return render(request, self.template_name, context)

    def post(self, request):
        org = _get_org(request)
        try:
            name = request.POST.get('name', '').strip()
            if not name:
                messages.error(request, "Item name is required.")
                return redirect('schooladmin:add_stock_item')
            item = StockItem.objects.create(
                org=org,
                name=name,
                sku=request.POST.get('sku', ''),
                unit=request.POST.get('unit', 'pcs'),
                category_id=request.POST.get('category') or None,
                branch_id=request.POST.get('branch') or None,
                quantity=request.POST.get('quantity', 0),
                low_stock_threshold=request.POST.get('low_stock_threshold', 5),
                supplier=request.POST.get('supplier', ''),
                purchase_cost=request.POST.get('purchase_cost', 0),
                status=request.POST.get('status', 'active'),
            )
            if float(request.POST.get('quantity', 0)) > 0:
                StockMovement.objects.create(
                    org=org,
                    branch=item.branch,
                    item=item,
                    created_by=request.user,
                    movement_type='in',
                    quantity=item.quantity,
                    unit_cost=item.purchase_cost or 0,
                    movement_date=datetime.date.today(),
                    note='Initial stock',
                )
            messages.success(request, f"Stock item '{name}' added.")
            return redirect('schooladmin:stock_items')
        except Exception as e:
            messages.error(request, f"Error: {e}")
            return redirect('schooladmin:add_stock_item')


class EditStockItemView(View):
    def get(self, request, pk):
        org = _get_org(request)
        item = get_object_or_404(StockItem, pk=pk, org=org)
        context = {
            'org': org,
            'item': item,
            'branches': Branch.objects.filter(org=org, status='active'),
            'categories': StockCategory.objects.filter(org=org),
        }
        return render(request, 'admin/stock/edit_item.html', context)

    def post(self, request, pk):
        org = _get_org(request)
        item = get_object_or_404(StockItem, pk=pk, org=org)
        item.name = request.POST.get('name', item.name)
        item.sku = request.POST.get('sku', item.sku)
        item.unit = request.POST.get('unit', item.unit)
        item.category_id = request.POST.get('category') or None
        item.branch_id = request.POST.get('branch') or None
        item.low_stock_threshold = request.POST.get('low_stock_threshold', item.low_stock_threshold)
        item.supplier = request.POST.get('supplier', item.supplier)
        item.purchase_cost = request.POST.get('purchase_cost', item.purchase_cost)
        item.status = request.POST.get('status', item.status)
        item.save()
        messages.success(request, "Stock item updated.")
        return redirect('schooladmin:stock_items')


def delete_stock_item(request, pk):
    org = _get_org(request)
    item = get_object_or_404(StockItem, pk=pk, org=org)
    item.delete()
    messages.success(request, "Stock item deleted.")
    return redirect('schooladmin:stock_items')


class StockInView(View):
    template_name = 'admin/stock/stock_in.html'

    def get(self, request):
        org = _get_org(request)
        context = {
            'org': org,
            'items': StockItem.objects.filter(org=org, status='active').order_by('name'),
            'today': datetime.date.today().strftime('%Y-%m-%d'),
        }
        return render(request, self.template_name, context)

    def post(self, request):
        org = _get_org(request)
        item_id = request.POST.get('item')
        quantity = request.POST.get('quantity')
        unit_cost = request.POST.get('unit_cost', 0)
        note = request.POST.get('note', '')
        movement_date = request.POST.get('movement_date', datetime.date.today())
        if not item_id or not quantity:
            messages.error(request, "Item and quantity are required.")
            return redirect('schooladmin:stock_in')
        item = get_object_or_404(StockItem, pk=item_id, org=org)
        movement = StockMovement.objects.create(
            org=org, branch=item.branch, item=item,
            created_by=request.user, movement_type='in',
            quantity=Decimal(str(quantity)), unit_cost=Decimal(str(unit_cost or 0)),
            movement_date=movement_date, note=note,
        )
        # Auto-log purchase as Finance expense if unit_cost entered
        add_as_expense = request.POST.get('add_as_expense') == 'on'
        unit_cost_val = float(unit_cost or 0)
        if add_as_expense and unit_cost_val > 0:
            total_cost = float(quantity) * unit_cost_val
            stock_cat, _ = TransactionCategory.objects.get_or_create(
                org=org, name='Stock Purchase', transaction_type='expense'
            )
            FinancialTransaction.objects.create(
                org=org,
                transaction_type='expense',
                title=f"Stock Purchase — {item.name}",
                amount=Decimal(str(total_cost)),
                category=stock_cat,
                transaction_date=movement_date if movement_date else datetime.date.today(),
                note=f"Auto-linked: {quantity} × {item.name} @ Rs.{unit_cost_val}",
                created_by=request.user,
            )
        messages.success(request, f"Stock in recorded for '{item.name}'.")
        return redirect('schooladmin:stock_items')


class StockOutView(View):
    template_name = 'admin/stock/stock_out.html'

    def get(self, request):
        org = _get_org(request)
        context = {
            'org': org,
            'items': StockItem.objects.filter(org=org, status='active').order_by('name'),
            'today': datetime.date.today().strftime('%Y-%m-%d'),
        }
        return render(request, self.template_name, context)

    def post(self, request):
        org = _get_org(request)
        item_id = request.POST.get('item')
        quantity = float(request.POST.get('quantity', 0))
        note = request.POST.get('note', '')
        movement_date = request.POST.get('movement_date', datetime.date.today())
        if not item_id or quantity <= 0:
            messages.error(request, "Item and valid quantity are required.")
            return redirect('schooladmin:stock_out')
        item = get_object_or_404(StockItem, pk=item_id, org=org)
        if item.quantity < quantity:
            messages.error(request, f"Insufficient stock. Available: {item.quantity} {item.unit}")
            return redirect('schooladmin:stock_out')
        StockMovement.objects.create(
            org=org, branch=item.branch, item=item,
            created_by=request.user, movement_type='out',
            quantity=quantity, unit_cost=item.purchase_cost or 0,
            movement_date=movement_date, note=note,
        )
        messages.success(request, f"Stock out recorded for '{item.name}'.")
        return redirect('schooladmin:stock_items')


class StockMovementHistoryView(View):
    template_name = 'admin/stock/movement_history.html'

    def get(self, request):
        org = _get_org(request)
        qs = StockMovement.objects.filter(org=org).select_related('item', 'branch', 'created_by').order_by('-movement_date', '-id')
        item_id = request.GET.get('item')
        movement_type = request.GET.get('movement_type')
        date_from = request.GET.get('date_from')
        date_to = request.GET.get('date_to')
        if item_id:
            qs = qs.filter(item_id=item_id)
        if movement_type:
            qs = qs.filter(movement_type=movement_type)
        if date_from:
            qs = qs.filter(movement_date__gte=date_from)
        if date_to:
            qs = qs.filter(movement_date__lte=date_to)
        context = {
            'org': org,
            'movements': qs,
            'items': StockItem.objects.filter(org=org).order_by('name'),
            'selected_item': item_id,
            'selected_type': movement_type,
            'date_from': date_from,
            'date_to': date_to,
        }
        return render(request, self.template_name, context)


class StockCategoryView(View):
    template_name = 'admin/stock/categories.html'

    def get(self, request):
        org = _get_org(request)
        return render(request, self.template_name, {
            'org': org,
            'categories': StockCategory.objects.filter(org=org),
        })

    def post(self, request):
        org = _get_org(request)
        action = request.POST.get('action')
        if action == 'add':
            name = request.POST.get('name', '').strip()
            desc = request.POST.get('description', '')
            if name:
                StockCategory.objects.get_or_create(org=org, name=name, defaults={'description': desc})
                messages.success(request, f"Category '{name}' added.")
            else:
                messages.error(request, "Name is required.")
        elif action == 'delete':
            StockCategory.objects.filter(pk=request.POST.get('cat_id'), org=org).delete()
            messages.success(request, "Category deleted.")
        return redirect('schooladmin:stock_categories')


# =============================================================
# EVENT MANAGEMENT
# =============================================================

class EventListView(View):
    template_name = 'admin/events/event_list.html'

    def get(self, request):
        org = _get_org(request)
        qs = Event.objects.filter(org=org).select_related('branch', 'responsible_staff').order_by('-start_date')
        status = request.GET.get('status')
        event_type = request.GET.get('event_type')
        if status:
            qs = qs.filter(status=status)
        if event_type:
            qs = qs.filter(event_type=event_type)
        context = {
            'org': org,
            'events': qs,
            'branches': Branch.objects.filter(org=org, status='active'),
            'selected_status': status,
            'selected_type': event_type,
            'event_types': Event.EVENT_TYPE_CHOICES,
            'status_choices': Event.STATUS_CHOICES,
        }
        return render(request, self.template_name, context)


class AddEventView(View):
    def get(self, request):
        org = _get_org(request)
        context = {
            'org': org,
            'branches': Branch.objects.filter(org=org, status='active'),
            'staff_list': Staff.objects.filter(org=org).select_related('admin'),
            'event_types': Event.EVENT_TYPE_CHOICES,
            'today': datetime.date.today().strftime('%Y-%m-%d'),
        }
        return render(request, 'admin/events/add_event.html', context)

    def post(self, request):
        org = _get_org(request)
        try:
            event = Event.objects.create(
                org=org,
                title=request.POST.get('title'),
                event_type=request.POST.get('event_type', 'other'),
                branch_id=request.POST.get('branch') or None,
                start_date=request.POST.get('start_date'),
                end_date=request.POST.get('end_date'),
                location=request.POST.get('location', ''),
                description=request.POST.get('description', ''),
                responsible_staff_id=request.POST.get('responsible_staff') or None,
                status=request.POST.get('status', 'upcoming'),
            )
            messages.success(request, f"Event '{event.title}' created.")
            return redirect('schooladmin:event_detail', pk=event.pk)
        except Exception as e:
            messages.error(request, f"Error: {e}")
            return redirect('schooladmin:add_event')


class EventDetailView(View):
    template_name = 'admin/events/event_detail.html'

    def get(self, request, pk):
        org = _get_org(request)
        event = get_object_or_404(Event, pk=pk, org=org)
        stock_usages = EventStockUsage.objects.filter(event=event).select_related('item')
        available_items = StockItem.objects.filter(org=org, status='active').order_by('name')
        context = {
            'org': org,
            'event': event,
            'stock_usages': stock_usages,
            'available_items': available_items,
            'branches': Branch.objects.filter(org=org, status='active'),
            'staff_list': Staff.objects.filter(org=org).select_related('admin'),
            'event_types': Event.EVENT_TYPE_CHOICES,
            'status_choices': Event.STATUS_CHOICES,
        }
        return render(request, self.template_name, context)

    def post(self, request, pk):
        org = _get_org(request)
        event = get_object_or_404(Event, pk=pk, org=org)
        action = request.POST.get('action')

        if action == 'update_event':
            event.title = request.POST.get('title', event.title)
            event.event_type = request.POST.get('event_type', event.event_type)
            event.branch_id = request.POST.get('branch') or None
            event.start_date = request.POST.get('start_date', event.start_date)
            event.end_date = request.POST.get('end_date', event.end_date)
            event.location = request.POST.get('location', event.location)
            event.description = request.POST.get('description', event.description)
            event.responsible_staff_id = request.POST.get('responsible_staff') or None
            event.status = request.POST.get('status', event.status)
            event.save()
            messages.success(request, "Event updated.")

        elif action == 'add_stock':
            item_id = request.POST.get('item_id')
            quantity = float(request.POST.get('quantity', 0))
            if item_id and quantity > 0:
                item = get_object_or_404(StockItem, pk=item_id, org=org)
                if item.quantity < quantity:
                    messages.error(request, f"Not enough stock for '{item.name}'. Available: {item.quantity}")
                else:
                    EventStockUsage.objects.create(event=event, item=item, quantity_used=quantity, note=request.POST.get('note', ''))
                    messages.success(request, f"Stock usage recorded for '{item.name}'.")
            else:
                messages.error(request, "Select an item and enter valid quantity.")

        elif action == 'remove_stock':
            usage_id = request.POST.get('usage_id')
            usage = get_object_or_404(EventStockUsage, pk=usage_id, event=event)
            usage.delete()
            messages.success(request, "Stock usage removed and quantity restored.")

        return redirect('schooladmin:event_detail', pk=pk)


def delete_event(request, pk):
    org = _get_org(request)
    event = get_object_or_404(Event, pk=pk, org=org)
    event.delete()
    messages.success(request, "Event deleted.")
    return redirect('schooladmin:event_list')


# =============================================================
# COURSE MANAGEMENT
# =============================================================

class CourseListView(View):
    template_name = 'admin/courses/course_list.html'

    def get(self, request):
        org = _get_org(request)
        qs = Course.objects.filter(org=org).select_related('branch', 'teacher').prefetch_related('classifications', 'sections').order_by('name')
        context = {
            'org': org,
            'courses': qs,
            'branches': Branch.objects.filter(org=org, status='active'),
        }
        return render(request, self.template_name, context)


class AddCourseView(View):
    def get(self, request):
        org = _get_org(request)
        context = {
            'org': org,
            'branches': Branch.objects.filter(org=org, status='active'),
            'classifications': Classification.objects.filter(org=org),
            'sections': Section.objects.filter(org=org),
            'staff_list': Staff.objects.filter(org=org).select_related('admin'),
        }
        return render(request, 'admin/courses/add_course.html', context)

    def post(self, request):
        org = _get_org(request)
        try:
            course = Course.objects.create(
                org=org,
                name=request.POST.get('name'),
                code=request.POST.get('code', ''),
                branch_id=request.POST.get('branch') or None,
                teacher_id=request.POST.get('teacher') or None,
                description=request.POST.get('description', ''),
                credit_hour=request.POST.get('credit_hour', 0),
                status=request.POST.get('status', 'active'),
            )
            classification_ids = request.POST.getlist('classifications')
            section_ids = request.POST.getlist('sections')
            if classification_ids:
                course.classifications.set(classification_ids)
            if section_ids:
                course.sections.set(section_ids)
            messages.success(request, f"Course '{course.name}' created.")
            return redirect('schooladmin:course_list')
        except Exception as e:
            messages.error(request, f"Error: {e}")
            return redirect('schooladmin:add_course')


def delete_course(request, pk):
    org = _get_org(request)
    course = get_object_or_404(Course, pk=pk, org=org)
    course.delete()
    messages.success(request, "Course deleted.")
    return redirect('schooladmin:course_list')


class CourseAttendanceView(View):
    template_name = 'admin/courses/course_attendance.html'

    def get(self, request):
        org = _get_org(request)
        courses = Course.objects.filter(org=org, status='active')
        selected_course_id = request.GET.get('course')
        selected_date = request.GET.get('date', datetime.date.today().strftime('%Y-%m-%d'))
        members_list = []
        course = None
        attendance_records = {}

        if selected_course_id:
            course = get_object_or_404(Course, pk=selected_course_id, org=org)
            members_list = member.objects.filter(org=org, courses__id=selected_course_id)
            records = CourseAttendance.objects.filter(course=course, attendance_date=selected_date)
            attendance_records = {r.pk: r for r in records}

        context = {
            'org': org,
            'courses': courses,
            'selected_course': course,
            'selected_date': selected_date,
            'members_list': members_list,
            'attendance_records': attendance_records,
        }
        return render(request, self.template_name, context)

    def post(self, request):
        org = _get_org(request)
        course_id = request.POST.get('course_id')
        attendance_date = request.POST.get('attendance_date')
        topic_taught = request.POST.get('topic_taught', '')
        gap_note = request.POST.get('gap_note', '')
        present_ids = request.POST.getlist('present_members')

        course = get_object_or_404(Course, pk=course_id, org=org)
        all_members = member.objects.filter(org=org, courses__id=course_id)

        for mem in all_members:
            is_present = str(mem.id) in present_ids
            if not is_present:
                AttendanceGap.objects.get_or_create(
                    org=org, member=mem, course=course, date=attendance_date,
                    defaults={
                        'branch': course.branch,
                        'teacher': request.user,
                        'topic_missed': topic_taught,
                        'reason': 'Absent from course session',
                        'recovery_status': 'pending',
                    }
                )

        if topic_taught:
            CourseAttendance.objects.update_or_create(
                org=org, course=course, attendance_date=attendance_date,
                staff=request.user,
                defaults={'topic_taught': topic_taught, 'gap_note': gap_note,
                          'branch': course.branch, 'classification': None, 'section': None}
            )

        messages.success(request, f"Course attendance saved for {attendance_date}.")
        return redirect(f"{request.path}?course={course_id}&date={attendance_date}")


# =============================================================
# STUDY GAP / TEACHING LOG
# =============================================================

class StudyGapListView(View):
    template_name = 'admin/study_gap/list.html'

    def get(self, request):
        org = _get_org(request)
        qs = AttendanceGap.objects.filter(org=org).select_related('member', 'course', 'branch').order_by('-date')
        course_id = request.GET.get('course')
        status = request.GET.get('recovery_status')
        member_id = request.GET.get('member')
        if course_id:
            qs = qs.filter(course_id=course_id)
        if status:
            qs = qs.filter(recovery_status=status)
        if member_id:
            qs = qs.filter(member_id=member_id)
        context = {
            'org': org,
            'gaps': qs,
            'courses': Course.objects.filter(org=org),
            'members': member.objects.filter(org=org),
            'selected_course': course_id,
            'selected_status': status,
            'selected_member': member_id,
            'status_choices': AttendanceGap._meta.get_field('recovery_status').choices,
        }
        return render(request, self.template_name, context)


def update_gap_status(request, pk):
    org = _get_org(request)
    gap = get_object_or_404(AttendanceGap, pk=pk, org=org)
    new_status = request.POST.get('status')
    if new_status:
        gap.recovery_status = new_status
        if new_status == 'covered':
            gap.covered_at = timezone.now()
        gap.save()
        messages.success(request, "Study gap status updated.")
    return redirect('schooladmin:study_gap_list')


# =============================================================
# RESULT MANAGEMENT
# =============================================================
from handle.models import compute_grade as _compute_grade
from handle.models import Section as _Section


class SubjectListView(View):
    template_name = 'admin/results/subjects.html'

    def _get_subjects(self, org, classification_id=None, section_id=None):
        qs = Subject.objects.filter(org=org).select_related('classification', 'section', 'teacher')
        if classification_id:
            qs = qs.filter(classification_id=classification_id)
        if section_id:
            qs = qs.filter(section_id=section_id)
        return qs

    def get(self, request):
        org = _get_org(request)
        classification_id = request.GET.get('classification')
        section_id = request.GET.get('section')
        classifications = Classification.objects.filter(org=org)
        sections = _Section.objects.filter(org=org, classification_id=classification_id) if classification_id else _Section.objects.none()
        from management.models import CustomUser
        teachers = CustomUser.objects.filter(staff__org=org)
        context = {
            'org': org,
            'subjects': self._get_subjects(org, classification_id, section_id),
            'classifications': classifications,
            'sections': sections,
            'teachers': teachers,
            'selected_classification': classification_id,
            'selected_section': section_id,
        }
        return render(request, self.template_name, context)

    def post(self, request):
        org = _get_org(request)
        action = request.POST.get('action')
        if action == 'add':
            cls_id = request.POST.get('classification') or None
            sec_id = request.POST.get('section') or None
            name = request.POST.get('name', '').strip()
            full_m = float(request.POST.get('full_marks', 100))
            pass_m = float(request.POST.get('pass_marks', 40))
            if not cls_id:
                messages.error(request, "Classification is required.")
            elif not name:
                messages.error(request, "Subject name is required.")
            elif pass_m < 0:
                messages.error(request, "Pass marks cannot be negative.")
            elif full_m <= pass_m:
                messages.error(request, "Full marks must be greater than pass marks.")
            elif Subject.objects.filter(org=org, classification_id=cls_id, section_id=sec_id, name=name).exists():
                messages.error(request, "A subject with this name already exists in this classification/section.")
            else:
                Subject.objects.create(
                    org=org,
                    name=name,
                    code=request.POST.get('code', '').strip() or None,
                    description=request.POST.get('description', '').strip() or None,
                    credit_hour=request.POST.get('credit_hour') or None,
                    classification_id=cls_id,
                    section_id=sec_id,
                    teacher_id=request.POST.get('teacher') or None,
                    full_marks=full_m,
                    pass_marks=pass_m,
                    monthly_fee=_money(request.POST.get('monthly_fee') or 0),
                    one_time_fee=_money(request.POST.get('one_time_fee') or 0),
                    status=request.POST.get('status', 'active'),
                )
                messages.success(request, f"Subject '{name}' added successfully.")
        elif action == 'edit':
            subj = get_object_or_404(Subject, pk=request.POST.get('subject_id'), org=org)
            subj.name = request.POST.get('name', subj.name).strip()
            subj.code = request.POST.get('code', '').strip() or None
            subj.teacher_id = request.POST.get('teacher') or None
            subj.full_marks = float(request.POST.get('full_marks', subj.full_marks))
            subj.pass_marks = float(request.POST.get('pass_marks', subj.pass_marks))
            subj.monthly_fee = _money(request.POST.get('monthly_fee', subj.monthly_fee))
            subj.one_time_fee = _money(request.POST.get('one_time_fee', subj.one_time_fee))
            subj.status = request.POST.get('status', subj.status)
            subj.credit_hour = request.POST.get('credit_hour') or None
            subj.save()
            messages.success(request, "Subject updated.")
        elif action == 'delete':
            Subject.objects.filter(pk=request.POST.get('subject_id'), org=org).delete()
            messages.success(request, "Subject deleted.")
        params = ''
        if request.POST.get('classification'):
            params = f"?classification={request.POST.get('classification')}"
        return redirect(f"{reverse('schooladmin:subject_list')}{params}")


class ExamTermListView(View):
    template_name = 'admin/results/exam_terms.html'

    def get(self, request):
        org = _get_org(request)
        qs = ExamTerm.objects.filter(org=org).select_related('classification', 'section')
        classification_id = request.GET.get('classification')
        if classification_id:
            qs = qs.filter(classification_id=classification_id)
        total_students = member.objects.filter(org=org).count()
        # Annotate each exam with entry/publish stats
        exams_data = []
        for exam in qs:
            entry_count = ResultRecord.objects.filter(exam=exam).values('student').distinct().count()
            exams_data.append({'exam': exam, 'entry_count': entry_count, 'total_students': total_students})
        context = {
            'org': org,
            'exams_data': exams_data,
            'classifications': Classification.objects.filter(org=org),
            'selected_classification': classification_id,
        }
        return render(request, self.template_name, context)

    def post(self, request):
        org = _get_org(request)
        action = request.POST.get('action')
        if action == 'add':
            ExamTerm.objects.create(
                org=org,
                name=request.POST.get('name'),
                academic_year=request.POST.get('academic_year', '').strip() or None,
                classification_id=request.POST.get('classification') or None,
                section_id=request.POST.get('section') or None,
                start_date=request.POST.get('start_date') or None,
                end_date=request.POST.get('end_date') or None,
                status=request.POST.get('status', 'draft'),
            )
            messages.success(request, "Exam created.")
        elif action == 'delete':
            ExamTerm.objects.filter(pk=request.POST.get('exam_id'), org=org).delete()
            messages.success(request, "Exam deleted.")
        elif action == 'set_status':
            exam = get_object_or_404(ExamTerm, pk=request.POST.get('exam_id'), org=org)
            new_status = request.POST.get('status')
            exam.status = new_status
            if new_status == 'published':
                exam.is_published = True
            elif new_status in ('draft', 'archived'):
                exam.is_published = False
            exam.save()
            messages.success(request, f"Exam status updated to {exam.get_status_display()}.")
        elif action == 'toggle_publish':
            exam = get_object_or_404(ExamTerm, pk=request.POST.get('exam_id'), org=org)
            exam.is_published = not exam.is_published
            exam.status = 'published' if exam.is_published else 'marks_entry'
            exam.save()
            messages.success(request, f"Result {'published' if exam.is_published else 'unpublished'}.")
        return redirect('schooladmin:exam_terms')


class ResultEntryView(View):
    template_name = 'admin/results/result_entry.html'

    def _build_members_data(self, org, exam, classification, section_id=None):
        subjects_qs = Subject.objects.filter(org=org, classification=classification, status='active')
        if section_id:
            subjects_qs = subjects_qs.filter(Q(section_id=section_id) | Q(section__isnull=True))
        subjects = list(subjects_qs)

        members_filter = {'org': org, 'classification': classification}
        if section_id:
            members_filter['section_id'] = section_id
        members_qs = member.objects.filter(**members_filter).order_by('name')

        members_data = []
        for mem in members_qs:
            existing = {r.subject_id: r for r in ResultRecord.objects.filter(student=mem, exam=exam).select_related('subject')} if exam else {}
            members_data.append({'member': mem, 'records': existing})
        return subjects, members_data

    def get(self, request):
        org = _get_org(request)
        exam_id = request.GET.get('exam')
        classification_id = request.GET.get('classification')
        section_id = request.GET.get('section')
        exam = classification = None
        subjects = []
        members_data = []
        sections = []

        if exam_id:
            exam = get_object_or_404(ExamTerm, pk=exam_id, org=org)
        if classification_id:
            classification = get_object_or_404(Classification, pk=classification_id, org=org)
            sections = list(_Section.objects.filter(org=org, classification=classification))
            if exam:
                subjects, members_data = self._build_members_data(org, exam, classification, section_id)

        context = {
            'org': org,
            'exams': ExamTerm.objects.filter(org=org),
            'classifications': Classification.objects.filter(org=org),
            'sections': sections,
            'selected_exam': exam,
            'selected_classification': classification,
            'selected_section': section_id,
            'subjects': subjects,
            'members_data': members_data,
        }
        return render(request, self.template_name, context)

    def post(self, request):
        org = _get_org(request)
        exam_id = request.POST.get('exam_id')
        classification_id = request.POST.get('classification_id')
        section_id = request.POST.get('section_id') or None
        exam = get_object_or_404(ExamTerm, pk=exam_id, org=org)
        subjects_qs = Subject.objects.filter(org=org, classification_id=classification_id, status='active')
        if section_id:
            subjects_qs = subjects_qs.filter(Q(section_id=section_id) | Q(section__isnull=True))
        members_filter = {'org': org, 'classification_id': classification_id}
        if section_id:
            members_filter['section_id'] = section_id
        members_qs = member.objects.filter(**members_filter)

        saved = 0
        for mem in members_qs:
            for subj in subjects_qs:
                marks_key = f"marks_{mem.id}_{subj.id}"
                absent_key = f"absent_{mem.id}_{subj.id}"
                marks_val = request.POST.get(marks_key, '').strip()
                is_absent = request.POST.get(absent_key) == 'on'
                if marks_val != '' or is_absent:
                    try:
                        marks_float = 0.0 if is_absent else float(marks_val)
                        ResultRecord.objects.update_or_create(
                            student=mem, exam=exam, subject=subj,
                            defaults={
                                'obtained_marks': marks_float,
                                'is_absent': is_absent,
                                'remarks': request.POST.get(f"remarks_{mem.id}_{subj.id}", '').strip() or ('Absent' if is_absent else None),
                                'updated_by': request.user,
                            }
                        )
                        saved += 1
                    except (ValueError, Exception):
                        pass

        # Auto-set exam to marks_entry status
        if exam.status == 'draft' and saved:
            exam.status = 'marks_entry'
            exam.save(update_fields=['status'])

        messages.success(request, f"Saved {saved} result records.")
        qs = f"?exam={exam_id}&classification={classification_id}"
        if section_id:
            qs += f"&section={section_id}"
        return redirect(f"{reverse('schooladmin:result_entry')}{qs}")


class ResultReportView(View):
    template_name = 'admin/results/result_report.html'

    def get(self, request):
        org = _get_org(request)
        exam_id = request.GET.get('exam')
        classification_id = request.GET.get('classification')
        section_id = request.GET.get('section')
        exam = classification = None
        report_data = []
        subjects = []
        sections = []

        if exam_id and classification_id:
            exam = get_object_or_404(ExamTerm, pk=exam_id, org=org)
            classification = get_object_or_404(Classification, pk=classification_id, org=org)
            sections = list(_Section.objects.filter(org=org, classification=classification))
            subjects_qs = Subject.objects.filter(org=org, classification=classification, status='active')
            if section_id:
                subjects_qs = subjects_qs.filter(Q(section_id=section_id) | Q(section__isnull=True))
            subjects = list(subjects_qs)
            members_filter = {'org': org, 'classification': classification}
            if section_id:
                members_filter['section_id'] = section_id
            members_qs = member.objects.filter(**members_filter).order_by('name')

            pass_count = fail_count = absent_count = entry_count = 0
            for mem in members_qs:
                results = {r.subject_id: r for r in ResultRecord.objects.filter(student=mem, exam=exam).select_related('subject')}
                total_obt = float(sum(r.obtained_marks for r in results.values()))
                full_total = float(sum(s.full_marks for s in subjects))
                pct = round(total_obt / full_total * 100, 1) if full_total else 0
                passed = all(r.is_passed for r in results.values()) if results else False
                has_absent = any(r.is_absent for r in results.values())
                if results:
                    entry_count += 1
                    if has_absent:
                        absent_count += 1
                    elif passed:
                        pass_count += 1
                    else:
                        fail_count += 1
                report_data.append({
                    'member': mem,
                    'results': results,
                    'total': total_obt,
                    'full_total': full_total,
                    'percentage': pct,
                    'passed': passed,
                    'grade': _compute_grade(pct),
                    'has_absent': has_absent,
                    'rank': 0,
                })

            # Assign ranks (by total marks desc)
            ranked = sorted([r for r in report_data if r['results']], key=lambda x: x['total'], reverse=True)
            for i, r in enumerate(ranked, 1):
                r['rank'] = i

            stat_summary = {
                'total_students': len(report_data),
                'entry_count': entry_count,
                'pass_count': pass_count,
                'fail_count': fail_count,
                'absent_count': absent_count,
                'pending_count': len(report_data) - entry_count,
            }
        else:
            stat_summary = {}

        context = {
            'org': org,
            'exams': ExamTerm.objects.filter(org=org),
            'classifications': Classification.objects.filter(org=org),
            'sections': sections,
            'selected_exam': exam,
            'selected_classification': classification,
            'selected_section': section_id,
            'subjects': subjects,
            'report_data': report_data,
            'stat_summary': stat_summary,
        }
        return render(request, self.template_name, context)


class ResultPublishSummaryView(View):
    """Pre-publish summary page for an exam."""

    def get(self, request, pk):
        org = _get_org(request)
        exam = get_object_or_404(ExamTerm, pk=pk, org=org)
        classifications = Classification.objects.filter(org=org)
        class_summaries = []
        pending_entry = 0
        for cls in classifications:
            students = list(member.objects.filter(org=org, classification=cls))
            if not students:
                continue
            entry_count = ResultRecord.objects.filter(exam=exam, student__in=students).values('student').distinct().count()
            pass_count = fail_count = absent_count = 0
            for mem in students:
                recs = list(ResultRecord.objects.filter(exam=exam, student=mem))
                if not recs:
                    continue
                if any(r.is_absent for r in recs):
                    absent_count += 1
                elif all(r.is_passed for r in recs):
                    pass_count += 1
                else:
                    fail_count += 1
            pending_for_cls = len(students) - entry_count
            if pending_for_cls > 0:
                pending_entry += 1
            class_summaries.append({
                'classification': cls.name,
                'section': None,
                'total_students': len(students),
                'entry_count': entry_count,
                'pass_count': pass_count,
                'fail_count': fail_count,
                'absent_count': absent_count,
            })
        context = {
            'org': org,
            'exam': exam,
            'class_summaries': class_summaries,
            'pending_entry': pending_entry,
            'total_records': ResultRecord.objects.filter(exam=exam).count(),
        }
        return render(request, 'admin/results/publish_summary.html', context)

    def post(self, request, pk):
        org = _get_org(request)
        exam = get_object_or_404(ExamTerm, pk=pk, org=org)
        exam.is_published = not exam.is_published
        exam.status = 'published' if exam.is_published else 'marks_entry'
        exam.save(update_fields=['is_published', 'status'])
        action_word = 'published' if exam.is_published else 'unpublished'
        messages.success(request, f"'{exam.name}' has been {action_word}.")
        return redirect('schooladmin:result_publish_summary', pk=pk)


class MarksheetView(View):
    """Printable marksheet for one student for one exam."""

    def get(self, request, exam_pk, member_pk):
        org = _get_org(request)
        exam = get_object_or_404(ExamTerm, pk=exam_pk, org=org)
        mem = get_object_or_404(member, pk=member_pk, org=org)
        subjects = _student_subjects(mem)
        results = {r.subject_id: r for r in ResultRecord.objects.filter(student=mem, exam=exam).select_related('subject')}
        rows = []
        total_obt = total_full = 0
        for subj in subjects:
            r = results.get(subj.id)
            rows.append({'subject': subj, 'record': r})
            total_full += float(subj.full_marks)
            if r:
                total_obt += float(r.obtained_marks)
        pct = round(total_obt / total_full * 100, 1) if total_full else 0
        passed = all(r['record'].is_passed for r in rows if r['record']) and bool(results)
        # Rank within classification
        all_members = member.objects.filter(org=org, classification=mem.classification)
        totals = []
        for m2 in all_members:
            t = float(sum(r.obtained_marks for r in ResultRecord.objects.filter(student=m2, exam=exam)))
            totals.append((m2.id, t))
        totals.sort(key=lambda x: x[1], reverse=True)
        rank = next((i+1 for i, (mid, _) in enumerate(totals) if mid == mem.id), '—')

        pass_count = sum(1 for r in rows if r['record'] and not r['record'].is_absent and r['record'].is_passed)
        fail_count = sum(1 for r in rows if r['record'] and not r['record'].is_absent and not r['record'].is_passed)
        absent_count = sum(1 for r in rows if r['record'] and r['record'].is_absent)
        context = {
            'org': org,
            'exam': exam,
            'member': mem,
            'result_rows': rows,
            'total_obtained': total_obt,
            'total_full': total_full,
            'percentage': pct,
            'overall_pass': passed,
            'overall_grade': _compute_grade(pct),
            'rank': rank,
            'pass_count': pass_count,
            'fail_count': fail_count,
            'absent_count': absent_count,
        }
        return render(request, 'admin/results/marksheet.html', context)


# =============================================================
# COMPLAINT SYSTEM
# =============================================================

class ComplaintListView(View):
    template_name = 'admin/complaints/list.html'

    def get(self, request):
        org = _get_org(request)
        qs = Complaint.objects.filter(org=org).select_related('filed_by', 'branch').order_by('-created_at')
        status = request.GET.get('status')
        priority = request.GET.get('priority')
        if status:
            qs = qs.filter(status=status)
        if priority:
            qs = qs.filter(priority=priority)
        context = {
            'org': org,
            'complaints': qs,
            'status_choices': Complaint.STATUS_CHOICES,
            'priority_choices': Complaint.PRIORITY_CHOICES,
            'selected_status': status,
            'selected_priority': priority,
            'pending_count': Complaint.objects.filter(org=org, status='pending').count(),
        }
        return render(request, self.template_name, context)


class ComplaintDetailView(View):
    template_name = 'admin/complaints/detail.html'

    def get(self, request, pk):
        org = _get_org(request)
        complaint = get_object_or_404(Complaint, pk=pk, org=org)
        return render(request, self.template_name, {'org': org, 'complaint': complaint, 'status_choices': Complaint.STATUS_CHOICES})

    def post(self, request, pk):
        org = _get_org(request)
        complaint = get_object_or_404(Complaint, pk=pk, org=org)
        complaint.status = request.POST.get('status', complaint.status)
        complaint.admin_remarks = request.POST.get('admin_remarks', '')
        resolution_date = request.POST.get('resolution_date')
        if resolution_date:
            complaint.resolution_date = resolution_date
        complaint.save()
        messages.success(request, "Complaint updated.")
        return redirect('schooladmin:complaint_detail', pk=pk)


class FileComplaintView(View):
    template_name = 'admin/complaints/file_complaint.html'

    def get(self, request):
        org = _get_org(request)
        context = {
            'org': org,
            'members': member.objects.filter(org=org),
            'branches': Branch.objects.filter(org=org, status='active'),
            'priority_choices': Complaint.PRIORITY_CHOICES,
        }
        return render(request, self.template_name, context)

    def post(self, request):
        org = _get_org(request)
        try:
            member_id = request.POST.get('filed_by')
            filed_by = get_object_or_404(member, pk=member_id, org=org)
            Complaint.objects.create(
                org=org,
                branch_id=request.POST.get('branch') or None,
                filed_by=filed_by,
                complaint_type=request.POST.get('complaint_type', ''),
                subject=request.POST.get('subject'),
                description=request.POST.get('description'),
                priority=request.POST.get('priority', 'medium'),
            )
            messages.success(request, "Complaint filed successfully.")
            return redirect('schooladmin:complaint_list')
        except Exception as e:
            messages.error(request, f"Error: {e}")
            return redirect('schooladmin:file_complaint')


# =============================================================
# HRMS EXTENDED - RESIGNATION
# =============================================================

class ResignationListView(View):
    template_name = 'admin/hrms/resignation_list.html'

    def get(self, request):
        org = _get_org(request)
        qs = ResignationRecord.objects.filter(org=org).select_related('member').order_by('-created_at')
        status = request.GET.get('status')
        self_applied_filter = request.GET.get('self_applied')
        if status:
            qs = qs.filter(status=status)
        if self_applied_filter == '1':
            qs = qs.filter(self_applied=True)
        elif self_applied_filter == '0':
            qs = qs.filter(self_applied=False)
        all_qs = ResignationRecord.objects.filter(org=org)
        context = {
            'org': org,
            'resignations': qs,
            'status_choices': ResignationRecord.STATUS_CHOICES,
            'selected_status': status,
            'pending_count':       all_qs.filter(status='pending').count(),
            'approved_count':      all_qs.filter(status='approved').count(),
            'completed_count':     all_qs.filter(status='completed').count(),
            'self_applied_count':  all_qs.filter(self_applied=True).count(),
            'self_applied_pending': all_qs.filter(self_applied=True, status='pending').count(),
        }
        return render(request, self.template_name, context)


class AddResignationView(View):
    def get(self, request):
        org = _get_org(request)
        context = {
            'org': org,
            'members': member.objects.filter(org=org),
            'today': datetime.date.today().strftime('%Y-%m-%d'),
        }
        return render(request, 'admin/hrms/add_resignation.html', context)

    def post(self, request):
        org = _get_org(request)
        try:
            mem = get_object_or_404(member, pk=request.POST.get('member_id'), org=org)
            notice_days = int(request.POST.get('notice_period_days', 30))
            resignation_date = datetime.datetime.strptime(request.POST.get('resignation_date'), '%Y-%m-%d').date()
            last_working_day_str = request.POST.get('last_working_day')
            last_working_day = datetime.datetime.strptime(last_working_day_str, '%Y-%m-%d').date() if last_working_day_str else resignation_date + timedelta(days=notice_days)
            ResignationRecord.objects.create(
                org=org,
                member=mem,
                resignation_date=resignation_date,
                notice_period_days=notice_days,
                last_working_day=last_working_day,
                reason=request.POST.get('reason', ''),
            )
            messages.success(request, f"Resignation record created for {mem.name}.")
            return redirect('schooladmin:resignation_list')
        except Exception as e:
            messages.error(request, f"Error: {e}")
            return redirect('schooladmin:add_resignation')


def update_resignation_status(request, pk):
    org = _get_org(request)
    res = get_object_or_404(ResignationRecord, pk=pk, org=org)
    new_status = request.POST.get('status')
    if new_status:
        res.status = new_status
        res.exit_interview_note = request.POST.get('exit_interview_note', res.exit_interview_note or '')
        res.clearance_status = request.POST.get('clearance_status') == 'on'
        res.final_settlement_status = request.POST.get('final_settlement_status') == 'on'
        res.save()
        messages.success(request, "Resignation status updated.")
    return redirect('schooladmin:resignation_list')


# =============================================================
# HRMS EXTENDED - STAFF DOCUMENTS
# =============================================================

class StaffDocumentListView(View):
    template_name = 'admin/hrms/document_list.html'

    def get(self, request):
        org = _get_org(request)
        qs = StaffDocument.objects.filter(org=org).select_related('member').order_by('-uploaded_at')
        member_id = request.GET.get('member')
        if member_id:
            qs = qs.filter(member_id=member_id)
        context = {
            'org': org,
            'documents': qs,
            'members': member.objects.filter(org=org),
            'selected_member': member_id,
        }
        return render(request, self.template_name, context)


class UploadStaffDocumentView(View):
    def get(self, request):
        org = _get_org(request)
        context = {
            'org': org,
            'members': member.objects.filter(org=org),
            'doc_types': StaffDocument.DOC_TYPE_CHOICES,
        }
        return render(request, 'admin/hrms/upload_document.html', context)

    def post(self, request):
        org = _get_org(request)
        try:
            mem = get_object_or_404(member, pk=request.POST.get('member_id'), org=org)
            file = request.FILES.get('file')
            if not file:
                messages.error(request, "Please select a file.")
                return redirect('schooladmin:upload_document')
            expiry_str = request.POST.get('expiry_date')
            StaffDocument.objects.create(
                org=org,
                member=mem,
                document_type=request.POST.get('document_type', 'other'),
                title=request.POST.get('title'),
                file=file,
                expiry_date=expiry_str if expiry_str else None,
            )
            messages.success(request, "Document uploaded successfully.")
            return redirect('schooladmin:document_list')
        except Exception as e:
            messages.error(request, f"Error: {e}")
            return redirect('schooladmin:upload_document')


def delete_document(request, pk):
    org = _get_org(request)
    doc = get_object_or_404(StaffDocument, pk=pk, org=org)
    doc.file.delete(save=False)
    doc.delete()
    messages.success(request, "Document deleted.")
    return redirect('schooladmin:document_list')


# =============================================================
# BRANCH MANAGEMENT
# =============================================================

class BranchListView(View):
    template_name = 'admin/branches/branch_list.html'

    def get(self, request):
        org = _get_org(request)
        branches = Branch.objects.filter(org=org).annotate(
            member_count=Count('members', filter=Q(members__status='active'))
        ).order_by('name')
        context = {'org': org, 'branches': branches}
        return render(request, self.template_name, context)

    def post(self, request):
        org = _get_org(request)
        action = request.POST.get('action')
        if action == 'add':
            name = request.POST.get('name', '').strip()
            code = request.POST.get('code', '').strip()
            if not name or not code:
                messages.error(request, "Name and code are required.")
            else:
                Branch.objects.get_or_create(org=org, code=code, defaults={
                    'name': name,
                    'address': request.POST.get('address', ''),
                    'phone': request.POST.get('phone', ''),
                    'email': request.POST.get('email', ''),
                })
                messages.success(request, f"Branch '{name}' added.")
        elif action == 'delete':
            Branch.objects.filter(pk=request.POST.get('branch_id'), org=org).delete()
            messages.success(request, "Branch deleted.")
        return redirect('schooladmin:branch_list')


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# NEW PHASE 2 VIEWS — Privilege, Billing, Absence Correction, Bulk Payslip
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

from handle.models import AbsenceCorrection, Bill, BillItem, PRIVILEGE_LEVEL_CHOICES
from school.email_utils import (
    send_welcome_email, send_leave_status_email, send_bill_email,
    send_result_email, send_resignation_status_email,
    send_payslip_email, send_complaint_update_email,
)

# ── Privilege Management ──────────────────────────────────────────────────────

class PrivilegeManageView(View):
    """Assign privilege levels to members."""
    template_name = 'admin/hrms/privilege_manage.html'

    def get(self, request):
        from django.core.paginator import Paginator
        org = _get_org(request)
        q = request.GET.get('q', '').strip()
        qs = member.objects.filter(org=org).order_by('name')
        if q:
            qs = qs.filter(name__icontains=q)
        paginator = Paginator(qs, 25)
        page_obj = paginator.get_page(request.GET.get('page'))
        return render(request, self.template_name, {
            'org': org,
            'members': page_obj,
            'page_obj': page_obj,
            'q': q,
            'privilege_choices': PRIVILEGE_LEVEL_CHOICES,
        })

    def post(self, request):
        org = _get_org(request)
        member_id = request.POST.get('member_id')
        privilege = request.POST.get('privilege')
        m = get_object_or_404(member, pk=member_id, org=org)
        m.privilege = int(privilege)
        m.save()
        messages.success(request, f"Privilege updated for {m.name}.")
        return redirect('schooladmin:privilege_manage')


# ── Absence Correction (Mark present-as-absent) ───────────────────────────────

class AbsenceCorrectionView(View):
    """Admin marks a member absent on a date where they have an incorrect present record."""
    template_name = 'admin/attendance/absence_correction.html'

    def get(self, request):
        org = _get_org(request)
        date_str = request.GET.get('date', timezone.localdate().strftime('%Y-%m-%d'))
        members_q = request.GET.get('q', '')
        members_qs = member.objects.filter(org=org)
        if members_q:
            members_qs = members_qs.filter(name__icontains=members_q)

        try:
            selected_date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            selected_date = timezone.localdate()

        present_ids = set(
            AttendanceRecord.objects.filter(org=org, scanned_time__date=selected_date)
            .values_list('mem_id', flat=True)
        )

        corrections = AbsenceCorrection.objects.filter(org=org).order_by('-corrected_at')[:30]

        return render(request, self.template_name, {
            'org': org,
            'selected_date': selected_date,
            'date_str': date_str,
            'members': members_qs,
            'present_ids': present_ids,
            'corrections': corrections,
            'q': members_q,
        })

    def post(self, request):
        org = _get_org(request)
        member_id = request.POST.get('member_id')
        date_str = request.POST.get('date')
        reason = request.POST.get('reason', '').strip()
        if not reason:
            messages.error(request, "Reason is required.")
            return redirect(f"{request.path}?date={date_str}")

        try:
            selected_date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            messages.error(request, "Invalid date.")
            return redirect('schooladmin:absence_correction')

        m = get_object_or_404(member, pk=member_id, org=org)
        records = AttendanceRecord.objects.filter(mem=m, org=org, scanned_time__date=selected_date)
        first_scan = records.first()
        original_time = first_scan.scanned_time if first_scan else None
        deleted = records.delete()[0]

        if deleted:
            AbsenceCorrection.objects.create(
                org=org, member=m, date=selected_date, reason=reason,
                corrected_by=request.user, original_scan_time=original_time,
            )
            messages.success(request, f"{m.name} marked absent on {selected_date}. Reason logged.")
        else:
            messages.warning(request, f"{m.name} had no attendance record on {selected_date}.")

        return redirect(f"{request.path}?date={date_str}")


# ── Bill Management ────────────────────────────────────────────────────────────

class BillListView(View):
    template_name = 'admin/billing/bill_list.html'

    def get(self, request):
        org = _get_org(request)
        bills = Bill.objects.filter(org=org).select_related('member').order_by('-issue_date')
        members_qs = member.objects.filter(org=org)
        status_filter = request.GET.get('status', '')
        member_filter = request.GET.get('member', '')
        if status_filter:
            bills = bills.filter(status=status_filter)
        if member_filter:
            bills = bills.filter(member_id=member_filter)
        total_billed = bills.aggregate(t=Sum('total_amount'))['t'] or 0
        total_paid = bills.aggregate(t=Sum('amount_paid'))['t'] or 0
        return render(request, self.template_name, {
            'org': org,
            'bills': bills,
            'members': members_qs,
            'status_choices': Bill.STATUS_CHOICES,
            'selected_status': status_filter,
            'selected_member': member_filter,
            'total_billed': total_billed,
            'total_paid': total_paid,
            'total_due': total_billed - total_paid,
        })


class CreateBillView(View):
    template_name = 'admin/billing/create_bill.html'

    def get(self, request):
        org = _get_org(request)
        return render(request, self.template_name, {
            'org': org,
            'members': member.objects.filter(org=org).order_by('name'),
        })

    def post(self, request):
        org = _get_org(request)
        member_id = request.POST.get('member_id')
        due_date = request.POST.get('due_date')
        remarks = request.POST.get('remarks', '')
        send_email = request.POST.get('send_email') == 'on'
        descriptions = request.POST.getlist('description')
        amounts = request.POST.getlist('amount')

        if not member_id or not due_date or not descriptions:
            messages.error(request, "Member, due date and at least one item are required.")
            return redirect('schooladmin:create_bill')

        m = get_object_or_404(member, pk=member_id, org=org)
        import random, string
        invoice_no = 'INV-' + ''.join(random.choices(string.digits, k=8))

        items = []
        total = Decimal('0')
        for desc, amt in zip(descriptions, amounts):
            desc = desc.strip()
            if desc and amt:
                try:
                    amt_d = Decimal(str(amt))
                    items.append({'desc': desc, 'amount': amt_d})
                    total += amt_d
                except Exception:
                    pass

        if not items:
            messages.error(request, "Add at least one valid line item.")
            return redirect('schooladmin:create_bill')

        bill = Bill.objects.create(
            org=org, member=m, invoice_number=invoice_no,
            due_date=due_date, total_amount=total, remarks=remarks,
        )
        for it in items:
            BillItem.objects.create(bill=bill, description=it['desc'], amount=it['amount'])

        if send_email and m.email:
            send_bill_email(
                email=m.email, name=m.name,
                invoice_number=invoice_no, total_amount=total,
                due_date=due_date, items=items, org_name=org.name, remarks=remarks,
            )

        messages.success(request, f"Bill {invoice_no} created for {m.name}.")
        return redirect('schooladmin:bill_list')


class BillDetailView(View):
    template_name = 'admin/billing/bill_detail.html'

    def get(self, request, pk):
        org = _get_org(request)
        bill = get_object_or_404(Bill, pk=pk, org=org)
        return render(request, self.template_name, {'org': org, 'bill': bill})

    def post(self, request, pk):
        org = _get_org(request)
        bill = get_object_or_404(Bill, pk=pk, org=org)
        action = request.POST.get('action')
        if action == 'update_payment':
            amount_paid = request.POST.get('amount_paid', '0')
            status = request.POST.get('status', bill.status)
            try:
                new_amount = Decimal(amount_paid)
                delta = new_amount - bill.amount_paid
                bill.amount_paid = new_amount
                bill.status = status
                bill.save()
                # Auto-log payment delta as Finance income
                if delta > 0:
                    bill_cat, _ = TransactionCategory.objects.get_or_create(
                        org=org, name='Bill Collection', transaction_type='income'
                    )
                    FinancialTransaction.objects.create(
                        org=org,
                        transaction_type='income',
                        title=f"Bill Payment — {bill.invoice_number} ({bill.member.name})",
                        amount=delta,
                        category=bill_cat,
                        reference_number=bill.invoice_number,
                        note=f"Auto-linked from invoice #{bill.invoice_number}",
                        created_by=request.user,
                    )
                messages.success(request, "Payment updated.")
            except Exception:
                messages.error(request, "Invalid amount.")
        elif action == 'resend_email':
            if bill.member.email:
                items = [{'desc': i.description, 'amount': i.amount} for i in bill.items.all()]
                send_bill_email(
                    email=bill.member.email, name=bill.member.name,
                    invoice_number=bill.invoice_number, total_amount=bill.total_amount,
                    due_date=bill.due_date, items=items, org_name=org.name, remarks=bill.remarks or '',
                )
                messages.success(request, f"Invoice emailed to {bill.member.email}.")
            else:
                messages.error(request, "Member has no email address on file.")
        return redirect('schooladmin:bill_detail', pk=pk)


def delete_bill(request, pk):
    org = _get_org(request)
    bill = get_object_or_404(Bill, pk=pk, org=org)
    bill.delete()
    messages.success(request, "Bill deleted.")
    return redirect('schooladmin:bill_list')


# ── Bulk Payslip ────────────────────────────────────────────────────────────────

class BulkPayslipView(View):
    template_name = 'admin/payroll/bulk_payslip.html'

    def get(self, request):
        org = _get_org(request)
        members_qs = member.objects.filter(org=org, salary_amount__gt=0).order_by('name')
        classifications = Classification.objects.filter(org=org)
        return render(request, self.template_name, {
            'org': org,
            'members': members_qs,
            'classifications': classifications,
        })

    def post(self, request):
        org = _get_org(request)
        member_ids = request.POST.getlist('member_ids')
        from_date_str = request.POST.get('from_date')
        to_date_str = request.POST.get('to_date')
        month_name = request.POST.get('month_name', '')
        send_emails = request.POST.get('send_email') == 'on'

        if not member_ids or not from_date_str or not to_date_str or not month_name:
            messages.error(request, "Please fill all required fields and select at least one member.")
            return redirect('schooladmin:bulk_payslip')

        try:
            from_date = datetime.datetime.strptime(from_date_str, '%Y-%m-%d').date()
            to_date = datetime.datetime.strptime(to_date_str, '%Y-%m-%d').date()
        except ValueError:
            messages.error(request, "Invalid date format.")
            return redirect('schooladmin:bulk_payslip')

        total_days = (to_date - from_date).days + 1
        policy = get_or_create_policy(org)
        generated = 0
        skipped = 0
        errors = 0

        for mid in member_ids:
            try:
                m = member.objects.get(pk=mid, org=org)
            except member.DoesNotExist:
                continue

            if PaySlip.objects.filter(member=m, org=org, from_date=from_date, to_date=to_date).exists():
                skipped += 1
                continue

            try:
                stats, _ = calculate_attendance_stats(m, from_date, to_date, org)
                comps = calculate_payroll_components(m, stats, org, policy, to_date)

                slip = PaySlip.objects.create(
                    member=m, org=org,
                    from_date=from_date, to_date=to_date, month_name=month_name,
                    total_days=stats['total_days'],
                    present_days=stats['days_present'],
                    paid_leaves=stats['days_paid_leave'],
                    holidays=stats['days_holiday'],
                    unpaid_absences=stats['days_unpaid_absent'],
                    salary_type=m.salary_type,
                    gross_salary=comps['gross_salary'],
                    allowance_total=comps['allowance_total'],
                    bonus_total=comps['bonus_total'],
                    advance_deduction=comps['advance_deduction'],
                    loan_deduction=comps['loan_deduction'],
                    other_deduction=comps['other_deduction'],
                    tax_deduction=comps['tax_amount'],
                    pf_employee=comps['pf_employee'],
                    pf_employer=comps['pf_employer'],
                    ssf_employee=comps['ssf_employee'],
                    ssf_employer=comps['ssf_employer'],
                    probation_adjustment=comps['probation_adjustment'],
                    net_payable=comps['net_payable'],
                    status='draft',
                )

                # PF / SSF records
                if slip.pf_employee or slip.pf_employer:
                    ProvidentFundRecord.objects.create(
                        org=org, member=m, payslip=slip, month_name=month_name or '',
                        employee_contribution=slip.pf_employee,
                        employer_contribution=slip.pf_employer,
                    )
                if slip.ssf_employee or slip.ssf_employer:
                    SocialSecurityFundRecord.objects.create(
                        org=org, member=m, payslip=slip, month_name=month_name or '',
                        employee_contribution=slip.ssf_employee,
                        employer_contribution=slip.ssf_employer,
                    )

                # Auto-log salary as finance expense
                sal_cat, _ = TransactionCategory.objects.get_or_create(
                    org=org, name='Salary Payment', transaction_type='expense'
                )
                FinancialTransaction.objects.create(
                    org=org, transaction_type='expense',
                    title=f"Salary — {m.name} ({month_name})",
                    amount=slip.net_payable,
                    category=sal_cat,
                    reference_number=str(slip.id),
                    note=f"Auto-linked from bulk payslip #{slip.id}",
                    created_by=request.user,
                )

                generated += 1

                if send_emails and m.email:
                    send_payslip_email(
                        email=m.email, name=m.name,
                        month_name=month_name, net_payable=comps['net_payable'],
                        org_name=org.name,
                        details={
                            'Gross Salary': f"Rs. {comps['gross_salary']}",
                            'Allowances': f"Rs. {comps['allowance_total']}",
                            'Deductions': f"Rs. {comps['advance_deduction'] + comps['loan_deduction']}",
                            'PF': f"Rs. {comps['pf_employee']}",
                            'Tax': f"Rs. {comps['tax_amount']}",
                            'Present Days': stats['days_present'],
                            'Total Days': stats['total_days'],
                        },
                    )

            except Exception as exc:
                errors += 1
                import traceback; traceback.print_exc()

        msg = f"Generated {generated} payslip(s). Skipped {skipped} (already exist)."
        if errors:
            msg += f" {errors} member(s) had errors — check terminal log."
        messages.success(request, msg)
        return redirect('schooladmin:bulk_payslip')


# ── Enhanced Leave Status (with email) ────────────────────────────────────────

def leave_status_with_email(request, id, status):
    org = _get_org(request)
    report = get_object_or_404(LeaveReport, pk=id)
    admin_remarks = request.POST.get('remarks', '') if request.method == 'POST' else ''

    if status == 'approved':
        report.approved = True
        report.rejected = False
    elif status == 'rejected':
        report.approved = False
        report.rejected = True
    report.seen = True
    report.save()

    if report.member and report.member.email:
        lt_name = report.leave_type.name if report.leave_type else 'Leave'
        send_leave_status_email(
            email=report.member.email,
            name=report.member.name,
            status=status,
            leave_type=lt_name,
            start=str(report.gap_start),
            end=str(report.gap_end),
            remarks=admin_remarks,
            org_name=org.name,
        )

    messages.success(request, f"Leave {status}.")
    return redirect('schooladmin:leaveReportView')


# ── Complaint Detail (with email on status change) ────────────────────────────

class ComplaintDetailViewWithEmail(View):
    """Override the existing ComplaintDetailView to send emails on status change."""
    template_name = 'admin/complaints/detail.html'

    def get(self, request, pk):
        org = _get_org(request)
        complaint = get_object_or_404(Complaint, pk=pk, org=org)
        return render(request, self.template_name, {'org': org, 'complaint': complaint})

    def post(self, request, pk):
        org = _get_org(request)
        complaint = get_object_or_404(Complaint, pk=pk, org=org)
        old_status = complaint.status
        complaint.status = request.POST.get('status', complaint.status)
        complaint.admin_remarks = request.POST.get('admin_remarks', '')
        if complaint.status == 'resolved' and not complaint.resolution_date:
            from django.utils.timezone import now
            complaint.resolution_date = now().date()
        complaint.save()

        if complaint.status != old_status and complaint.filed_by.email:
            send_complaint_update_email(
                email=complaint.filed_by.email,
                name=complaint.filed_by.name,
                subject_text=complaint.subject,
                status=complaint.status,
                remarks=complaint.admin_remarks,
                org_name=org.name,
            )

        messages.success(request, "Complaint updated.")
        return redirect('schooladmin:complaint_detail', pk=pk)


# ── Resignation Update (with email) ───────────────────────────────────────────

def update_resignation_with_email(request, pk):
    org = _get_org(request)
    rec = get_object_or_404(ResignationRecord, pk=pk, org=org)
    old_status = rec.status
    if request.method == 'POST':
        rec.status = request.POST.get('status', rec.status)
        rec.exit_interview_note = request.POST.get('exit_interview_note', '')
        rec.clearance_status = request.POST.get('clearance_status') == 'on'
        rec.final_settlement_status = request.POST.get('final_settlement_status') == 'on'
        rec.save()

        if rec.status != old_status and rec.member.email:
            send_resignation_status_email(
                email=rec.member.email,
                name=rec.member.name,
                status=rec.status,
                last_working_day=str(rec.last_working_day) if rec.last_working_day else '',
                org_name=org.name,
            )
        messages.success(request, "Resignation record updated.")
    return redirect('schooladmin:resignation_list')


# ── Result Publish (with email) ───────────────────────────────────────────────

def publish_exam_with_email(request, pk):
    org = _get_org(request)
    exam = get_object_or_404(ExamTerm, pk=pk, org=org)
    exam.is_published = not exam.is_published
    exam.save()

    if exam.is_published:
        results = ResultRecord.objects.filter(exam=exam).select_related('student', 'subject')
        student_map = {}
        for r in results:
            sid = r.student_id
            if sid not in student_map:
                student_map[sid] = {'member': r.student, 'results': []}
            student_map[sid]['results'].append({
                'subject': r.subject.name,
                'marks': r.obtained_marks,
                'full': r.subject.full_marks,
                'passed': r.is_passed,
            })
        for sid, data in student_map.items():
            m = data['member']
            if m.email:
                send_result_email(
                    email=m.email, name=m.name,
                    exam_name=exam.name, results=data['results'], org_name=org.name,
                )
        messages.success(request, f"Exam published and emails sent to {len(student_map)} student(s).")
    else:
        messages.success(request, "Exam unpublished.")

    return redirect('schooladmin:exam_terms')


# ── Super Admin: Cross-Org Attendance Report & Date-Range Delete ──────────────

class SuperAttendanceReportView(View):
    """Super admin can view and delete attendance records by org + date range."""
    template_name = 'super_admin/attendance_report.html'

    def get(self, request):
        from management.models import Organization
        orgs = Organization.objects.all().order_by('name')
        selected_org = request.GET.get('org')
        from_date = request.GET.get('from_date', '')
        to_date = request.GET.get('to_date', '')
        records = AttendanceRecord.objects.none()
        org_obj = None

        if selected_org:
            try:
                org_obj = Organization.objects.get(pk=selected_org)
                records = AttendanceRecord.objects.filter(org=org_obj).select_related('mem').order_by('-scanned_time')
                if from_date:
                    records = records.filter(scanned_time__date__gte=from_date)
                if to_date:
                    records = records.filter(scanned_time__date__lte=to_date)
            except Organization.DoesNotExist:
                pass

        return render(request, self.template_name, {
            'orgs': orgs,
            'records': records[:500],
            'total_records': records.count() if org_obj else 0,
            'selected_org': selected_org,
            'org_obj': org_obj,
            'from_date': from_date,
            'to_date': to_date,
        })

    def post(self, request):
        selected_org = request.POST.get('org')
        from_date = request.POST.get('from_date')
        to_date = request.POST.get('to_date')
        confirm = request.POST.get('confirm') == 'yes'

        if not confirm:
            messages.error(request, "Please check the confirmation box before deleting.")
            return redirect(f"/superadmin/attendance-report/?org={selected_org}&from_date={from_date}&to_date={to_date}")

        try:
            org_obj = Organization.objects.get(pk=selected_org)
            qs = AttendanceRecord.objects.filter(org=org_obj)
            if from_date:
                qs = qs.filter(scanned_time__date__gte=from_date)
            if to_date:
                qs = qs.filter(scanned_time__date__lte=to_date)
            count = qs.count()
            qs.delete()
            messages.success(request, f"Deleted {count} attendance records from {org_obj.name}.")
        except Exception as e:
            messages.error(request, f"Error: {e}")

        return redirect('superadmin:attendance_report')



# ============================================================
# TASK MANAGEMENT — Admin Views
# ============================================================

from handle.models import Task, TaskInstance, TaskUpdateLog, TaskAttachment
from school.email_utils import (
    send_task_assigned_email, send_task_completed_email,
    send_task_overdue_email, send_task_approval_email,
)


def _task_org(request):
    if request.user.user_type == "2":
        return request.user.schooladmin.org
    if request.user.user_type == "3":
        return request.user.staff.org
    return None


class TaskDashboardView(AdminRequiredMixin, LoginRequiredMixin, View):
    template_name = 'admin/tasks/dashboard.html'

    def get(self, request):
        org = _task_org(request)
        today = datetime.date.today()

        # Auto-refresh overdue statuses
        stale = TaskInstance.objects.filter(
            task__org=org, due_date__lt=today, status__in=['pending', 'in_progress']
        )
        for inst in stale:
            inst.refresh_overdue_status()

        all_inst = TaskInstance.objects.filter(task__org=org)
        total = all_inst.count()
        pending = all_inst.filter(status='pending').count()
        in_progress = all_inst.filter(status='in_progress').count()
        completed = all_inst.filter(status='completed').count()
        not_completed = all_inst.filter(status='not_completed').count()
        overdue = all_inst.filter(status='overdue').count()
        missed = all_inst.filter(status='missed_absence').count()
        rework = all_inst.filter(status='rework_required').count()
        pending_approval = all_inst.filter(approval_status='pending_approval').count()

        today_tasks = all_inst.filter(due_date=today).select_related('task', 'assigned_member')
        urgent_tasks = all_inst.filter(
            task__priority='urgent', status__in=['pending', 'in_progress', 'overdue']
        ).select_related('task', 'assigned_member')[:10]

        # Staff-wise progress
        from django.db.models import Count, Case, When, IntegerField
        staff_stats = (
            all_inst
            .values('assigned_member__name', 'assigned_member__id')
            .annotate(
                total=Count('id'),
                done=Count(Case(When(status='completed', then=1), output_field=IntegerField())),
                pending_c=Count(Case(When(status='pending', then=1), output_field=IntegerField())),
                overdue_c=Count(Case(When(status__in=['overdue', 'missed_absence'], then=1), output_field=IntegerField())),
            )
            .order_by('-total')[:10]
        )

        # Priority breakdown
        priority_stats = (
            TaskInstance.objects.filter(task__org=org)
            .values('task__priority')
            .annotate(count=Count('id'))
        )

        ctx = dict(
            org=org, today=today,
            total=total, pending=pending, in_progress=in_progress,
            completed=completed, not_completed=not_completed,
            overdue=overdue, missed=missed, rework=rework,
            pending_approval=pending_approval,
            today_tasks=today_tasks,
            urgent_tasks=urgent_tasks,
            staff_stats=staff_stats,
            priority_stats=priority_stats,
        )
        return render(request, self.template_name, ctx)


class TaskListView(AdminRequiredMixin, LoginRequiredMixin, View):
    template_name = 'admin/tasks/task_list.html'

    def get(self, request):
        org = _task_org(request)
        today = datetime.date.today()
        tasks = Task.objects.filter(org=org, is_active=True).prefetch_related('assigned_to', 'instances')

        # Filters
        status_f = request.GET.get('status', '')
        priority_f = request.GET.get('priority', '')
        member_id = request.GET.get('member', '')
        task_type_f = request.GET.get('task_type', '')
        from_date = request.GET.get('from_date', '')
        to_date = request.GET.get('to_date', '')

        inst_qs = TaskInstance.objects.filter(task__org=org)
        if status_f:
            inst_qs = inst_qs.filter(status=status_f)
        if priority_f:
            inst_qs = inst_qs.filter(task__priority=priority_f)
        if member_id:
            inst_qs = inst_qs.filter(assigned_member_id=member_id)
        if task_type_f:
            inst_qs = inst_qs.filter(task__task_type=task_type_f)
        if from_date:
            inst_qs = inst_qs.filter(due_date__gte=from_date)
        if to_date:
            inst_qs = inst_qs.filter(due_date__lte=to_date)

        inst_qs = inst_qs.select_related('task', 'assigned_member').order_by('-due_date')[:200]

        members = member.objects.filter(org=org, status='active').order_by('name')
        ctx = dict(
            org=org, today=today,
            instances=inst_qs, members=members,
            status_choices=TaskInstance.STATUS_CHOICES,
            priority_choices=Task.PRIORITY_CHOICES,
            type_choices=Task.TASK_TYPE_CHOICES,
            filters=dict(status=status_f, priority=priority_f, member=member_id,
                         task_type=task_type_f, from_date=from_date, to_date=to_date),
        )
        return render(request, self.template_name, ctx)


class CreateTaskView(AdminRequiredMixin, LoginRequiredMixin, View):
    template_name = 'admin/tasks/create_task.html'

    def get(self, request):
        org = _task_org(request)
        members = member.objects.filter(org=org, status='active').order_by('name')
        branches = Branch.objects.filter(org=org)
        ctx = dict(
            org=org, members=members, branches=branches,
            priority_choices=Task.PRIORITY_CHOICES,
            type_choices=Task.TASK_TYPE_CHOICES,
            today=datetime.date.today(),
        )
        return render(request, self.template_name, ctx)

    def post(self, request):
        org = _task_org(request)
        title = request.POST.get('title', '').strip()
        description = request.POST.get('description', '')
        priority = request.POST.get('priority', 'medium')
        task_type = request.POST.get('task_type', 'one_time')
        start_date = request.POST.get('start_date')
        due_date = request.POST.get('due_date')
        due_time = request.POST.get('due_time') or None
        branch_id = request.POST.get('branch') or None
        notes = request.POST.get('notes', '')
        requires_approval = request.POST.get('requires_approval') == 'on'
        member_ids = request.POST.getlist('assigned_to')

        if not title or not start_date or not due_date or not member_ids:
            messages.error(request, "Title, dates, and at least one assignee are required.")
            return redirect('schooladmin:create_task')

        import datetime as _dt
        try:
            sd = _dt.date.fromisoformat(start_date)
            dd = _dt.date.fromisoformat(due_date)
        except ValueError:
            messages.error(request, "Invalid date format.")
            return redirect('schooladmin:create_task')

        if dd < sd:
            messages.error(request, "Due date must be on or after start date.")
            return redirect('schooladmin:create_task')

        task = Task.objects.create(
            org=org,
            branch_id=branch_id,
            title=title,
            description=description,
            priority=priority,
            task_type=task_type,
            start_date=sd,
            due_date=dd,
            due_time=due_time,
            notes=notes,
            requires_approval=requires_approval,
            created_by=request.user,
        )

        if 'attachment' in request.FILES:
            task.attachment = request.FILES['attachment']
            task.save(update_fields=['attachment'])

        assigned_members = member.objects.filter(id__in=member_ids, org=org)
        task.assigned_to.set(assigned_members)
        task.generate_instances()

        # Email notifications
        assigned_by = request.user.get_full_name() or request.user.username
        for m in assigned_members:
            if m.email:
                send_task_assigned_email(
                    m.email, m.name, task.title,
                    str(dd), priority, org.name, assigned_by
                )

        messages.success(request, f"Task '{title}' created and assigned to {assigned_members.count()} member(s).")
        return redirect('schooladmin:task_list')


class TaskDetailAdminView(AdminRequiredMixin, LoginRequiredMixin, View):
    template_name = 'admin/tasks/task_detail.html'

    def get(self, request, pk):
        org = _task_org(request)
        task = get_object_or_404(Task, pk=pk, org=org)
        instances = task.instances.select_related('assigned_member', 'approved_by').prefetch_related('update_logs', 'attachments').order_by('due_date', 'assigned_member__name')
        members = member.objects.filter(org=org, status='active').order_by('name')
        ctx = dict(org=org, task=task, instances=instances, members=members)
        return render(request, self.template_name, ctx)

    def post(self, request, pk):
        org = _task_org(request)
        task = get_object_or_404(Task, pk=pk, org=org)
        action = request.POST.get('action')

        if action == 'approve_instance':
            inst_id = request.POST.get('instance_id')
            inst = get_object_or_404(TaskInstance, pk=inst_id, task=task)
            inst.approval_status = 'approved'
            inst.status = 'completed'
            inst.approved_by = request.user
            inst.approved_at = timezone.now()
            inst.save()
            TaskUpdateLog.objects.create(instance=inst, changed_by=request.user, old_status='completed', new_status='completed', note='Admin approved completion.')
            if inst.assigned_member.email:
                send_task_approval_email(inst.assigned_member.email, inst.assigned_member.name, task.title, 'approved', '', org.name)
            messages.success(request, "Task completion approved.")

        elif action == 'reject_instance':
            inst_id = request.POST.get('instance_id')
            reason = request.POST.get('rejection_reason', '')
            inst = get_object_or_404(TaskInstance, pk=inst_id, task=task)
            old_status = inst.status
            inst.approval_status = 'rejected'
            inst.status = 'rework_required'
            inst.rejection_reason = reason
            inst.approved_by = request.user
            inst.approved_at = timezone.now()
            inst.save()
            TaskUpdateLog.objects.create(instance=inst, changed_by=request.user, old_status=old_status, new_status='rework_required', note=f'Rejected: {reason}')
            if inst.assigned_member.email:
                send_task_approval_email(inst.assigned_member.email, inst.assigned_member.name, task.title, 'rejected', reason, org.name)
            messages.success(request, "Task rejected and returned to staff.")

        elif action == 'reassign':
            inst_id = request.POST.get('instance_id')
            new_member_id = request.POST.get('new_member')
            inst = get_object_or_404(TaskInstance, pk=inst_id, task=task)
            new_m = get_object_or_404(member, pk=new_member_id, org=org)
            inst.assigned_member = new_m
            inst.status = 'pending'
            inst.completion_note = ''
            inst.save()
            task.assigned_to.add(new_m)
            if new_m.email:
                send_task_assigned_email(new_m.email, new_m.name, task.title, str(inst.due_date), task.priority, org.name, 'Admin (Reassigned)')
            messages.success(request, f"Task reassigned to {new_m.name}.")

        elif action == 'cancel_instance':
            inst_id = request.POST.get('instance_id')
            inst = get_object_or_404(TaskInstance, pk=inst_id, task=task)
            old = inst.status
            inst.status = 'cancelled'
            inst.save()
            TaskUpdateLog.objects.create(instance=inst, changed_by=request.user, old_status=old, new_status='cancelled', note='Cancelled by admin.')
            messages.success(request, "Task instance cancelled.")

        elif action == 'deactivate':
            task.is_active = False
            task.save(update_fields=['is_active'])
            messages.success(request, "Task deactivated.")
            return redirect('schooladmin:task_list')

        return redirect('schooladmin:task_detail', pk=pk)


class TaskReportView(AdminRequiredMixin, LoginRequiredMixin, View):
    template_name = 'admin/tasks/task_report.html'

    def get(self, request):
        org = _task_org(request)
        from_date = request.GET.get('from_date', '')
        to_date = request.GET.get('to_date', '')
        member_id = request.GET.get('member', '')
        status_f = request.GET.get('status', '')
        priority_f = request.GET.get('priority', '')
        task_type_f = request.GET.get('task_type', '')

        qs = TaskInstance.objects.filter(task__org=org).select_related('task', 'assigned_member', 'approved_by')

        if from_date:
            qs = qs.filter(due_date__gte=from_date)
        if to_date:
            qs = qs.filter(due_date__lte=to_date)
        if member_id:
            qs = qs.filter(assigned_member_id=member_id)
        if status_f:
            qs = qs.filter(status=status_f)
        if priority_f:
            qs = qs.filter(task__priority=priority_f)
        if task_type_f:
            qs = qs.filter(task__task_type=task_type_f)

        qs = qs.order_by('-due_date')[:500]

        members = member.objects.filter(org=org, status='active').order_by('name')
        ctx = dict(
            org=org, instances=qs, members=members,
            status_choices=TaskInstance.STATUS_CHOICES,
            priority_choices=Task.PRIORITY_CHOICES,
            type_choices=Task.TASK_TYPE_CHOICES,
            filters=dict(from_date=from_date, to_date=to_date, member=member_id,
                         status=status_f, priority=priority_f, task_type=task_type_f),
        )
        return render(request, self.template_name, ctx)

# ══════════════════════════════════════════════════════════════════════════════
# EXPORT HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _excel_response(filename):
    resp = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    resp['Content-Disposition'] = f'attachment; filename="{filename}"'
    return resp

def _style_header(ws, headers, fill_color='2563EB'):
    fill = PatternFill(start_color=fill_color, end_color=fill_color, fill_type='solid')
    font = Font(color='FFFFFF', bold=True)
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.fill = fill
        cell.font = font
        cell.alignment = Alignment(horizontal='center')
    ws.row_dimensions[1].height = 20

def _np_str(d):
    """Convert a date/datetime to Nepali BS string if possible."""
    try:
        if hasattr(d, 'date'):
            d = d.date()
        return str(nepali_datetime.date.from_datetime_date(d))
    except Exception:
        return str(d) if d else ''

def _org_from_req(request):
    if hasattr(request.user, 'schooladmin'):
        return request.user.schooladmin.org
    if hasattr(request.user, 'superadmin'):
        # superadmin can pass org_id param
        org_id = request.GET.get('org_id')
        if org_id:
            from management.models import Organization
            return Organization.objects.filter(pk=org_id).first()
    return None


# ── 1. ATTENDANCE EXPORT ──────────────────────────────────────────────────────

@login_required
def export_attendance(request):
    org = _org_from_req(request)
    if not org:
        return HttpResponse('Unauthorized', status=403)

    fmt = request.GET.get('fmt', 'excel')
    from_date = request.GET.get('from_date')
    to_date = request.GET.get('to_date')
    nepali_enabled = getattr(org, 'nepali_date', False)

    qs = AttendanceRecord.objects.filter(org=org).select_related('mem', 'mem__classification').order_by('scanned_time')
    if from_date:
        try:
            qs = qs.filter(scanned_time__date__gte=datetime.date.fromisoformat(from_date))
        except Exception:
            pass
    if to_date:
        try:
            qs = qs.filter(scanned_time__date__lte=datetime.date.fromisoformat(to_date))
        except Exception:
            pass

    headers = ['Member Name', 'Member Type', 'Class/Branch', 'Date (AD)', 'Date (BS)' if nepali_enabled else '', 'Check-in Time', 'Status']
    headers = [h for h in headers if h]

    if fmt == 'csv':
        resp = HttpResponse(content_type='text/csv')
        resp['Content-Disposition'] = 'attachment; filename="attendance_report.csv"'
        writer = csv.writer(resp)
        writer.writerow(headers)
        for r in qs:
            row = [
                r.mem.name if r.mem else '',
                r.mem.get_member_type_display() if r.mem else '',
                r.mem.classification.name if r.mem and r.mem.classification else '',
                r.scanned_time.date(),
            ]
            if nepali_enabled:
                row.append(_np_str(r.scanned_time.date()))
            row += [r.scanned_time.strftime('%H:%M:%S'), r.status or 'present']
            writer.writerow(row)
        return resp

    # Excel
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Attendance'
    _style_header(ws, headers)
    for ridx, r in enumerate(qs, 2):
        row = [
            r.mem.name if r.mem else '',
            r.mem.get_member_type_display() if r.mem else '',
            r.mem.classification.name if r.mem and r.mem.classification else '',
            str(r.scanned_time.date()),
        ]
        if nepali_enabled:
            row.append(_np_str(r.scanned_time.date()))
        row += [r.scanned_time.strftime('%H:%M:%S'), r.status or 'present']
        for cidx, val in enumerate(row, 1):
            ws.cell(row=ridx, column=cidx, value=val)

    ws.column_dimensions['A'].width = 25
    ws.column_dimensions['B'].width = 15
    ws.column_dimensions['C'].width = 20
    resp = _excel_response('attendance_report.xlsx')
    wb.save(resp)
    return resp


# ── 2. PAYSLIP EXPORT ────────────────────────────────────────────────────────

@login_required
def export_payslips(request):
    org = _org_from_req(request)
    if not org:
        return HttpResponse('Unauthorized', status=403)

    fmt = request.GET.get('fmt', 'excel')
    from_date = request.GET.get('from_date')
    to_date = request.GET.get('to_date')
    nepali_enabled = getattr(org, 'nepali_date', False)

    qs = PaySlip.objects.filter(org=org).select_related('member').order_by('-from_date')
    if from_date:
        try:
            qs = qs.filter(from_date__gte=from_date)
        except Exception:
            pass
    if to_date:
        try:
            qs = qs.filter(to_date__lte=to_date)
        except Exception:
            pass

    headers = ['Member', 'Period', 'Month', 'From (AD)', 'To (AD)']
    if nepali_enabled:
        headers += ['From (BS)', 'To (BS)']
    headers += ['Present Days', 'Gross Salary', 'Allowances', 'Deductions', 'Net Payable', 'Generated On']

    if fmt == 'csv':
        resp = HttpResponse(content_type='text/csv')
        resp['Content-Disposition'] = 'attachment; filename="payslips_report.csv"'
        writer = csv.writer(resp)
        writer.writerow(headers)
        for ps in qs:
            total_ded = float(ps.advance_deduction or 0) + float(ps.loan_deduction or 0) + float(ps.other_deduction or 0) + float(ps.tax_deduction or 0) + float(ps.pf_employee or 0) + float(ps.ssf_employee or 0)
            row = [ps.member.name, ps.month_name or '', ps.month_name or '', str(ps.from_date), str(ps.to_date)]
            if nepali_enabled:
                row += [_np_str(ps.from_date), _np_str(ps.to_date)]
            row += [ps.present_days, float(ps.gross_salary), float(ps.allowance_total), round(total_ded, 2), float(ps.net_payable), str(ps.generated_on.date() if ps.generated_on else '')]
            writer.writerow(row)
        return resp

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Payslips'
    _style_header(ws, headers, fill_color='16A34A')
    for ridx, ps in enumerate(qs, 2):
        total_ded = float(ps.advance_deduction or 0) + float(ps.loan_deduction or 0) + float(ps.other_deduction or 0) + float(ps.tax_deduction or 0) + float(ps.pf_employee or 0) + float(ps.ssf_employee or 0)
        row = [ps.member.name, ps.month_name or '', ps.month_name or '', str(ps.from_date), str(ps.to_date)]
        if nepali_enabled:
            row += [_np_str(ps.from_date), _np_str(ps.to_date)]
        row += [ps.present_days, float(ps.gross_salary), float(ps.allowance_total), round(total_ded, 2), float(ps.net_payable), str(ps.generated_on.date() if ps.generated_on else '')]
        for cidx, val in enumerate(row, 1):
            ws.cell(row=ridx, column=cidx, value=val)

    ws.column_dimensions['A'].width = 25
    resp = _excel_response('payslips_report.xlsx')
    wb.save(resp)
    return resp


# ── 3. STOCK EXPORT ──────────────────────────────────────────────────────────

@login_required
def export_stock(request):
    from handle.models import StockMovement, StockItem
    org = _org_from_req(request)
    if not org:
        return HttpResponse('Unauthorized', status=403)

    fmt = request.GET.get('fmt', 'excel')
    export_type = request.GET.get('type', 'items')  # items or movements
    nepali_enabled = getattr(org, 'nepali_date', False)

    if export_type == 'movements':
        qs = StockMovement.objects.filter(org=org).select_related('item', 'performed_by').order_by('-date')
        headers = ['Item', 'Type', 'Quantity', 'Unit', 'Date (AD)']
        if nepali_enabled:
            headers.append('Date (BS)')
        headers += ['Note', 'Performed By']

        if fmt == 'csv':
            resp = HttpResponse(content_type='text/csv')
            resp['Content-Disposition'] = 'attachment; filename="stock_movements.csv"'
            writer = csv.writer(resp)
            writer.writerow(headers)
            for m in qs:
                row = [m.item.name if m.item else '', m.movement_type, float(m.quantity), m.item.unit if m.item else '', str(m.date)]
                if nepali_enabled:
                    row.append(_np_str(m.date))
                row += [m.note or '', m.performed_by.get_full_name() if m.performed_by else '']
                writer.writerow(row)
            return resp

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = 'Stock Movements'
        _style_header(ws, headers, fill_color='D97706')
        for ridx, mv in enumerate(qs, 2):
            row = [mv.item.name if mv.item else '', mv.movement_type, float(mv.quantity), mv.item.unit if mv.item else '', str(mv.date)]
            if nepali_enabled:
                row.append(_np_str(mv.date))
            row += [mv.note or '', mv.performed_by.get_full_name() if mv.performed_by else '']
            for cidx, val in enumerate(row, 1):
                ws.cell(row=ridx, column=cidx, value=val)
    else:
        qs = StockItem.objects.filter(org=org).select_related('category').order_by('name')
        headers = ['Name', 'Category', 'Unit', 'Quantity', 'Low Stock Threshold', 'Unit Price', 'Status']

        if fmt == 'csv':
            resp = HttpResponse(content_type='text/csv')
            resp['Content-Disposition'] = 'attachment; filename="stock_items.csv"'
            writer = csv.writer(resp)
            writer.writerow(headers)
            for item in qs:
                writer.writerow([item.name, item.category.name if item.category else '', item.unit, float(item.quantity), float(item.low_stock_threshold), float(item.unit_price or 0), item.status])
            return resp

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = 'Stock Items'
        _style_header(ws, headers, fill_color='D97706')
        for ridx, item in enumerate(qs, 2):
            row = [item.name, item.category.name if item.category else '', item.unit, float(item.quantity), float(item.low_stock_threshold), float(item.unit_price or 0), item.status]
            for cidx, val in enumerate(row, 1):
                ws.cell(row=ridx, column=cidx, value=val)

    ws.column_dimensions['A'].width = 25
    resp = _excel_response(f'stock_{export_type}.xlsx')
    wb.save(resp)
    return resp


# ── 4. FINANCE EXPORT ────────────────────────────────────────────────────────

@login_required
def export_finance(request):
    from handle.models import FinancialTransaction
    org = _org_from_req(request)
    if not org:
        return HttpResponse('Unauthorized', status=403)

    fmt = request.GET.get('fmt', 'excel')
    txn_type = request.GET.get('type', 'all')  # income / expense / all
    from_date = request.GET.get('from_date')
    to_date = request.GET.get('to_date')
    nepali_enabled = getattr(org, 'nepali_date', False)

    qs = FinancialTransaction.objects.filter(org=org).order_by('-transaction_date')
    if txn_type in ('income', 'expense'):
        qs = qs.filter(transaction_type=txn_type)
    if from_date:
        try:
            qs = qs.filter(transaction_date__gte=from_date)
        except Exception:
            pass
    if to_date:
        try:
            qs = qs.filter(transaction_date__lte=to_date)
        except Exception:
            pass

    headers = ['Type', 'Category', 'Amount', 'Date (AD)']
    if nepali_enabled:
        headers.append('Date (BS)')
    headers += ['Description', 'Recorded By']

    if fmt == 'csv':
        resp = HttpResponse(content_type='text/csv')
        resp['Content-Disposition'] = 'attachment; filename="finance_report.csv"'
        writer = csv.writer(resp)
        writer.writerow(headers)
        for t in qs:
            row = [t.transaction_type, t.category.name if hasattr(t, 'category') and t.category else '', float(t.amount), str(t.transaction_date)]
            if nepali_enabled:
                row.append(_np_str(t.transaction_date))
            row += [t.description or '', t.created_by.get_full_name() if hasattr(t, 'created_by') and t.created_by else '']
            writer.writerow(row)
        return resp

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Finance'
    _style_header(ws, headers, fill_color='15803D')
    for ridx, t in enumerate(qs, 2):
        row = [t.transaction_type, t.category.name if hasattr(t, 'category') and t.category else '', float(t.amount), str(t.transaction_date)]
        if nepali_enabled:
            row.append(_np_str(t.transaction_date))
        row += [t.description or '', t.created_by.get_full_name() if hasattr(t, 'created_by') and t.created_by else '']
        for cidx, val in enumerate(row, 1):
            ws.cell(row=ridx, column=cidx, value=val)

    ws.column_dimensions['C'].width = 15
    resp = _excel_response('finance_report.xlsx')
    wb.save(resp)
    return resp


# ── 5. LEAVE EXPORT ──────────────────────────────────────────────────────────

@login_required
def export_leave(request):
    org = _org_from_req(request)
    if not org:
        return HttpResponse('Unauthorized', status=403)

    fmt = request.GET.get('fmt', 'excel')
    nepali_enabled = getattr(org, 'nepali_date', False)

    qs = LeaveReport.objects.filter(org=org).select_related('member', 'leave_type').order_by('-gap_start')

    headers = ['Member', 'Leave Type', 'From (AD)', 'To (AD)']
    if nepali_enabled:
        headers += ['From (BS)', 'To (BS)']
    headers += ['Days', 'Reason', 'Status']

    def leave_status(lr):
        if lr.approved:
            return 'Approved'
        if lr.rejected:
            return 'Rejected'
        return 'Pending'

    if fmt == 'csv':
        resp = HttpResponse(content_type='text/csv')
        resp['Content-Disposition'] = 'attachment; filename="leave_report.csv"'
        writer = csv.writer(resp)
        writer.writerow(headers)
        for lr in qs:
            row = [lr.member.name, lr.leave_type.name if lr.leave_type else 'General', str(lr.gap_start or ''), str(lr.gap_end or '')]
            if nepali_enabled:
                row += [_np_str(lr.gap_start) if lr.gap_start else '', _np_str(lr.gap_end) if lr.gap_end else '']
            row += [lr.total_leave_days(), lr.reason, leave_status(lr)]
            writer.writerow(row)
        return resp

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Leave Report'
    _style_header(ws, headers, fill_color='7C3AED')
    for ridx, lr in enumerate(qs, 2):
        row = [lr.member.name, lr.leave_type.name if lr.leave_type else 'General', str(lr.gap_start or ''), str(lr.gap_end or '')]
        if nepali_enabled:
            row += [_np_str(lr.gap_start) if lr.gap_start else '', _np_str(lr.gap_end) if lr.gap_end else '']
        row += [lr.total_leave_days(), lr.reason, leave_status(lr)]
        for cidx, val in enumerate(row, 1):
            ws.cell(row=ridx, column=cidx, value=val)

    ws.column_dimensions['A'].width = 25
    resp = _excel_response('leave_report.xlsx')
    wb.save(resp)
    return resp


# ── 6. MEMBER LIST EXPORT ────────────────────────────────────────────────────

@login_required
def export_members(request):
    org = _org_from_req(request)
    if not org:
        return HttpResponse('Unauthorized', status=403)

    fmt = request.GET.get('fmt', 'excel')
    nepali_enabled = getattr(org, 'nepali_date', False)

    qs = member.objects.filter(org=org).select_related('classification').order_by('name')

    headers = ['Name', 'Type', 'Class/Dept', 'Phone', 'Email', 'Status', 'Joined (AD)']
    if nepali_enabled:
        headers.append('Joined (BS)')
    headers.append('Salary')

    if fmt == 'csv':
        resp = HttpResponse(content_type='text/csv')
        resp['Content-Disposition'] = 'attachment; filename="members.csv"'
        writer = csv.writer(resp)
        writer.writerow(headers)
        for m in qs:
            row = [m.name, m.get_member_type_display(), m.classification.name if m.classification else '', m.number or '', m.email or '', m.status, str(m.created_at.date() if hasattr(m, 'created_at') and m.created_at else '')]
            if nepali_enabled:
                joined = m.created_at.date() if hasattr(m, 'created_at') and m.created_at else None
                row.append(_np_str(joined) if joined else '')
            row.append(float(m.salary_amount or 0))
            writer.writerow(row)
        return resp

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Members'
    _style_header(ws, headers, fill_color='0369A1')
    for ridx, m in enumerate(qs, 2):
        row = [m.name, m.get_member_type_display(), m.classification.name if m.classification else '', m.number or '', m.email or '', m.status, str(m.created_at.date() if hasattr(m, 'created_at') and m.created_at else '')]
        if nepali_enabled:
            joined = m.created_at.date() if hasattr(m, 'created_at') and m.created_at else None
            row.append(_np_str(joined) if joined else '')
        row.append(float(m.salary_amount or 0))
        for cidx, val in enumerate(row, 1):
            ws.cell(row=ridx, column=cidx, value=val)

    for col in ['A', 'D', 'E']:
        ws.column_dimensions[col].width = 25
    resp = _excel_response('members.xlsx')
    wb.save(resp)
    return resp


# ── 7. TASK EXPORT ───────────────────────────────────────────────────────────

@login_required
def export_tasks(request):
    org = _task_org(request)
    if not org:
        return HttpResponse('Unauthorized', status=403)

    fmt = request.GET.get('fmt', 'excel')
    nepali_enabled = getattr(org, 'nepali_date', False)

    qs = TaskInstance.objects.filter(task__org=org).select_related('task', 'assigned_member').order_by('-due_date')

    headers = ['Task Title', 'Member', 'Priority', 'Type', 'Status', 'Due Date (AD)']
    if nepali_enabled:
        headers.append('Due Date (BS)')
    headers += ['Completed At', 'Note']

    if fmt == 'csv':
        resp = HttpResponse(content_type='text/csv')
        resp['Content-Disposition'] = 'attachment; filename="tasks_report.csv"'
        writer = csv.writer(resp)
        writer.writerow(headers)
        for ti in qs:
            row = [ti.task.title, ti.assigned_member.name if ti.assigned_member else '', ti.task.get_priority_display(), ti.task.get_task_type_display(), ti.get_status_display(), str(ti.due_date)]
            if nepali_enabled:
                row.append(_np_str(ti.due_date) if ti.due_date else '')
            row += [str(ti.completed_at.date() if ti.completed_at else ''), ti.completion_note or '']
            writer.writerow(row)
        return resp

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Tasks'
    _style_header(ws, headers, fill_color='6D28D9')
    for ridx, ti in enumerate(qs, 2):
        row = [ti.task.title, ti.assigned_member.name if ti.assigned_member else '', ti.task.get_priority_display(), ti.task.get_task_type_display(), ti.get_status_display(), str(ti.due_date)]
        if nepali_enabled:
            row.append(_np_str(ti.due_date) if ti.due_date else '')
        row += [str(ti.completed_at.date() if ti.completed_at else ''), ti.completion_note or '']
        for cidx, val in enumerate(row, 1):
            ws.cell(row=ridx, column=cidx, value=val)

    ws.column_dimensions['A'].width = 35
    ws.column_dimensions['B'].width = 25
    resp = _excel_response('tasks_report.xlsx')
    wb.save(resp)
    return resp


# ══════════════════════════════════════════════════════════════════════════════
# EXPORT HUB PAGE
# ══════════════════════════════════════════════════════════════════════════════

class ExportHubView(AdminRequiredMixin, View):
    template_name = 'admin/export_hub.html'

    def get(self, request):
        if hasattr(request.user, 'schooladmin'):
            org = request.user.schooladmin.org
        elif request.user.user_type == '1':
            from management.models import Organization
            orgs = Organization.objects.all()
            return render(request, self.template_name, {'orgs': orgs, 'org': None, 'nepali_enabled': False})
        else:
            return redirect('management:login')

        nepali_enabled = getattr(org, 'nepali_date', False)
        return render(request, self.template_name, {'org': org, 'nepali_enabled': nepali_enabled})


# ══════════════════════════════════════════════════════════════════════════════
# CALENDAR PAGE + API
# ══════════════════════════════════════════════════════════════════════════════

class CalendarView(AdminRequiredMixin, View):
    template_name = 'admin/calendar.html'

    def get(self, request):
        if hasattr(request.user, 'schooladmin'):
            org = request.user.schooladmin.org
        else:
            return redirect('management:login')
        nepali_enabled = getattr(org, 'nepali_date', False)
        return render(request, self.template_name, {'org': org, 'nepali_enabled': nepali_enabled})


@login_required
def api_calendar_events(request):
    """Return all events + holidays + occasions as FullCalendar JSON."""
    if hasattr(request.user, 'schooladmin'):
        org = request.user.schooladmin.org
    else:
        return JsonResponse([], safe=False)

    nepali_enabled = getattr(org, 'nepali_date', False)
    events = []

    # Handle holidays (management.Holiday)
    for h in Holiday.objects.filter(org=org):
        events.append({
            'id': f'holiday_{h.pk}',
            'title': h.holiday,
            'color': '#ef4444',
            'allDay': True,
            'extendedProps': {'type': 'holiday', 'pk': h.pk},
        })

    # Occasions (management.Occasion) have dates
    for oc in Occasion.objects.filter(org=org):
        item = {
            'id': f'occasion_{oc.pk}',
            'title': oc.name,
            'start': str(oc.date),
            'color': '#f59e0b',
            'allDay': True,
            'extendedProps': {'type': 'occasion', 'pk': oc.pk},
        }
        if oc.end_date:
            import datetime as _dt
            end = oc.end_date + _dt.timedelta(days=1)  # FullCalendar end is exclusive
            item['end'] = str(end)
        events.append(item)

    # Events (handle.Event)
    for ev in Event.objects.filter(org=org):
        color_map = {
            'sports': '#3b82f6', 'seminar': '#8b5cf6', 'meeting': '#06b6d4',
            'exam': '#ef4444', 'program': '#22c55e', 'holiday': '#f59e0b', 'other': '#6b7280',
        }
        import datetime as _dt
        events.append({
            'id': f'event_{ev.pk}',
            'title': ev.title,
            'start': str(ev.start_date),
            'end': str(ev.end_date + _dt.timedelta(days=1)),
            'color': color_map.get(ev.event_type, '#6b7280'),
            'allDay': True,
            'extendedProps': {'type': 'event', 'pk': ev.pk, 'event_type': ev.event_type, 'status': ev.status},
        })

    return JsonResponse(events, safe=False)


@login_required
def api_calendar_add(request):
    """Add a holiday, occasion, or event from calendar click."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    if hasattr(request.user, 'schooladmin'):
        org = request.user.schooladmin.org
    else:
        return JsonResponse({'error': 'Unauthorized'}, status=403)

    data = json.loads(request.body)
    item_type = data.get('type')
    title = data.get('title', '').strip()
    start = data.get('start')
    end = data.get('end') or start

    if not title or not start:
        return JsonResponse({'error': 'Title and date required'}, status=400)

    import datetime as _dt

    try:
        start_date = _dt.date.fromisoformat(start)
        end_date = _dt.date.fromisoformat(end) if end else start_date
    except Exception:
        return JsonResponse({'error': 'Invalid date'}, status=400)

    if item_type == 'holiday':
        h = Holiday.objects.create(org=org, holiday=title)
        return JsonResponse({'ok': True, 'id': f'holiday_{h.pk}'})

    elif item_type == 'occasion':
        oc = Occasion.objects.create(org=org, name=title, date=start_date, end_date=end_date if end_date != start_date else None)
        return JsonResponse({'ok': True, 'id': f'occasion_{oc.pk}'})

    elif item_type == 'event':
        event_type = data.get('event_type', 'other')
        ev = Event.objects.create(org=org, title=title, event_type=event_type, start_date=start_date, end_date=end_date, status='upcoming')
        return JsonResponse({'ok': True, 'id': f'event_{ev.pk}'})

    return JsonResponse({'error': 'Unknown type'}, status=400)


@login_required
def api_calendar_delete(request, item_type, pk):
    """Delete a holiday/occasion/event."""
    if hasattr(request.user, 'schooladmin'):
        org = request.user.schooladmin.org
    else:
        return JsonResponse({'error': 'Unauthorized'}, status=403)

    if item_type == 'holiday':
        Holiday.objects.filter(pk=pk, org=org).delete()
    elif item_type == 'occasion':
        Occasion.objects.filter(pk=pk, org=org).delete()
    elif item_type == 'event':
        Event.objects.filter(pk=pk, org=org).delete()
    else:
        return JsonResponse({'error': 'Unknown type'}, status=400)

    return JsonResponse({'ok': True})


# ── Full Member Profile ─────────────────────────────────────────────────────────

class MemberProfileView(AdminRequiredMixin, View):
    def get(self, request, pk):
        org = request.user.schooladmin.org
        mem = get_object_or_404(member, pk=pk, org=org)

        # ── Attendance stats ───────────────────────────────────────────────
        from collections import defaultdict
        records_qs = AttendanceRecord.objects.filter(mem=mem).order_by('scanned_time')
        daily = defaultdict(list)
        for r in records_qs:
            d = timezone.localtime(r.scanned_time).date()
            daily[d].append(timezone.localtime(r.scanned_time).time())

        total_present = len(daily)
        total_late_minutes = 0
        late_days = 0

        for date, times in daily.items():
            times_sorted = sorted(times)
            first_punch = times_sorted[0]
            if first_punch > mem.shift_start_time:
                import datetime as _dt
                diff = _dt.datetime.combine(date, first_punch) - _dt.datetime.combine(date, mem.shift_start_time)
                total_late_minutes += int(diff.total_seconds() / 60)
                late_days += 1

        late_hours = total_late_minutes // 60
        late_mins = total_late_minutes % 60

        # Heatmap – last 90 days
        import datetime as _dt
        today = _dt.date.today()
        heatmap = {}
        for i in range(89, -1, -1):
            d = today - _dt.timedelta(days=i)
            heatmap[d.isoformat()] = 'present' if d in daily else 'absent'

        # ── Leave ─────────────────────────────────────────────────────────
        leaves = LeaveReport.objects.filter(member=mem, org=org).order_by('-id')
        leave_approved = leaves.filter(approved=True).count()
        leave_pending = leaves.filter(approved=False, rejected=False).count()
        leave_rejected = leaves.filter(rejected=True).count()

        # ── Payslips ──────────────────────────────────────────────────────
        payslips = PaySlip.objects.filter(member=mem, org=org).order_by('-generated_on')
        total_net_paid = sum(p.net_payable for p in payslips)

        # ── Tasks ─────────────────────────────────────────────────────────
        from handle.models import TaskInstance
        task_instances = TaskInstance.objects.filter(assigned_member=mem).select_related('task').order_by('-due_date')
        task_total    = task_instances.count()
        task_completed = task_instances.filter(status='completed').count()
        task_pending  = task_instances.filter(status__in=['pending', 'in_progress']).count()
        task_overdue  = task_instances.filter(status='overdue').count()
        task_missed   = task_instances.filter(status='missed_absence').count()
        task_on_time_pct = round(task_completed / task_total * 100) if task_total else 0

        # ── Complaints ────────────────────────────────────────────────────
        complaints = Complaint.objects.filter(filed_by=mem, org=org).order_by('-created_at')
        complaint_pending  = complaints.filter(status='pending').count()
        complaint_resolved = complaints.filter(status='resolved').count()

        # ── Bills ─────────────────────────────────────────────────────────
        bills = Bill.objects.filter(member=mem, org=org).order_by('-issue_date')
        total_billed = sum(b.total_amount for b in bills)
        total_paid   = sum(b.amount_paid for b in bills)
        total_due    = total_billed - total_paid

        # ── Academic Results ───────────────────────────────────────────────
        results = ResultRecord.objects.filter(student=mem).select_related('exam', 'subject').order_by('-exam__id')

        # ── HRMS ──────────────────────────────────────────────────────────
        resignation = mem.resignations.first()
        documents   = mem.documents.all().order_by('-id')

        # ── Absence Corrections ───────────────────────────────────────────
        corrections_qs = AbsenceCorrection.objects.filter(member=mem, org=org).order_by('-date')
        corrections_count = corrections_qs.count()
        corrections = corrections_qs[:30]

        # ── Payroll Adjustments (allowances / advances / loans) ───────────
        adjustments_active = PayrollAdjustment.objects.filter(
            org=org, member=mem, status='active'
        ).order_by('-effective_date')
        adjustments_applied = PayrollAdjustment.objects.filter(
            org=org, member=mem, status='applied'
        ).order_by('-effective_date')[:10]
        adj_allowance_total = sum(a.amount for a in adjustments_active if a.adjustment_type == 'allowance')
        adj_advance_total   = sum(a.amount for a in adjustments_active if a.adjustment_type == 'advance')
        adj_loan_total      = sum(a.amount for a in adjustments_active if a.adjustment_type == 'loan')

        nepali_enabled = org.nepali_date

        ctx = {
            'mem': mem,
            'org': org,
            'total_present': total_present,
            'late_days': late_days,
            'late_hours': late_hours,
            'late_mins': late_mins,
            'heatmap_json': json.dumps(heatmap),
            'leaves': leaves[:30],
            'leave_approved': leave_approved,
            'leave_pending': leave_pending,
            'leave_rejected': leave_rejected,
            'payslips': payslips,
            'total_net_paid': total_net_paid,
            'task_instances': task_instances[:30],
            'task_total': task_total,
            'task_completed': task_completed,
            'task_pending': task_pending,
            'task_overdue': task_overdue,
            'task_missed': task_missed,
            'task_on_time_pct': task_on_time_pct,
            'complaints': complaints,
            'complaint_pending': complaint_pending,
            'complaint_resolved': complaint_resolved,
            'bills': bills,
            'total_billed': total_billed,
            'total_paid': total_paid,
            'total_due': total_due,
            'results': results,
            'resignation': resignation,
            'documents': documents,
            'corrections': corrections,
            'corrections_count': corrections_count,
            'adjustments_active': adjustments_active,
            'adjustments_applied': adjustments_applied,
            'adj_allowance_total': adj_allowance_total,
            'adj_advance_total': adj_advance_total,
            'adj_loan_total': adj_loan_total,
            'nepali_enabled': nepali_enabled,
            'today': _dt.date.today().strftime('%Y-%m-%d'),
        }
        return render(request, 'admin/member_profile.html', ctx)

    def post(self, request, pk):
        org = request.user.schooladmin.org
        mem = get_object_or_404(member, pk=pk, org=org)
        action = request.POST.get('action')

        if action == 'add_adjustment':
            adj_type  = request.POST.get('adjustment_type', '')
            title     = request.POST.get('title', '').strip()
            amount    = request.POST.get('amount', '0')
            eff_date  = request.POST.get('effective_date') or timezone.localdate()
            notes     = request.POST.get('notes', '')
            if title and adj_type:
                try:
                    PayrollAdjustment.objects.create(
                        org=org, member=mem,
                        adjustment_type=adj_type,
                        title=title,
                        amount=Decimal(str(amount)),
                        effective_date=eff_date,
                        notes=notes,
                        created_by=request.user,
                        status='active',
                    )
                    messages.success(request, f"{title} added to {mem.name}'s adjustments.")
                except Exception as e:
                    messages.error(request, f"Error: {e}")
            else:
                messages.error(request, "Title and type are required.")

        elif action == 'cancel_adjustment':
            adj_pk = request.POST.get('adj_pk')
            PayrollAdjustment.objects.filter(pk=adj_pk, org=org, member=mem).update(status='cancelled')
            messages.success(request, "Adjustment cancelled.")

        return redirect('schooladmin:member_profile', pk=pk)


# ── Advance Salary ─────────────────────────────────────────────────────────────

from handle.models import AdvanceSalary


class AdvanceSalaryView(AdminRequiredMixin, View):
    template_name = 'admin/payroll/advance_salary.html'

    def get(self, request):
        org = _get_org(request)
        advances = AdvanceSalary.objects.filter(org=org).select_related('member', 'approved_by').order_by('-created_at')
        members_qs = member.objects.filter(org=org, salary_amount__gt=0).order_by('name')
        return render(request, self.template_name, {
            'org': org,
            'advances': advances,
            'members': members_qs,
            'today': datetime.date.today().strftime('%Y-%m-%d'),
        })

    def post(self, request):
        org = _get_org(request)
        action = request.POST.get('action')

        if action == 'create':
            member_id = request.POST.get('member_id')
            total_amount = request.POST.get('total_amount')
            num_installments = int(request.POST.get('num_installments', 1))
            purpose = request.POST.get('purpose', '')
            effective_date = request.POST.get('effective_date') or datetime.date.today()
            notes = request.POST.get('notes', '')
            try:
                mem = get_object_or_404(member, pk=member_id, org=org)
                total = Decimal(str(total_amount))
                installment = (total / num_installments).quantize(Decimal('0.01'))
                AdvanceSalary.objects.create(
                    org=org, member=mem,
                    total_amount=total,
                    num_installments=num_installments,
                    installment_amount=installment,
                    remaining_balance=total,
                    purpose=purpose,
                    approved_by=request.user,
                    effective_date=effective_date,
                    notes=notes,
                    status='active',
                )
                messages.success(request, f"Advance Rs. {total} approved for {mem.name}. Recovering Rs. {installment}/month over {num_installments} month(s).")
            except Exception as e:
                messages.error(request, f"Error: {e}")

        elif action == 'apply_installment':
            adv_pk = request.POST.get('adv_pk')
            adv = get_object_or_404(AdvanceSalary, pk=adv_pk, org=org)
            adv.apply_installment()
            messages.success(request, f"Installment of Rs. {adv.installment_amount} applied. Remaining: Rs. {adv.remaining_balance}")

        elif action == 'cancel':
            adv_pk = request.POST.get('adv_pk')
            AdvanceSalary.objects.filter(pk=adv_pk, org=org).update(status='cancelled')
            messages.success(request, "Advance salary cancelled.")

        return redirect('schooladmin:advance_salary')


# ── Appointment Management ─────────────────────────────────────────────────────

from management.models import AppointmentType, Appointment, CustomForm, FormField, FormSubmission, FieldResponse


class AppointmentTypeView(AdminRequiredMixin, View):
    def get(self, request):
        org = request.user.schooladmin.org
        types = AppointmentType.objects.filter(org=org)
        appts = Appointment.objects.filter(org=org).order_by('-date', '-time')
        return render(request, 'admin/appointments.html', {'org': org, 'types': types, 'appts': appts})

    def post(self, request):
        org = request.user.schooladmin.org
        action = request.POST.get('action')
        if action == 'create_type':
            AppointmentType.objects.create(
                org=org,
                name=request.POST.get('name', ''),
                description=request.POST.get('description', ''),
                duration_minutes=int(request.POST.get('duration_minutes', 30)),
                color=request.POST.get('color', '#e11d48'),
            )
            messages.success(request, 'Appointment type created.')
        elif action == 'delete_type':
            AppointmentType.objects.filter(pk=request.POST.get('pk'), org=org).delete()
            messages.success(request, 'Appointment type deleted.')
        elif action == 'update_status':
            appt = get_object_or_404(Appointment, pk=request.POST.get('pk'), org=org)
            appt.status = request.POST.get('status', 'confirmed')
            appt.admin_note = request.POST.get('admin_note', '')
            appt.save()
            messages.success(request, f'Appointment {appt.status}.')
        return redirect(request.path)


class FormBuilderView(AdminRequiredMixin, View):
    def get(self, request):
        org = request.user.schooladmin.org
        forms = CustomForm.objects.filter(org=org)
        return render(request, 'admin/form_builder_list.html', {'org': org, 'forms': forms})


class FormBuilderEditView(AdminRequiredMixin, View):
    def get(self, request, pk=None):
        org = request.user.schooladmin.org
        form_obj = get_object_or_404(CustomForm, pk=pk, org=org) if pk else None
        fields = form_obj.fields.all() if form_obj else []
        return render(request, 'admin/form_builder_edit.html', {'org': org, 'form_obj': form_obj, 'fields': fields})

    def post(self, request, pk=None):
        org = request.user.schooladmin.org
        action = request.POST.get('action', 'save_form')

        if action == 'save_form':
            if pk:
                form_obj = get_object_or_404(CustomForm, pk=pk, org=org)
            else:
                form_obj = CustomForm(org=org)
            form_obj.title = request.POST.get('title', 'Untitled Form')
            form_obj.description = request.POST.get('description', '')
            form_obj.is_active = request.POST.get('is_active') == 'on'
            form_obj.success_message = request.POST.get('success_message', 'Thank you for your submission!')
            form_obj.save()
            messages.success(request, 'Form saved.')
            return redirect('schooladmin:form_builder_edit', pk=form_obj.pk)

        elif action == 'add_field':
            form_obj = get_object_or_404(CustomForm, pk=pk, org=org)
            order = form_obj.fields.count()
            FormField.objects.create(
                form=form_obj,
                label=request.POST.get('label', 'Field'),
                field_type=request.POST.get('field_type', 'text'),
                placeholder=request.POST.get('placeholder', ''),
                options=request.POST.get('options', ''),
                required=request.POST.get('required') == 'on',
                order=order,
            )
            messages.success(request, 'Field added.')
            return redirect('schooladmin:form_builder_edit', pk=pk)

        elif action == 'delete_field':
            FormField.objects.filter(pk=request.POST.get('field_pk'), form__org=org).delete()
            messages.success(request, 'Field removed.')
            return redirect('schooladmin:form_builder_edit', pk=pk)

        elif action == 'delete_form':
            get_object_or_404(CustomForm, pk=pk, org=org).delete()
            messages.success(request, 'Form deleted.')
            return redirect('schooladmin:form_builder')

        return redirect(request.path)


class FormSubmissionsView(AdminRequiredMixin, View):
    def get(self, request, pk):
        org = request.user.schooladmin.org
        form_obj = get_object_or_404(CustomForm, pk=pk, org=org)
        submissions = form_obj.submissions.prefetch_related('responses').all()
        return render(request, 'admin/form_submissions.html', {'org': org, 'form_obj': form_obj, 'submissions': submissions})


# =============================================================
# CLASSIFICATION DETAIL HUB
# =============================================================

import calendar as _cal
from handle.models import Bill, BillItem, BillSendLog, ResultSendLog

def _money(value):
    try:
        return Decimal(str(value or 0)).quantize(Decimal("0.01"))
    except Exception:
        return Decimal("0.00")


def _student_subjects(mem):
    """Subjects/courses applicable to this student for result and fee use."""
    if not mem or not getattr(mem, 'org_id', None) or not getattr(mem, 'classification_id', None):
        return Subject.objects.none()
    qs = Subject.objects.filter(
        org_id=mem.org_id,
        classification_id=mem.classification_id,
        status='active',
    )
    if mem.section_id:
        return qs.filter(Q(section_id=mem.section_id) | Q(section__isnull=True)).order_by('name')
    return qs.filter(section__isnull=True).order_by('name')


def _fee_breakdown(mem):
    """Return a billing snapshot without mutating old bills."""
    billing_type = mem.billing_type or 'monthly_fee'
    base_amount = Decimal("0.00")
    course_fee = Decimal("0.00")
    subjects = []

    if billing_type == 'course_wise':
        subjects = list(_student_subjects(mem))
        course_fee = sum((_money(subject.monthly_fee) for subject in subjects), Decimal("0.00"))
    elif billing_type == 'scholarship':
        base_amount = Decimal("0.00")
    else:
        base_amount = _money(mem.monthly_fee)

    subtotal = base_amount + course_fee
    discount = Decimal("0.00")
    if mem.discount_type == 'fixed':
        discount = _money(mem.discount_amount)
    elif mem.discount_type == 'percentage':
        discount = (subtotal * _money(mem.discount_amount) / Decimal("100")).quantize(Decimal("0.01"))
    scholarship = _money(mem.scholarship_amount)
    final_amount = max(Decimal("0.00"), subtotal - discount - scholarship)
    if billing_type == 'scholarship' and not mem.monthly_fee:
        final_amount = Decimal("0.00")

    return {
        'billing_type': billing_type,
        'base_amount': base_amount,
        'course_fee_amount': course_fee,
        'discount_amount': discount,
        'scholarship_amount': scholarship,
        'final_amount': final_amount,
        'subjects': subjects,
    }


def _compute_final_fee(mem):
    """Return the final monthly payable for a member based on billing setup."""
    return _fee_breakdown(mem)['final_amount']


def _bill_due_queryset(org, mem, month=None, year=None):
    qs = Bill.objects.filter(org=org, member=mem).exclude(status='Cancelled')
    if month and year:
        qs = qs.exclude(billing_month=month, billing_year=year)
    return qs


def _bill_due_total(qs):
    totals = qs.aggregate(total=Sum('total_amount'), paid=Sum('amount_paid'))
    return max(Decimal("0.00"), _money(totals.get('total')) - _money(totals.get('paid')))


def _format_message_template(template, values):
    try:
        return template.format(**values)
    except Exception:
        return template


class ClassificationDetailView(AdminRequiredMixin, View):
    template_name = 'admin/classification/detail.html'

    def get(self, request, pk):
        org = _get_org(request)
        cls = get_object_or_404(Classification, pk=pk, org=org)
        tab = request.GET.get('tab', 'overview')
        section_filter = request.GET.get('section', '')
        search_q = request.GET.get('q', '').strip()

        sections = list(Section.objects.filter(org=org, classification=cls).order_by('name'))

        # Student queryset
        students_qs = member.objects.filter(org=org, classification=cls).select_related('section')
        if section_filter:
            students_qs = students_qs.filter(section_id=section_filter)
        if search_q:
            students_qs = students_qs.filter(
                Q(name__icontains=search_q) | Q(card__icontains=search_q) |
                Q(phone__icontains=search_q) | Q(guardian_name__icontains=search_q)
            )
        students = list(students_qs.order_by('name'))

        # Stats
        total_students  = member.objects.filter(org=org, classification=cls).count()
        active_students = member.objects.filter(org=org, classification=cls, status='active').count()

        # Billing stats
        today = timezone.localdate()
        bills_qs = Bill.objects.filter(org=org, classification=cls)
        expected_monthly = sum(_compute_final_fee(m) for m in member.objects.filter(org=org, classification=cls, status='active'))
        total_billed = _money(bills_qs.aggregate(s=Sum('total_amount'))['s'])
        total_paid   = _money(bills_qs.aggregate(s=Sum('amount_paid'))['s'])
        total_due    = max(Decimal("0.00"), total_billed - total_paid)
        monthly_fee_count = member.objects.filter(org=org, classification=cls, billing_type='monthly_fee').count()
        course_wise_count = member.objects.filter(org=org, classification=cls, billing_type='course_wise').count()
        custom_fee_count = member.objects.filter(org=org, classification=cls, billing_type='custom').count()
        scholarship_count = member.objects.filter(org=org, classification=cls, billing_type='scholarship').count()

        # Subject/course stats
        subjects_count = Subject.objects.filter(org=org, classification=cls, status='active').count()

        # Exam stats
        exams = ExamTerm.objects.filter(org=org, classification=cls).order_by('-start_date')
        published_exams = exams.filter(is_published=True).count()

        # Attendance summary (today present %)
        today_records = AttendanceRecord.objects.filter(
            org=org, mem__classification=cls, scanned_time__date=today
        ).values('mem_id').distinct().count()
        attend_pct = round(today_records / max(active_students, 1) * 100)

        # Per-student billing summary for table
        student_rows = []
        for s in students:
            final = _compute_final_fee(s)
            s_due = _bill_due_total(_bill_due_queryset(org, s))
            # Last result
            last_result = ResultRecord.objects.filter(student=s).select_related('exam').order_by('-exam__start_date').first()
            present_days = AttendanceRecord.objects.filter(
                org=org, mem=s, scanned_time__date__gte=today - timedelta(days=30)
            ).values('scanned_time__date').distinct().count()
            student_rows.append({
                'member': s,
                'final_fee': final,
                'due': s_due,
                'last_result': last_result,
                'attendance_pct': round(present_days / 30 * 100),
            })
        from management.models import CustomUser as _CU

        context = {
            'org': org,
            'cls': cls,
            'tab': tab,
            'sections': sections,
            'section_filter': section_filter,
            'search_q': search_q,
            'students': student_rows,
            'total_students': total_students,
            'active_students': active_students,
            'sections_count': len(sections),
            'subjects_count': subjects_count,
            'expected_monthly': expected_monthly,
            'total_billed': total_billed,
            'total_paid': total_paid,
            'total_due': total_due,
            'monthly_fee_count': monthly_fee_count,
            'course_wise_count': course_wise_count,
            'custom_fee_count': custom_fee_count,
            'scholarship_count': scholarship_count,
            'published_exams': published_exams,
            'exams': exams,
            'attend_pct': attend_pct,
            'today_present': today_records,
            # Subject list
            'subjects': Subject.objects.filter(org=org, classification=cls).select_related('section', 'teacher').order_by('name'),
            'teachers': _CU.objects.filter(Q(staff__org=org) | Q(schooladmin__org=org)).distinct(),
            'bill_send_logs': BillSendLog.objects.filter(bill__org=org, bill__classification=cls).select_related('bill', 'bill__member', 'sent_by')[:10],
            'result_send_logs': ResultSendLog.objects.filter(exam__org=org, member__classification=cls).select_related('exam', 'member', 'sent_by')[:10],
            'student_status_choices': member.STATUS_CHOICES,
            'billing_type_choices': member.BILLING_TYPE_CHOICES,
            'discount_type_choices': member.DISCOUNT_TYPE_CHOICES,
            'months': [(str(i), _cal.month_name[i]) for i in range(1, 13)],
            'current_month': str(today.month),
            'current_year': str(today.year),
        }
        return render(request, self.template_name, context)

    def post(self, request, pk):
        org = _get_org(request)
        cls = get_object_or_404(Classification, pk=pk, org=org)
        action = request.POST.get('action', '')

        if action == 'add_section':
            name = request.POST.get('name', '').strip()
            if name:
                Section.objects.get_or_create(
                    org=org,
                    classification=cls,
                    name=name,
                    defaults={
                        'status': request.POST.get('status', 'active'),
                        'code': request.POST.get('code', '').strip() or None,
                        'branch': cls.branch,
                    },
                )
                messages.success(request, f"Section '{name}' added.")
            else:
                messages.error(request, "Section name required.")

        elif action == 'edit_section':
            sid = request.POST.get('section_id')
            sec = get_object_or_404(Section, pk=sid, org=org, classification=cls)
            sec.name = request.POST.get('name', sec.name).strip() or sec.name
            sec.code = request.POST.get('code', '').strip() or None
            sec.status = request.POST.get('status', sec.status)
            sec.save(update_fields=['name', 'code', 'status', 'updated_at'])
            messages.success(request, "Section updated.")

        elif action == 'deactivate_section':
            sid = request.POST.get('section_id')
            Section.objects.filter(pk=sid, org=org, classification=cls).update(status='inactive')
            messages.success(request, "Section deactivated.")

        elif action == 'delete_section':
            sid = request.POST.get('section_id')
            Section.objects.filter(pk=sid, org=org, classification=cls).delete()
            messages.success(request, "Section deleted.")

        elif action == 'add_subject':
            from handle.models import Subject as _Subj
            name     = request.POST.get('name', '').strip()
            sec_id   = request.POST.get('section') or None
            full_m   = _money(request.POST.get('full_marks', 100))
            pass_m   = _money(request.POST.get('pass_marks', 40))
            monthly  = _money(request.POST.get('monthly_fee') or 0)
            one_time = _money(request.POST.get('one_time_fee') or 0)
            if not name:
                messages.error(request, "Subject name required.")
            elif full_m <= pass_m:
                messages.error(request, "Full marks must be greater than pass marks.")
            elif _Subj.objects.filter(org=org, classification=cls, section_id=sec_id, name=name).exists():
                messages.error(request, "Subject already exists.")
            else:
                _Subj.objects.create(
                    org=org, classification=cls, section_id=sec_id,
                    name=name, code=request.POST.get('code', '').strip() or None,
                    full_marks=full_m, pass_marks=pass_m,
                    monthly_fee=monthly, one_time_fee=one_time,
                    teacher_id=request.POST.get('teacher') or None,
                    status='active',
                )
                messages.success(request, f"Subject '{name}' added.")

        elif action == 'edit_subject':
            subj = get_object_or_404(Subject, pk=request.POST.get('subject_id'), org=org, classification=cls)
            subj.name = request.POST.get('name', subj.name).strip() or subj.name
            subj.code = request.POST.get('code', '').strip() or None
            subj.section_id = request.POST.get('section') or None
            subj.teacher_id = request.POST.get('teacher') or None
            subj.full_marks = _money(request.POST.get('full_marks', subj.full_marks))
            subj.pass_marks = _money(request.POST.get('pass_marks', subj.pass_marks))
            subj.monthly_fee = _money(request.POST.get('monthly_fee', subj.monthly_fee))
            subj.one_time_fee = _money(request.POST.get('one_time_fee', subj.one_time_fee))
            subj.status = request.POST.get('status', subj.status)
            subj.save()
            messages.success(request, "Course / Subject updated.")

        elif action == 'deactivate_subject':
            Subject.objects.filter(pk=request.POST.get('subject_id'), org=org, classification=cls).update(status='inactive')
            messages.success(request, "Course / Subject deactivated.")

        elif action == 'delete_subject':
            Subject.objects.filter(pk=request.POST.get('subject_id'), org=org, classification=cls).delete()
            messages.success(request, "Subject deleted.")

        return redirect(f"{reverse('schooladmin:classification_detail', args=[pk])}?tab={request.POST.get('return_tab','overview')}")


# =============================================================
# STUDENT / MEMBER MANAGEMENT (Add / Edit with billing)
# =============================================================

class StudentAddEditView(AdminRequiredMixin, View):
    template_name = 'admin/students/add_edit.html'

    def _get_context(self, org, instance=None):
        from management.models import CustomUser as _CU
        final_fee = _compute_final_fee(instance) if instance else Decimal("0.00")
        total_due = _bill_due_total(_bill_due_queryset(org, instance)) if instance else Decimal("0.00")
        return {
            'org': org,
            'instance': instance,
            'classifications': Classification.objects.filter(org=org),
            'sections': Section.objects.filter(org=org).select_related('classification'),
            'teachers': _CU.objects.filter(Q(staff__org=org) | Q(schooladmin__org=org)).distinct(),
            'status_choices': member.STATUS_CHOICES,
            'billing_type_choices': member.BILLING_TYPE_CHOICES,
            'discount_type_choices': member.DISCOUNT_TYPE_CHOICES,
            'final_fee': final_fee,
            'total_due': total_due,
        }

    def get(self, request, pk=None):
        org = _get_org(request)
        instance = get_object_or_404(member, pk=pk, org=org) if pk else None
        return render(request, self.template_name, self._get_context(org, instance))

    def post(self, request, pk=None):
        org = _get_org(request)
        instance = get_object_or_404(member, pk=pk, org=org) if pk else None

        name     = request.POST.get('name', '').strip()
        gender   = request.POST.get('gender', 'Male')
        def _int_or_none(value):
            digits = ''.join(ch for ch in str(value or '') if ch.isdigit())
            return int(digits) if digits else None

        phone    = request.POST.get('phone', '').strip() or None
        email    = request.POST.get('email', '').strip() or None
        address  = request.POST.get('address', '').strip() or None
        card     = request.POST.get('card', '').strip() or None
        cls_id   = request.POST.get('classification') or None
        sec_id   = request.POST.get('section') or None
        mtype    = request.POST.get('member_type', 'student')
        status   = request.POST.get('status', 'active')
        dob      = request.POST.get('date_of_birth') or None
        adm_date = request.POST.get('admission_date') or None

        # Guardian
        g_name  = request.POST.get('guardian_name', '').strip() or None
        g_phone = request.POST.get('guardian_phone', '').strip() or None
        g_email = request.POST.get('guardian_email', '').strip() or None

        # Billing
        billing_type    = request.POST.get('billing_type', 'monthly_fee')
        monthly_fee_val = request.POST.get('monthly_fee', '0').strip() or 0
        disc_type       = request.POST.get('discount_type') or None
        disc_amount     = request.POST.get('discount_amount', '0').strip() or 0
        schol_amount    = request.POST.get('scholarship_amount', '0').strip() or 0
        billing_start   = request.POST.get('billing_start_date') or None
        try:
            due_day = min(max(int(request.POST.get('due_day', '15') or 15), 1), 31)
        except (TypeError, ValueError):
            due_day = 15

        if not name:
            messages.error(request, "Name is required.")
            return render(request, self.template_name, self._get_context(org, instance))
        if email and member.objects.filter(email=email).exclude(pk=instance.pk if instance else None).exists():
            messages.error(request, "A member with this email already exists.")
            return render(request, self.template_name, self._get_context(org, instance))

        # Build or update
        if instance:
            mem = instance
        else:
            mem = member(org=org)

        mem.name          = name
        mem.gender        = gender
        mem.phone         = _int_or_none(phone)
        mem.email         = email
        mem.address       = address
        mem.card          = card
        mem.classification_id = cls_id
        mem.section_id    = sec_id
        mem.member_type   = mtype
        mem.status        = status
        mem.date_of_birth = dob
        mem.admission_date = adm_date
        mem.guardian_name  = g_name
        mem.guardian_phone = _int_or_none(g_phone)
        mem.guardian_email = g_email
        mem.billing_type      = billing_type
        mem.monthly_fee       = _money(monthly_fee_val)
        mem.discount_type     = disc_type
        mem.discount_amount   = _money(disc_amount)
        mem.scholarship_amount = _money(schol_amount)
        mem.billing_start_date = billing_start
        mem.due_day            = due_day
        # Compute final fee
        mem.final_monthly_fee = _compute_final_fee(mem)
        mem.save()
        messages.success(request, f"{'Updated' if pk else 'Added'} member '{mem.name}' successfully.")
        if cls_id:
            return redirect(f"{reverse('schooladmin:classification_detail', args=[cls_id])}?tab=students")
        return redirect('schooladmin:student_list')


class StudentListView(AdminRequiredMixin, View):
    """Global student list (all classifications)."""
    template_name = 'admin/students/list.html'

    def get(self, request):
        org = _get_org(request)
        cls_filter = request.GET.get('classification', '')
        sec_filter = request.GET.get('section', '')
        type_filter = request.GET.get('member_type', '')
        search_q = request.GET.get('q', '').strip()

        qs = member.objects.filter(org=org).select_related('classification', 'section').order_by('classification__name', 'name')
        if cls_filter:
            qs = qs.filter(classification_id=cls_filter)
        if sec_filter:
            qs = qs.filter(section_id=sec_filter)
        if type_filter:
            qs = qs.filter(member_type=type_filter)
        if search_q:
            qs = qs.filter(
                Q(name__icontains=search_q) | Q(card__icontains=search_q) |
                Q(phone__icontains=search_q) | Q(guardian_name__icontains=search_q)
            )

        rows = []
        for mem_obj in qs:
            rows.append({
                'member': mem_obj,
                'final_fee': _compute_final_fee(mem_obj),
                'due': _bill_due_total(_bill_due_queryset(org, mem_obj)),
            })

        context = {
            'org': org,
            'members': qs,
            'member_rows': rows,
            'classifications': Classification.objects.filter(org=org),
            'sections': Section.objects.filter(org=org),
            'cls_filter': cls_filter,
            'sec_filter': sec_filter,
            'type_filter': type_filter,
            'search_q': search_q,
            'total': len(rows),
        }
        return render(request, self.template_name, context)


# =============================================================
# BULK BILL GENERATION
# =============================================================

class BulkBillGenerateView(AdminRequiredMixin, View):
    template_name = 'admin/billing/bulk_generate.html'

    def get(self, request):
        org = _get_org(request)
        cls_id = request.GET.get('classification', '')
        sec_id = request.GET.get('section', '')
        month  = request.GET.get('month', '')
        year   = request.GET.get('year', str(timezone.localdate().year))
        billing_type = request.GET.get('billing_type', '')
        preview = request.GET.get('preview', '')

        classifications = Classification.objects.filter(org=org)
        sections = Section.objects.filter(org=org, classification_id=cls_id) if cls_id else Section.objects.none()

        preview_rows = []
        month_int = int(month) if month else None
        year_int  = int(year)  if year  else None

        if preview and cls_id and month_int and year_int:
            students = member.objects.filter(
                org=org, classification_id=cls_id, status='active'
            ).select_related('classification', 'section')
            if sec_id:
                students = students.filter(section_id=sec_id)
            if billing_type:
                students = students.filter(billing_type=billing_type)

            for s in students:
                breakdown = _fee_breakdown(s)
                # Check existing bill
                existing = Bill.objects.filter(
                    org=org, member=s, billing_month=month_int, billing_year=year_int
                ).first()
                prev_due = _bill_due_total(_bill_due_queryset(org, s, month_int, year_int))

                preview_rows.append({
                    'member': s,
                    'base_amount': breakdown['base_amount'],
                    'course_fee_amount': breakdown['course_fee_amount'],
                    'discount_amount': breakdown['discount_amount'],
                    'scholarship_amount': breakdown['scholarship_amount'],
                    'final_fee': breakdown['final_amount'],
                    'prev_due': prev_due,
                    'total_payable': breakdown['final_amount'] + prev_due,
                    'existing_bill': existing,
                    'existing_status': existing.status if existing else None,
                })

        context = {
            'org': org,
            'classifications': classifications,
            'sections': sections,
            'cls_id': cls_id,
            'sec_id': sec_id,
            'month': month,
            'year': year,
            'billing_type': billing_type,
            'billing_type_choices': member.BILLING_TYPE_CHOICES,
            'months': [(str(i), _cal.month_name[i]) for i in range(1, 13)],
            'years': [str(y) for y in range(timezone.localdate().year - 2, timezone.localdate().year + 2)],
            'preview_rows': preview_rows,
            'preview': bool(preview),
        }
        return render(request, self.template_name, context)

    def post(self, request):
        from django.db import transaction as _tx
        org = _get_org(request)
        cls_id    = request.POST.get('classification')
        sec_id    = request.POST.get('section') or None
        billing_type = request.POST.get('billing_type') or None
        month_int = int(request.POST.get('month', 0))
        year_int  = int(request.POST.get('year', 0))
        regenerate = request.POST.get('regenerate') == '1'

        if not cls_id or not month_int or not year_int:
            messages.error(request, "Classification, month and year are required.")
            return redirect('schooladmin:bulk_bill_generate')

        students = member.objects.filter(org=org, classification_id=cls_id, status='active')
        if sec_id:
            students = students.filter(section_id=sec_id)
        if billing_type:
            students = students.filter(billing_type=billing_type)

        generated = skipped = 0
        month_name = _cal.month_name[month_int]
        import uuid as _uuid

        with _tx.atomic():
            for s in students:
                existing = Bill.objects.filter(org=org, member=s, billing_month=month_int, billing_year=year_int).first()
                if existing and not regenerate:
                    skipped += 1
                    continue
                if existing and regenerate:
                    existing.delete()

                breakdown = _fee_breakdown(s)
                final_fee = breakdown['final_amount']
                prev_due = _bill_due_total(_bill_due_queryset(org, s))

                due_day_val = s.due_day or 15
                import calendar as cal2
                last_day = cal2.monthrange(year_int, month_int)[1]
                due_day_actual = min(due_day_val, last_day)
                import datetime as _dt
                due_date = _dt.date(year_int, month_int, due_day_actual)

                inv_num = f"BILL-{year_int}{month_int:02d}-{s.id}-{_uuid.uuid4().hex[:6].upper()}"
                bill = Bill.objects.create(
                    org=org,
                    member=s,
                    classification_id=cls_id,
                    section_id=s.section_id,
                    invoice_number=inv_num,
                    billing_month=month_int,
                    billing_year=year_int,
                    billing_type=breakdown['billing_type'],
                    base_amount=breakdown['base_amount'],
                    course_fee_amount=breakdown['course_fee_amount'],
                    previous_due=prev_due,
                    discount_amount=breakdown['discount_amount'],
                    scholarship_amount=breakdown['scholarship_amount'],
                    total_amount=final_fee + prev_due,
                    due_date=due_date,
                    generated_by=request.user,
                )
                # Bill items
                if breakdown['billing_type'] == 'course_wise':
                    for subject in breakdown['subjects']:
                        amount = _money(subject.monthly_fee)
                        if amount > 0:
                            BillItem.objects.create(
                                bill=bill,
                                subject=subject,
                                description=f"{subject.name} Course Fee - {month_name} {year_int}",
                                fee_type='course',
                                amount=amount,
                            )
                elif breakdown['base_amount'] > 0:
                    title = "Custom Fee" if breakdown['billing_type'] == 'custom' else "Monthly Fee"
                    BillItem.objects.create(
                        bill=bill,
                        description=f"{month_name} {year_int} {title}",
                        fee_type='monthly',
                        amount=breakdown['base_amount'],
                    )
                if breakdown['discount_amount'] > 0:
                    BillItem.objects.create(
                        bill=bill,
                        description="Discount",
                        fee_type='misc',
                        amount=0,
                        discount=breakdown['discount_amount'],
                    )
                if breakdown['scholarship_amount'] > 0:
                    BillItem.objects.create(
                        bill=bill,
                        description="Scholarship",
                        fee_type='misc',
                        amount=0,
                        discount=breakdown['scholarship_amount'],
                    )
                if prev_due > 0:
                    BillItem.objects.create(bill=bill, description="Previous Due", fee_type='misc', amount=prev_due)
                generated += 1

        messages.success(request, f"Generated {generated} bills. Skipped {skipped} (already exist).")
        send_url = f"{reverse('schooladmin:bulk_bill_send')}?classification={cls_id}&month={month_int}&year={year_int}"
        if sec_id:
            send_url += f"&section={sec_id}"
        return redirect(send_url)


# =============================================================
# BULK BILL SEND
# =============================================================

class BulkBillSendView(AdminRequiredMixin, View):
    template_name = 'admin/billing/bulk_send.html'

    def get(self, request):
        org = _get_org(request)
        cls_id   = request.GET.get('classification', '')
        sec_id   = request.GET.get('section', '')
        month    = request.GET.get('month', '')
        year     = request.GET.get('year', str(timezone.localdate().year))

        classifications = Classification.objects.filter(org=org)
        sections = Section.objects.filter(org=org, classification_id=cls_id) if cls_id else Section.objects.none()

        bills = Bill.objects.none()
        if cls_id and month and year:
            bills = Bill.objects.filter(
                org=org, classification_id=cls_id,
                billing_month=int(month), billing_year=int(year)
            ).select_related('member', 'member__section')
            if sec_id:
                bills = bills.filter(section_id=sec_id)
            bills = bills.order_by('member__name')

        context = {
            'org': org,
            'classifications': classifications,
            'sections': sections,
            'bills': bills,
            'cls_id': cls_id, 'sec_id': sec_id,
            'month': month, 'year': year,
            'months': [(str(i), _cal.month_name[i]) for i in range(1, 13)],
            'years': [str(y) for y in range(timezone.localdate().year - 2, timezone.localdate().year + 2)],
        }
        return render(request, self.template_name, context)

    def post(self, request):
        from django.db import transaction as _tx
        org      = _get_org(request)
        bill_ids = request.POST.getlist('bill_ids')
        method   = request.POST.get('send_method', 'email')
        custom_msg = request.POST.get('custom_message', '').strip()

        sent = failed = 0
        with _tx.atomic():
            for bid in bill_ids:
                try:
                    bill = Bill.objects.get(pk=bid, org=org)
                    mem  = bill.member
                    month_name = _cal.month_name[bill.billing_month] if bill.billing_month else "—"

                    guardian = mem.guardian_name or mem.name
                    values = {
                        'guardian_name': guardian,
                        'student_name': mem.name,
                        'month': f"{month_name} {bill.billing_year or ''}".strip(),
                        'total_payable': bill.total_amount,
                        'paid_amount': bill.amount_paid,
                        'due_amount': bill.balance_due,
                        'due_date': bill.due_date,
                        'organization_name': org.name,
                    }
                    default_msg = (
                        f"Dear {guardian},\n"
                        f"Bill for {mem.name} for {month_name} {bill.billing_year} has been generated.\n"
                        f"Total Amount: Rs. {bill.total_amount}\n"
                        f"Paid: Rs. {bill.amount_paid}\n"
                        f"Due: Rs. {bill.balance_due}\n"
                        f"Due Date: {bill.due_date}\n"
                        f"Please clear the payment on time.\n\n"
                        f"— {org.name}"
                    )
                    msg = _format_message_template(custom_msg, values) if custom_msg else default_msg

                    log_status = 'pending'
                    err_msg = None

                    if method == 'email':
                        email_target = mem.guardian_email or mem.email
                        if email_target:
                            try:
                                send_mail(
                                    subject=f"Fee Bill – {month_name} {bill.billing_year} | {org.name}",
                                    message=msg,
                                    from_email=settings.DEFAULT_FROM_EMAIL,
                                    recipient_list=[email_target],
                                    fail_silently=False,
                                )
                                log_status = 'sent'
                                bill.is_sent = True
                                bill.sent_at = timezone.now()
                                bill.sent_method = 'email'
                                bill.save(update_fields=['is_sent', 'sent_at', 'sent_method'])
                                sent += 1
                            except Exception as e:
                                log_status = 'failed'
                                err_msg = str(e)
                                failed += 1
                        else:
                            log_status = 'failed'
                            err_msg = 'No email address'
                            failed += 1
                    else:
                        # PDF / other: just mark as ready
                        log_status = 'pending'
                        bill.sent_method = method
                        bill.save(update_fields=['sent_method'])
                        sent += 1

                    BillSendLog.objects.create(
                        bill=bill,
                        sent_to_email=mem.guardian_email or mem.email,
                        sent_to_phone=str(mem.guardian_phone or mem.phone or ''),
                        sent_method=method,
                        message_body=msg,
                        status=log_status,
                        sent_by=request.user,
                        error_message=err_msg,
                    )
                except Exception:
                    failed += 1

        if method == 'email':
            messages.success(request, f"Sent {sent} emails. Failed: {failed}.")
        else:
            messages.success(request, f"Marked {sent} bills as ready-to-send via {method}.")
        return redirect(request.path + f"?classification={request.POST.get('cls_id','')}&month={request.POST.get('month','')}&year={request.POST.get('year','')}")


# =============================================================
# BULK RESULT SEND
# =============================================================

class BulkResultSendView(AdminRequiredMixin, View):
    template_name = 'admin/results/bulk_send.html'

    def _build_msg(self, org, mem, exam, total_obtained, total_full, pct, grade, passed):
        guardian = mem.guardian_name or mem.name
        return (
            f"Dear {guardian},\n"
            f"Result of {mem.name} for {exam.name} has been published.\n"
            f"Total: {total_obtained}/{total_full}\n"
            f"Percentage: {pct}%\n"
            f"Grade: {grade}\n"
            f"Status: {'Pass' if passed else 'Fail'}\n"
            f"Please check the full marksheet from the school portal.\n\n"
            f"— {org.name}"
        )

    def get(self, request):
        org    = _get_org(request)
        exam_id = request.GET.get('exam', '')
        cls_id  = request.GET.get('classification', '')
        sec_id  = request.GET.get('section', '')

        exams           = ExamTerm.objects.filter(org=org, is_published=True).order_by('-start_date')
        classifications = Classification.objects.filter(org=org)
        sections        = Section.objects.filter(org=org, classification_id=cls_id) if cls_id else Section.objects.none()

        preview_rows = []
        exam = None
        if exam_id and cls_id:
            exam = get_object_or_404(ExamTerm, pk=exam_id, org=org)
            students = member.objects.filter(org=org, classification_id=cls_id)
            if sec_id:
                students = students.filter(section_id=sec_id)

            for s in students:
                subjects = list(_student_subjects(s))
                recs = {r.subject_id: r for r in ResultRecord.objects.filter(student=s, exam=exam, subject__in=subjects).select_related('subject')}
                total_obt = float(sum(r.obtained_marks for r in recs.values() if not r.is_absent))
                total_full_m = float(sum(sub.full_marks for sub in subjects))
                pct = round(total_obt / max(total_full_m, 1) * 100, 1)
                passed = bool(subjects) and len(recs) >= len(subjects) and all(r.is_passed for r in recs.values())
                grade = _compute_grade(pct) if recs else '—'
                already_sent = ResultSendLog.objects.filter(exam=exam, member=s, status='sent').exists()
                preview_rows.append({
                    'member': s,
                    'total_obt': total_obt,
                    'total_full': total_full_m,
                    'pct': pct,
                    'grade': grade,
                    'passed': passed,
                    'has_results': bool(recs),
                    'is_complete': bool(subjects) and len(recs) >= len(subjects),
                    'subjects_count': len(subjects),
                    'already_sent': already_sent,
                })

        context = {
            'org': org,
            'exams': exams,
            'classifications': classifications,
            'sections': sections,
            'exam_id': exam_id,
            'cls_id': cls_id,
            'sec_id': sec_id,
            'exam': exam,
            'preview_rows': preview_rows,
        }
        return render(request, self.template_name, context)

    def post(self, request):
        from django.db import transaction as _tx
        org        = _get_org(request)
        exam_id    = request.POST.get('exam_id')
        cls_id     = request.POST.get('cls_id') or None
        member_ids = request.POST.getlist('member_ids')
        method     = request.POST.get('send_method', 'email')
        custom_msg = request.POST.get('custom_message', '').strip()

        exam = get_object_or_404(ExamTerm, pk=exam_id, org=org)

        sent = failed = 0
        with _tx.atomic():
            for mid in member_ids:
                try:
                    mem = member.objects.get(pk=mid, org=org)
                    subjects = list(_student_subjects(mem))
                    recs = list(ResultRecord.objects.filter(student=mem, exam=exam, subject__in=subjects))
                    total_obt  = float(sum(r.obtained_marks for r in recs if not r.is_absent))
                    total_full = float(sum(sub.full_marks for sub in subjects))
                    pct        = round(total_obt / max(total_full, 1) * 100, 1)
                    passed     = bool(subjects) and len(recs) >= len(subjects) and all(r.is_passed for r in recs)
                    grade      = _compute_grade(pct) if recs else 'NG'

                    values = {
                        'guardian_name': mem.guardian_name or mem.name,
                        'student_name': mem.name,
                        'exam_title': exam.name,
                        'obtained_marks': total_obt,
                        'full_marks': total_full,
                        'percentage': pct,
                        'grade': grade,
                        'pass_fail_status': 'Pass' if passed else 'Fail',
                        'organization_name': org.name,
                    }
                    msg = _format_message_template(custom_msg, values) if custom_msg else self._build_msg(org, mem, exam, total_obt, total_full, pct, grade, passed)
                    log_status = 'pending'
                    err_msg = None

                    if method == 'email':
                        email_target = mem.guardian_email or mem.email
                        if email_target:
                            try:
                                send_mail(
                                    subject=f"Result Published – {exam.name} | {org.name}",
                                    message=msg,
                                    from_email=settings.DEFAULT_FROM_EMAIL,
                                    recipient_list=[email_target],
                                    fail_silently=False,
                                )
                                log_status = 'sent'
                                sent += 1
                            except Exception as e:
                                log_status = 'failed'
                                err_msg = str(e)
                                failed += 1
                        else:
                            log_status = 'failed'
                            err_msg = 'No email address'
                            failed += 1
                    else:
                        log_status = 'pending'
                        sent += 1

                    ResultSendLog.objects.create(
                        exam=exam, member=mem,
                        sent_to_email=mem.guardian_email or mem.email or '',
                        sent_to_phone=str(mem.guardian_phone or mem.phone or ''),
                        sent_method=method,
                        message_body=msg,
                        status=log_status,
                        sent_by=request.user,
                        error_message=err_msg,
                    )
                except Exception:
                    failed += 1

        if method == 'email':
            messages.success(request, f"Sent {sent} result emails. Failed: {failed}.")
        else:
            messages.success(request, f"Logged {sent} result send records.")
        return redirect(request.path + f"?exam={exam_id}&classification={cls_id or ''}")


# =============================================================
# STUDENT PROFILE (upgraded)
# =============================================================

class StudentProfileView(AdminRequiredMixin, View):
    template_name = 'admin/students/profile.html'

    def get(self, request, pk):
        org = _get_org(request)
        mem = get_object_or_404(member, pk=pk, org=org)
        tab = request.GET.get('tab', 'overview')

        bills    = Bill.objects.filter(org=org, member=mem).prefetch_related('items').order_by('-issue_date')
        results  = ResultRecord.objects.filter(student=mem).select_related('exam', 'subject').order_by('-exam__start_date')
        exams    = ExamTerm.objects.filter(org=org, is_published=True)
        subjects = _student_subjects(mem)
        docs     = StaffDocument.objects.filter(org=org, member=mem)
        gaps     = AttendanceGap.objects.filter(org=org, member=mem).order_by('-date')[:10]

        # Finance summary
        total_billed = _money(bills.aggregate(s=Sum('total_amount'))['s'])
        total_paid   = _money(bills.aggregate(s=Sum('amount_paid'))['s'])
        total_due    = max(Decimal("0.00"), total_billed - total_paid)

        # Attendance summary (last 30 days)
        today = timezone.localdate()
        from_date = today - timedelta(days=30)
        att_count = AttendanceRecord.objects.filter(
            mem=mem, scanned_time__date__gte=from_date
        ).values('scanned_time__date').distinct().count()

        final_fee = _compute_final_fee(mem)

        context = {
            'org': org,
            'mem': mem,
            'tab': tab,
            'bills': bills,
            'results': results,
            'subjects': subjects,
            'docs': docs,
            'gaps': gaps,
            'final_fee': final_fee,
            'total_billed': total_billed,
            'total_paid': total_paid,
            'total_due': total_due,
            'att_count': att_count,
        }
        return render(request, self.template_name, context)


# ── Organization Feature Settings ────────────────────────────────────────────

# All boolean fields on Organization that can be toggled via the Feature Settings page
_ORG_FEATURE_FIELDS = [
    'rfid_based', 'qr_based', 'location_based', 'manual_attendance', 'auto_checkin',
    'course_based_attendance', 'nepali_date', 'mutifeature_enable',
    'feature_finance', 'feature_billing', 'feature_stock', 'feature_tasks',
    'feature_results', 'feature_hrms', 'feature_payroll', 'feature_complaints',
    'feature_events', 'feature_branches', 'feature_leave', 'feature_study_gap',
    'feature_bulk_export', 'feature_notifications', 'feature_courses',
    'feature_student_mgmt', 'feature_member_mgmt',
]


class OrgFeaturesView(AdminRequiredMixin, View):
    """Let schooladmin toggle which modules are active for their organization."""
    template_name = 'admin/org/features.html'

    def _get_org(self, request):
        if request.user.user_type == '2':
            return request.user.schooladmin.org
        return None

    def get(self, request):
        org = self._get_org(request)
        if org is None:
            messages.error(request, "No organization found.")
            return redirect('schooladmin:dashboard')
        return render(request, self.template_name, {'org': org})

    def post(self, request):
        org = self._get_org(request)
        if org is None:
            messages.error(request, "No organization found.")
            return redirect('schooladmin:dashboard')

        for field in _ORG_FEATURE_FIELDS:
            value = request.POST.get(field) == '1'
            setattr(org, field, value)

        # Dependency enforcement: disable dependent features when parent is off
        if not org.feature_courses:
            org.feature_results = False
            org.feature_study_gap = False
        if not org.feature_student_mgmt:
            org.feature_billing = False

        org.save()
        messages.success(request, "Feature settings saved successfully.")
        return redirect('schooladmin:org_features')


# ── Staff Permission Management ───────────────────────────────────────────────

_STAFF_PERM_FIELDS = [
    'can_view_attendance', 'can_add_attendance', 'can_edit_attendance', 'can_export_attendance',
    'can_view_members', 'can_add_members', 'can_edit_members', 'can_delete_members',
    'can_view_payroll', 'can_generate_payroll', 'can_view_own_payslip', 'can_manage_payroll_cfg',
    'can_view_leave', 'can_request_leave', 'can_approve_leave', 'can_view_leave_report',
    'can_view_stock', 'can_add_stock', 'can_edit_stock', 'can_delete_stock', 'can_stock_in_out',
    'can_view_tasks', 'can_assign_tasks', 'can_manage_tasks', 'can_view_task_report',
    'can_view_courses', 'can_manage_courses', 'can_publish_results', 'can_view_result_report',
    'can_view_billing', 'can_generate_bills', 'can_record_payment', 'can_view_dues', 'can_export_billing',
    'can_view_finance', 'can_manage_finance',
    'can_view_events', 'can_manage_events',
    'can_view_complaints', 'can_manage_complaints',
    'can_view_hrms', 'can_manage_hrms',
    'can_view_branches', 'can_manage_branches',
    'can_view_reports', 'can_export_reports', 'can_bulk_export',
]


class StaffPermissionsView(AdminRequiredMixin, View):
    """List all members with a link to edit their permissions."""
    template_name = 'admin/hrms/staff_permissions.html'

    def get(self, request):
        from django.core.paginator import Paginator
        org = _get_org(request)
        q = request.GET.get('q', '').strip()
        qs = member.objects.filter(org=org).order_by('name')
        if q:
            qs = qs.filter(name__icontains=q)
        paginator = Paginator(qs, 25)
        page_obj = paginator.get_page(request.GET.get('page'))
        return render(request, self.template_name, {
            'org': org,
            'members': page_obj,
            'page_obj': page_obj,
            'q': q,
        })


class EditStaffPermissionsView(AdminRequiredMixin, View):
    """Edit granular permissions for a single staff member."""
    template_name = 'admin/hrms/staff_permission_edit.html'

    def _get_or_create_sp(self, mem):
        from handle.models import StaffPermission
        sp, _ = StaffPermission.objects.get_or_create(
            member=mem,
            defaults={'org': mem.org},
        )
        return sp

    def get(self, request, member_id):
        org = _get_org(request)
        mem = get_object_or_404(member, pk=member_id, org=org)
        sp = self._get_or_create_sp(mem)
        return render(request, self.template_name, {
            'org': org,
            'member': mem,
            'sp': sp,
        })

    def post(self, request, member_id):
        org = _get_org(request)
        mem = get_object_or_404(member, pk=member_id, org=org)
        sp = self._get_or_create_sp(mem)

        for field in _STAFF_PERM_FIELDS:
            setattr(sp, field, request.POST.get(field) == '1')
        sp.save()

        messages.success(request, f"Permissions updated for {mem.name}.")
        return redirect('schooladmin:staff_permissions')
