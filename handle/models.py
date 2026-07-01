import datetime
from decimal import Decimal
from management.models import LeaveReport, LeaveType, Organization, CustomUser
from django.db import models
import nepali_datetime
from django.utils import timezone

from datetime import datetime as dt


class Branch(models.Model):
    STATUS_CHOICES = (
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('archived', 'Archived'),
    )

    org = models.ForeignKey(Organization, related_name='branches', on_delete=models.CASCADE)
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=50)
    address = models.CharField(max_length=255, null=True, blank=True)
    phone = models.CharField(max_length=30, null=True, blank=True)
    email = models.EmailField(null=True, blank=True)
    manager = models.ForeignKey(CustomUser, related_name='managed_branches', on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('org', 'code')
        ordering = ('name',)

    def __str__(self):
        return f"{self.name} ({self.code})"


class Classification(models.Model):
    STATUS_CHOICES = (
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('archived', 'Archived'),
    )

    id = models.AutoField(primary_key=1)
    org = models.ForeignKey(Organization, on_delete=models.CASCADE, null = True)
    branch = models.ForeignKey(Branch, related_name='classifications', on_delete=models.SET_NULL, null=True, blank=True)
    name = models.CharField(max_length=200)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    objects = models.Manager()

    def __str__(self):
        return self.name


class Section(models.Model):
    STATUS_CHOICES = (
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('archived', 'Archived'),
    )

    org = models.ForeignKey(Organization, related_name='sections', on_delete=models.CASCADE)
    branch = models.ForeignKey(Branch, related_name='sections', on_delete=models.SET_NULL, null=True, blank=True)
    classification = models.ForeignKey(Classification, related_name='sections', on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=50, null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    updated_at = models.DateTimeField(auto_now=True, null=True)

    class Meta:
        unique_together = ('org', 'classification', 'name')
        ordering = ('classification__name', 'name')

    def __str__(self):
        return f"{self.classification.name} - {self.name}"


class member(models.Model):
    SALARY_CHOICES = (
        ('hourly', 'Per Hour'),
        ('daily', 'Per Day'),
        ('weekly', 'Per Week'),
        ('monthly', 'Per Month'),
    )
    MEMBER_TYPE_CHOICES = (
        ('student', 'Student'),
        ('employee', 'Employee'),
        ('staff', 'Staff'),
        ('intern', 'Intern'),
        ('trainee', 'Trainee'),
        ('teacher', 'Teacher'),
        ('worker', 'Worker'),
        ('member', 'Organization Member'),
    )
    STATUS_CHOICES = (
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('passed_out', 'Passed Out'),
        ('dropped', 'Dropped'),
        ('transferred', 'Transferred'),
        ('suspended', 'Suspended'),
        ('restricted', 'Restricted'),
        ('resigned', 'Resigned'),
        ('intern', 'Intern'),
        ('probation', 'Probation'),
    )

    id = models.AutoField(primary_key=1)
    branch = models.ForeignKey(Branch, related_name='members', on_delete=models.SET_NULL, null=True, blank=True)
    classification = models.ForeignKey(Classification, on_delete=models.DO_NOTHING, related_name='member_type', null=True, blank=True)
    section = models.ForeignKey(Section, related_name='members', on_delete=models.SET_NULL, null=True, blank=True)
    courses = models.ManyToManyField('Course', related_name='members', blank=True)
    device_id = models.IntegerField(null=True)
    org = models.ForeignKey(Organization, on_delete=models.CASCADE, null=True)
    shift_start_time = models.TimeField(default=datetime.time(9, 0, 0), help_text="Expected check-in time (e.g., 09:00 AM)")
    shift_end_time = models.TimeField(default=datetime.time(17, 0, 0), help_text="Expected check-out time (e.g., 05:00 PM)")
    name = models.CharField(max_length=200)
    member_type = models.CharField(max_length=30, choices=MEMBER_TYPE_CHOICES, default='member')
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='active')
    privilege = models.IntegerField(default=1)
    card = models.CharField(max_length=14, unique=False, null=True, blank=True)
    gender = models.CharField(max_length=200, choices=(('Male', 'Male'), ('Female', "Female")))
    address = models.CharField(max_length=200, null=True)
    email = models.EmailField(null=True, unique=True)
    phone = models.BigIntegerField(null=True)
    date_of_birth = models.DateField(null=True, blank=True)
    
    # --- UPGRADED FEATURES ---
    salary_type = models.CharField(max_length=20, choices=SALARY_CHOICES, default='monthly')
    salary_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    salary_per_hour = models.IntegerField(default=15) # Kept for legacy fallback
    tax_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=1.00, help_text="e.g. 1.00 for 1% TDS")
    make_staff = models.BooleanField(default=False) # Toggle to convert member to Staff app user
    staff_type = models.CharField(
        max_length=30,
        choices=(
            ('permanent', 'Permanent'),
            ('temporary', 'Temporary'),
            ('intern', 'Intern'),
            ('contract', 'Contract'),
            ('probation', 'Probation'),
        ),
        default='permanent',
    )
    probation_start_date = models.DateField(null=True, blank=True)
    probation_end_date = models.DateField(null=True, blank=True)
    probation_salary_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=100.00)
    probation_leave_cut_enabled = models.BooleanField(default=False)
    probation_review_status = models.CharField(
        max_length=30,
        choices=(
            ('not_required', 'Not Required'),
            ('pending', 'Pending'),
            ('passed', 'Passed'),
            ('extended', 'Extended'),
            ('failed', 'Failed'),
        ),
        default='not_required',
    )
    pf_enabled = models.BooleanField(default=True)
    ssf_enabled = models.BooleanField(default=True)
    # -------------------------

    # --- STUDENT / MEMBER PROFILE ---
    guardian_name = models.CharField(max_length=200, null=True, blank=True)
    guardian_phone = models.BigIntegerField(null=True, blank=True)
    guardian_email = models.EmailField(null=True, blank=True)
    admission_date = models.DateField(null=True, blank=True)

    # --- BILLING SETUP ---
    BILLING_TYPE_CHOICES = (
        ('monthly_fee',  'Monthly Fee'),
        ('course_wise',  'Course-wise Fee'),
        ('custom',       'Custom Fee'),
        ('scholarship',  'Free / Scholarship'),
    )
    DISCOUNT_TYPE_CHOICES = (
        ('fixed',      'Fixed Amount'),
        ('percentage', 'Percentage'),
    )
    billing_type        = models.CharField(max_length=20, choices=BILLING_TYPE_CHOICES, default='monthly_fee', null=True, blank=True)
    monthly_fee         = models.DecimalField(max_digits=10, decimal_places=2, default=0, null=True, blank=True)
    discount_type       = models.CharField(max_length=20, choices=DISCOUNT_TYPE_CHOICES, null=True, blank=True)
    discount_amount     = models.DecimalField(max_digits=10, decimal_places=2, default=0, null=True, blank=True)
    scholarship_amount  = models.DecimalField(max_digits=10, decimal_places=2, default=0, null=True, blank=True)
    final_monthly_fee   = models.DecimalField(max_digits=10, decimal_places=2, default=0, null=True, blank=True)
    billing_start_date  = models.DateField(null=True, blank=True)
    due_day             = models.PositiveIntegerField(default=15, null=True, blank=True)
    # -------------------------

    created_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)
    sms_enabled = models.BooleanField(default=False)
    black_list = models.BooleanField(default=False)
    
    objects = models.Manager()
    first_date = None
    last_date = None
    ft = None
    tt = None
    date = None
    def __str__(self):
        return f"{self.name} - {self.card} - {self.phone}"

    def first_daily_time(self):
        # Use timezone.localdate() instead of naive datetime.date.today()
        target_date = self.date if self.date else timezone.localdate()
        
        # .first() gets exactly one record from the DB, making it incredibly fast
        first_record = self.member_record.filter(scanned_time__date=target_date).order_by('scanned_time').first()
        
        if first_record:
            # 1. Convert the UTC database time to Nepal local time
            local_time = timezone.localtime(first_record.scanned_time)
            
            self.ft = local_time
            self.first_date = local_time.time() # Now extracts the correct Nepal time
            return self.first_date
            
        return None
    
    def last_daily_time(self):
        target_date = self.date if self.date else timezone.localdate()
        
        records_today = self.member_record.filter(scanned_time__date=target_date).order_by('scanned_time')
        
        # Use .count() instead of len() - it runs a fast SQL COUNT() query
        total_punches = records_today.count()
        
        if total_punches <= 1 or total_punches % 2 == 1:
            self.last_date = None
            return self.last_date
        else:
            # .last() gets only the final record without looping
            last_record = records_today.last()
            
            # Convert to Nepal time
            local_time = timezone.localtime(last_record.scanned_time)
            
            self.tt = local_time
            self.last_date = local_time.time()
            return self.last_date
            

        
    def parse_time(self, time_string):
        try:
            # Try parsing with microseconds
            return dt.strptime(time_string, '%H:%M:%S.%f')
        except ValueError:
            # Fallback to parsing without microseconds
            return dt.strptime(time_string, '%H:%M:%S')
        

    def hour_inside(self):
        aa = self.first_daily_time()
        try:
            bb = self.last_daily_time()
        except:
            bb = None  # Make sure bb is set to None if the exception is caught

        time_interval = None
        if aa:
            time_1 = self.parse_time(str(aa))
        if bb:
            time_2 = self.parse_time(str(bb))
            time_interval = time_2 - time_1
        return time_interval
    
    
    
    def alldataofdaily(self):
        if self.date == None:
            all_todays_data_of_member = self.member_record.filter(scanned_time__date = datetime.date.today())
        else:
            all_todays_data_of_member = self.member_record.filter(scanned_time__date = self.date)
        return all_todays_data_of_member
    
    def get_time_difference(self, time1, time2):
        """Helper to get difference between two time objects as a clean duration string"""
        if not time1 or not time2:
            return None
        # Convert to dummy datetimes to perform math
        today = datetime.date.today()
        dt1 = dt.combine(today, time1)
        dt2 = dt.combine(today, time2)
        if dt1 > dt2:
            diff = dt1 - dt2
            # Format to HH:MM
            total_seconds = int(diff.total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            return f"{hours:02d}:{minutes:02d}"
        return None

    def late_in(self):
        """Calculates how late the member checked in"""
        actual_in = self.first_daily_time()
        if actual_in and actual_in > self.shift_start_time:
            return self.get_time_difference(actual_in, self.shift_start_time)
        return None

    def early_in(self):
        """Calculates how early the member arrived before shift start"""
        actual_in = self.first_daily_time()
        if actual_in and actual_in < self.shift_start_time:
            return self.get_time_difference(self.shift_start_time, actual_in)
        return None

    def early_out(self):
        """Calculates how early the member left before shift end"""
        actual_out = self.last_daily_time()
        if actual_out and actual_out < self.shift_end_time:
            return self.get_time_difference(self.shift_end_time, actual_out)
        return None

    def late_out(self):
        """Calculates how extra hours the member worked after shift end"""
        actual_out = self.last_daily_time()
        if actual_out and actual_out > self.shift_end_time:
            return self.get_time_difference(actual_out, self.shift_end_time)
        return None
    
    def get_leave_balance(self, leave_type_id):
        """Calculates remaining leave balance for the current year"""
        current_year = datetime.date.today().year
        leave_policy = LeaveType.objects.get(id=leave_type_id)
        
        # Find all approved leaves for this specific type, this year
        approved_leaves = LeaveReport.objects.filter(
            member=self,
            leave_type=leave_policy,
            approved=True,
            gap_start__year=current_year
        )
        
        # Sum up used days
        used_days = sum(leave.total_leave_days() for leave in approved_leaves)
        remaining = leave_policy.annual_allocation - used_days
        
        return {
            'total': leave_policy.annual_allocation,
            'used': used_days,
            'remaining': remaining
        }

    def is_on_probation(self, target_date=None):
        target_date = target_date or timezone.localdate()
        if self.staff_type == 'probation' or self.status == 'probation':
            if self.probation_start_date and self.probation_end_date:
                return self.probation_start_date <= target_date <= self.probation_end_date
            return True
        return False
    


class Staff(models.Model):
    id = models.AutoField(primary_key = True)
    admin = models.OneToOneField(CustomUser, on_delete=models.CASCADE)
    org = models.ForeignKey(Organization, on_delete=models.CASCADE)
    member = models.OneToOneField(member, related_name="staff_member", null = True, blank=True, on_delete=models.CASCADE)
    number = models.BigIntegerField(null=True)
    objects = models.Manager()
    def __str__(self):
        return self.admin.email
    
    
class AttendingClassification(models.Model):
    id = models.AutoField(primary_key = True)
    staff = models.ForeignKey(CustomUser, related_name='staff_attending' ,on_delete=models.CASCADE)
    classification = models.ForeignKey(Classification, related_name='staff_classificaton' ,on_delete=models.CASCADE)
    objects = models.Manager()
    def __str__(self):
        return self.staff.email
    
class PaySlip(models.Model):
    member = models.ForeignKey(member, on_delete=models.CASCADE)
    org = models.ForeignKey(Organization, on_delete=models.CASCADE)
    
    # Period
    from_date = models.DateField(null=True, blank=True)
    to_date = models.DateField(null=True, blank=True)
    month_name = models.CharField(max_length=100, null=True, blank=True)
    
    # Stats
    total_days = models.IntegerField(default=0)
    present_days = models.IntegerField(default=0)
    paid_leaves = models.IntegerField(default=0)
    holidays = models.IntegerField(default=0)
    unpaid_absences = models.IntegerField(default=0)
    
    # Financials
    salary_type = models.CharField(max_length=50, null=True, blank=True)
    gross_salary = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    allowance_total = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    bonus_total = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    advance_deduction = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    loan_deduction = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    other_deduction = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    tax_deduction = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    pf_employee = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    pf_employer = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    ssf_employee = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    ssf_employer = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    probation_adjustment = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    net_payable = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    
    generated_on = models.DateTimeField(auto_now_add=True, null=True)
    updated_at = models.DateTimeField(auto_now=True, null=True)

    STATUS_CHOICES = (
        ('draft', 'Draft'),
        ('finalized', 'Finalized'),
        ('paid', 'Paid'),
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    finalized_by = models.ForeignKey(
        'management.CustomUser', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='finalized_payslips'
    )
    notes = models.TextField(null=True, blank=True)

    class Meta:
        ordering = ('-from_date', '-id')

    def __str__(self):
        return f"Payslip: {self.member.name} - {self.month_name}"


class PayrollPolicy(models.Model):
    org = models.OneToOneField(Organization, related_name='payroll_policy', on_delete=models.CASCADE)
    pf_employee_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=10.00)
    pf_employer_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=10.00)
    ssf_employee_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=11.00)
    ssf_employer_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=20.00)
    probation_salary_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=80.00)
    probation_leave_cut_enabled = models.BooleanField(default=True)
    probation_reminder_days = models.PositiveIntegerField(default=7)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Payroll Policy - {self.org.name}"


class PayrollAdjustment(models.Model):
    ADJUSTMENT_CHOICES = (
        ('allowance', 'Allowance'),
        ('bonus', 'Bonus'),
        ('deduction', 'Other Deduction'),
        ('advance', 'Advance Salary'),
        ('loan', 'Loan Deduction'),
    )
    STATUS_CHOICES = (
        ('active', 'Active'),
        ('applied', 'Applied'),
        ('cancelled', 'Cancelled'),
    )

    org = models.ForeignKey(Organization, related_name='payroll_adjustments', on_delete=models.CASCADE)
    member = models.ForeignKey(member, related_name='payroll_adjustments', on_delete=models.CASCADE)
    adjustment_type = models.CharField(max_length=20, choices=ADJUSTMENT_CHOICES)
    title = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    effective_date = models.DateField(default=timezone.localdate)
    notes = models.TextField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    created_by = models.ForeignKey(CustomUser, related_name='payroll_adjustments', on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-effective_date', '-id')

    def __str__(self):
        return f"{self.member.name} - {self.title}"


class AdvanceSalary(models.Model):
    """
    Dedicated advance salary model with installment tracking.
    Unlike PayrollAdjustment(type='advance'), this records the full
    repayment schedule and tracks how much has been recovered.
    """
    STATUS_CHOICES = (
        ('active', 'Active — recovering'),
        ('fully_recovered', 'Fully Recovered'),
        ('cancelled', 'Cancelled'),
    )

    org = models.ForeignKey(Organization, related_name='advance_salaries', on_delete=models.CASCADE)
    member = models.ForeignKey(member, related_name='advance_salaries', on_delete=models.CASCADE)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    num_installments = models.PositiveIntegerField(default=1, help_text="Number of months to recover over")
    installment_amount = models.DecimalField(max_digits=12, decimal_places=2, help_text="Auto-deducted each payslip cycle")
    paid_installments = models.PositiveIntegerField(default=0)
    remaining_balance = models.DecimalField(max_digits=12, decimal_places=2)
    purpose = models.CharField(max_length=255, null=True, blank=True)
    approved_by = models.ForeignKey(CustomUser, related_name='approved_advances', on_delete=models.SET_NULL, null=True, blank=True)
    effective_date = models.DateField(default=timezone.localdate, help_text="Recovery starts from this date")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    notes = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('-created_at',)

    def __str__(self):
        return f"Advance {self.total_amount} — {self.member.name} ({self.status})"

    def save(self, *args, **kwargs):
        if not self.pk:
            self.remaining_balance = self.total_amount
        if not self.installment_amount:
            n = self.num_installments or 1
            self.installment_amount = (self.total_amount / n).quantize(
                __import__('decimal').Decimal('0.01')
            )
        super().save(*args, **kwargs)

    def apply_installment(self):
        """Call when a payslip that deducted this advance is finalized."""
        from decimal import Decimal
        if self.status != 'active':
            return
        self.paid_installments += 1
        self.remaining_balance = max(
            Decimal('0.00'),
            self.remaining_balance - self.installment_amount
        )
        if self.remaining_balance <= Decimal('0.01'):
            self.status = 'fully_recovered'
        self.save(update_fields=['paid_installments', 'remaining_balance', 'status', 'updated_at'])


class ProvidentFundRecord(models.Model):
    org = models.ForeignKey(Organization, related_name='pf_records', on_delete=models.CASCADE)
    member = models.ForeignKey(member, related_name='pf_records', on_delete=models.CASCADE)
    payslip = models.ForeignKey(PaySlip, related_name='pf_records', on_delete=models.SET_NULL, null=True, blank=True)
    month_name = models.CharField(max_length=100)
    employee_contribution = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    employer_contribution = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    recorded_on = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-recorded_on',)

    def __str__(self):
        return f"PF {self.member.name} - {self.month_name}"


class SocialSecurityFundRecord(models.Model):
    org = models.ForeignKey(Organization, related_name='ssf_records', on_delete=models.CASCADE)
    member = models.ForeignKey(member, related_name='ssf_records', on_delete=models.CASCADE)
    payslip = models.ForeignKey(PaySlip, related_name='ssf_records', on_delete=models.SET_NULL, null=True, blank=True)
    month_name = models.CharField(max_length=100)
    employee_contribution = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    employer_contribution = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    recorded_on = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-recorded_on',)

    def __str__(self):
        return f"SSF {self.member.name} - {self.month_name}"


class ProbationReview(models.Model):
    REVIEW_CHOICES = (
        ('pending', 'Pending'),
        ('passed', 'Passed'),
        ('extended', 'Extended'),
        ('failed', 'Failed'),
    )

    org = models.ForeignKey(Organization, related_name='probation_reviews', on_delete=models.CASCADE)
    member = models.ForeignKey(member, related_name='probation_reviews', on_delete=models.CASCADE)
    review_date = models.DateField(default=timezone.localdate)
    status = models.CharField(max_length=20, choices=REVIEW_CHOICES, default='pending')
    reviewer = models.ForeignKey(CustomUser, related_name='probation_reviews', on_delete=models.SET_NULL, null=True, blank=True)
    notes = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-review_date', '-id')

    def __str__(self):
        return f"{self.member.name} probation review - {self.status}"
    
    
class Device(models.Model):
    org = models.ForeignKey(Organization, on_delete=models.CASCADE, null = True)
    name = models.CharField(max_length=200)
    ip_address = models.CharField(max_length=30)
    port_no = models.IntegerField()

    def __str__(self):
        return f"{self.org}- {self.name}"



class AttendanceRecord(models.Model):
    mem = models.ForeignKey(member, related_name="member_record", on_delete=models.CASCADE)
    org = models.ForeignKey(Organization, on_delete=models.CASCADE, null=True)
    scanned_time = models.DateTimeField()
    got_time = datetime.datetime.today()
    scanned_time_np = models.CharField(max_length=50, blank=True)  # Store Nepali datetime as string
    
    def save(self, *args, **kwargs):
        # Convert to Nepali datetime when saving
        # if self.scanned_time:
        #     nepali_dt = nepali_datetime.datetime.from_datetime(self.scanned_time)
        #     self.scanned_time_np = str(nepali_dt)
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.mem.name} scanned on {self.scanned_time}"
    
    def first_daily_time(self):
        today_data = AttendanceRecord.objects.filter(scanned_time__date=self.got_time).filter(mem=self.mem)
        first_date = None
        for d in today_data:
            first_date = d.scanned_time.time()
            break
        return first_date
    
    def last_daily_time(self):
        today_data = AttendanceRecord.objects.filter(scanned_time__date=self.got_time).filter(mem=self.mem)
        last_date = None
        if len(today_data) <= 1:
            last_date = None
        else:
            for d in today_data:
                last_date = d.scanned_time.time()
            return last_date


class Course(models.Model):
    STATUS_CHOICES = (
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('archived', 'Archived'),
    )

    org = models.ForeignKey(Organization, related_name="org_course", on_delete=models.CASCADE)
    branch = models.ForeignKey(Branch, related_name='courses', on_delete=models.SET_NULL, null=True, blank=True)
    classifications = models.ManyToManyField(Classification, related_name='courses', blank=True)
    sections = models.ManyToManyField(Section, related_name='courses', blank=True)
    teacher = models.ForeignKey(CustomUser, related_name='assigned_courses', on_delete=models.SET_NULL, null=True, blank=True)
    code = models.CharField(max_length=50, null=True, blank=True)
    name = models.CharField(max_length=200)
    description = models.TextField(null=True, blank=True)
    credit_hour = models.DecimalField(max_digits=6, decimal_places=2, default=0.00)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    updated_at = models.DateTimeField(auto_now=True, null=True)

    class Meta:
        ordering = ('name',)

    def __str__(self):
        return f"{self.name} {self.org.name}"
    



class CourseAttendance(models.Model):
    org = models.ForeignKey(Organization, related_name="org_course_attendance", on_delete=models.CASCADE)
    staff = models.ForeignKey(CustomUser, related_name='staff_course_attendance', on_delete=models.DO_NOTHING, null=True, blank=True)
    course = models.ForeignKey(Course, related_name='course_attendance', on_delete=models.DO_NOTHING, null=True, blank=True)
    branch = models.ForeignKey(Branch, related_name='course_attendance', on_delete=models.SET_NULL, null=True, blank=True)
    classification = models.ForeignKey(Classification, related_name='course_classification', on_delete=models.DO_NOTHING, null= True, blank=True)
    section = models.ForeignKey(Section, related_name='course_attendance', on_delete=models.SET_NULL, null=True, blank=True)
    attendance_date = models.DateField(default=timezone.localdate)
    topic_taught = models.CharField(max_length=255, null=True, blank=True)
    gap_note = models.TextField(null=True, blank=True)

 
    def __str__(self):
        return f"{self.staff.get_full_name()} {self.org.name}"


class AttendanceGap(models.Model):
    RECOVERY_STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('notified', 'Notified'),
        ('covered', 'Covered'),
        ('reviewed', 'Reviewed'),
    )

    org = models.ForeignKey(Organization, related_name='attendance_gaps', on_delete=models.CASCADE)
    member = models.ForeignKey(member, related_name='attendance_gaps', on_delete=models.CASCADE)
    branch = models.ForeignKey(Branch, related_name='attendance_gaps', on_delete=models.SET_NULL, null=True, blank=True)
    classification = models.ForeignKey(Classification, related_name='attendance_gaps', on_delete=models.SET_NULL, null=True, blank=True)
    section = models.ForeignKey(Section, related_name='attendance_gaps', on_delete=models.SET_NULL, null=True, blank=True)
    course = models.ForeignKey(Course, related_name='attendance_gaps', on_delete=models.SET_NULL, null=True, blank=True)
    teacher = models.ForeignKey(CustomUser, related_name='attendance_gaps', on_delete=models.SET_NULL, null=True, blank=True)
    date = models.DateField(default=timezone.localdate)
    topic_missed = models.CharField(max_length=255)
    reason = models.TextField(null=True, blank=True)
    recovery_status = models.CharField(max_length=20, choices=RECOVERY_STATUS_CHOICES, default='pending')
    notified_at = models.DateTimeField(null=True, blank=True)
    covered_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('-date', 'member__name')

    def __str__(self):
        return f"{self.member.name} missed {self.topic_missed} on {self.date}"


class StockCategory(models.Model):
    org = models.ForeignKey(Organization, related_name='stock_categories', on_delete=models.CASCADE)
    name = models.CharField(max_length=150)
    description = models.TextField(null=True, blank=True)

    class Meta:
        unique_together = ('org', 'name')
        ordering = ('name',)

    def __str__(self):
        return self.name


class StockItem(models.Model):
    STATUS_CHOICES = (
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('archived', 'Archived'),
    )

    org = models.ForeignKey(Organization, related_name='stock_items', on_delete=models.CASCADE)
    branch = models.ForeignKey(Branch, related_name='stock_items', on_delete=models.SET_NULL, null=True, blank=True)
    category = models.ForeignKey(StockCategory, related_name='items', on_delete=models.SET_NULL, null=True, blank=True)
    name = models.CharField(max_length=200)
    sku = models.CharField(max_length=80, null=True, blank=True)
    unit = models.CharField(max_length=50, default='pcs')
    quantity = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    low_stock_threshold = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    supplier = models.CharField(max_length=200, null=True, blank=True)
    purchase_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    purchase_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('name',)

    def __str__(self):
        return self.name

    @property
    def is_low_stock(self):
        return self.quantity <= self.low_stock_threshold


class StockMovement(models.Model):
    MOVEMENT_CHOICES = (
        ('in', 'Stock In'),
        ('out', 'Stock Out'),
        ('damage', 'Damage/Lost'),
        ('adjustment', 'Adjustment'),
    )

    org = models.ForeignKey(Organization, related_name='stock_movements', on_delete=models.CASCADE)
    branch = models.ForeignKey(Branch, related_name='stock_movements', on_delete=models.SET_NULL, null=True, blank=True)
    item = models.ForeignKey(StockItem, related_name='movements', on_delete=models.CASCADE)
    movement_type = models.CharField(max_length=20, choices=MOVEMENT_CHOICES)
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    movement_date = models.DateField(default=timezone.localdate)
    note = models.TextField(null=True, blank=True)
    created_by = models.ForeignKey(CustomUser, related_name='stock_movements', on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-movement_date', '-id')

    def __str__(self):
        return f"{self.item.name} {self.movement_type} {self.quantity}"

    @property
    def total_cost(self):
        return self.quantity * self.unit_cost

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        previous = None
        if not is_new:
            previous = StockMovement.objects.get(pk=self.pk)
        super().save(*args, **kwargs)
        if previous:
            previous.item.quantity -= previous.signed_quantity()
            previous.item.save(update_fields=['quantity', 'updated_at'])
        self.item.quantity += self.signed_quantity()
        self.item.save(update_fields=['quantity', 'updated_at'])

    def signed_quantity(self):
        if self.movement_type == 'in':
            return self.quantity
        if self.movement_type == 'adjustment':
            return self.quantity
        return -self.quantity

    def delete(self, *args, **kwargs):
        self.item.quantity -= self.signed_quantity()
        self.item.save(update_fields=['quantity', 'updated_at'])
        super().delete(*args, **kwargs)


class TransactionCategory(models.Model):
    TYPE_CHOICES = (
        ('income', 'Income'),
        ('expense', 'Expense'),
    )

    org = models.ForeignKey(Organization, related_name='transaction_categories', on_delete=models.CASCADE)
    name = models.CharField(max_length=150)
    transaction_type = models.CharField(max_length=20, choices=TYPE_CHOICES)

    class Meta:
        unique_together = ('org', 'name', 'transaction_type')
        ordering = ('transaction_type', 'name')

    def __str__(self):
        return f"{self.name} ({self.transaction_type})"


class FinancialTransaction(models.Model):
    TYPE_CHOICES = (
        ('income', 'Income'),
        ('expense', 'Expense'),
    )
    METHOD_CHOICES = (
        ('cash', 'Cash'),
        ('bank', 'Bank'),
        ('card', 'Card'),
        ('online', 'Online'),
        ('other', 'Other'),
    )

    org = models.ForeignKey(Organization, related_name='financial_transactions', on_delete=models.CASCADE)
    branch = models.ForeignKey(Branch, related_name='financial_transactions', on_delete=models.SET_NULL, null=True, blank=True)
    category = models.ForeignKey(TransactionCategory, related_name='transactions', on_delete=models.SET_NULL, null=True, blank=True)
    transaction_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    title = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    transaction_date = models.DateField(default=timezone.localdate)
    payment_method = models.CharField(max_length=20, choices=METHOD_CHOICES, default='cash')
    reference_number = models.CharField(max_length=120, null=True, blank=True)
    note = models.TextField(null=True, blank=True)
    attachment = models.FileField(upload_to='transactions/', null=True, blank=True)
    created_by = models.ForeignKey(CustomUser, related_name='financial_transactions', on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('-transaction_date', '-id')

    def __str__(self):
        return f"{self.title} - {self.amount}"


def compute_grade(percentage):
    """Standard grade from percentage. Used in ResultRecord and views."""
    p = float(percentage)
    if p >= 90: return 'A+'
    if p >= 80: return 'A'
    if p >= 70: return 'B+'
    if p >= 60: return 'B'
    if p >= 50: return 'C+'
    if p >= 40: return 'C'
    return 'NG'


class Subject(models.Model):
    """Specific subjects/courses taught within a classification (and optionally a section)."""
    STATUS_CHOICES = (('active', 'Active'), ('inactive', 'Inactive'))

    org = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="org_subjects")
    classification = models.ForeignKey(Classification, on_delete=models.CASCADE, related_name="class_subjects")
    section = models.ForeignKey('Section', on_delete=models.SET_NULL, null=True, blank=True, related_name='section_subjects')
    teacher = models.ForeignKey('management.CustomUser', on_delete=models.SET_NULL, null=True, blank=True, related_name='teaching_subjects')
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=50, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    credit_hour = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    full_marks = models.DecimalField(max_digits=5, decimal_places=2, default=100)
    pass_marks = models.DecimalField(max_digits=5, decimal_places=2, default=40)
    monthly_fee  = models.DecimalField(max_digits=10, decimal_places=2, default=0, null=True, blank=True)
    one_time_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0, null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    updated_at = models.DateTimeField(auto_now=True, null=True)

    class Meta:
        unique_together = ('org', 'classification', 'section', 'name')
        ordering = ('classification', 'name')

    def __str__(self):
        base = f"{self.name} — {self.classification.name}"
        return f"{base} ({self.section.name})" if self.section else base


class ExamTerm(models.Model):
    """Defines an exam period scoped to an org (optionally classification/section)."""
    STATUS_CHOICES = (
        ('draft', 'Draft'),
        ('marks_entry', 'Marks Entry'),
        ('published', 'Published'),
        ('archived', 'Archived'),
    )

    org = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="org_exams")
    classification = models.ForeignKey(Classification, on_delete=models.SET_NULL, null=True, blank=True, related_name='exams')
    section = models.ForeignKey('Section', on_delete=models.SET_NULL, null=True, blank=True, related_name='exams')
    academic_year = models.CharField(max_length=20, null=True, blank=True)
    name = models.CharField(max_length=200)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    is_published = models.BooleanField(default=False)

    class Meta:
        ordering = ('-start_date',)

    def __str__(self):
        return f"{self.name} ({self.org.name})"


class ResultRecord(models.Model):
    """Marks obtained by a student in a subject for a specific exam."""
    from management.models import CustomUser as _CU  # local import to avoid circular

    student = models.ForeignKey(member, on_delete=models.CASCADE, related_name="student_results")
    exam = models.ForeignKey(ExamTerm, on_delete=models.CASCADE, related_name="exam_records")
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name="subject_records")
    obtained_marks = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    grade = models.CharField(max_length=5, null=True, blank=True)
    is_absent = models.BooleanField(default=False)
    remarks = models.CharField(max_length=255, null=True, blank=True)
    created_by = models.ForeignKey('management.CustomUser', on_delete=models.SET_NULL, null=True, blank=True, related_name='created_results')
    updated_by = models.ForeignKey('management.CustomUser', on_delete=models.SET_NULL, null=True, blank=True, related_name='updated_results')
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    updated_at = models.DateTimeField(auto_now=True, null=True)

    class Meta:
        unique_together = ('student', 'exam', 'subject')

    def __str__(self):
        return f"{self.student.name} — {self.subject.name}: {self.obtained_marks}"

    def save(self, *args, **kwargs):
        if self.is_absent:
            self.obtained_marks = 0
            self.remarks = self.remarks or 'Absent'
        if self.subject_id and self.subject.full_marks > 0:
            pct = float(self.obtained_marks) / float(self.subject.full_marks) * 100
            self.grade = compute_grade(pct)
        super().save(*args, **kwargs)

    @property
    def is_passed(self):
        return (not self.is_absent) and self.obtained_marks >= self.subject.pass_marks

    @property
    def percentage(self):
        if self.subject.full_marks:
            return round(float(self.obtained_marks) / float(self.subject.full_marks) * 100, 1)
        return 0

# ---------------------------------------------------------
# 2. BILLING & INVOICING MODELS
# ---------------------------------------------------------

class Bill(models.Model):
    """Main invoice header for a student/member"""
    org    = models.ForeignKey(Organization,  on_delete=models.CASCADE, related_name="org_bills")
    member = models.ForeignKey(member,        on_delete=models.CASCADE, related_name="member_bills")
    classification = models.ForeignKey(Classification, on_delete=models.SET_NULL, null=True, blank=True, related_name='class_bills')
    section        = models.ForeignKey('Section',       on_delete=models.SET_NULL, null=True, blank=True, related_name='section_bills')

    invoice_number = models.CharField(max_length=100, unique=True)
    issue_date     = models.DateField(auto_now_add=True)
    due_date       = models.DateField()

    # Monthly context
    billing_month = models.PositiveSmallIntegerField(null=True, blank=True)  # 1–12
    billing_year  = models.PositiveIntegerField(null=True, blank=True)
    BILLING_TYPE_CHOICES = (
        ('monthly_fee', 'Monthly Fee'),
        ('course_wise', 'Course-wise Fee'),
        ('custom',      'Custom Fee'),
        ('scholarship', 'Scholarship/Free'),
    )
    billing_type = models.CharField(max_length=20, choices=BILLING_TYPE_CHOICES, null=True, blank=True)

    # Amount breakdown (snapshot at generation)
    base_amount        = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    course_fee_amount  = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount_amount    = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    scholarship_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    fine_amount        = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    previous_due       = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    STATUS_CHOICES = (
        ('Unpaid',    'Unpaid'),
        ('Partial',   'Partial'),
        ('Paid',      'Paid'),
        ('Cancelled', 'Cancelled'),
    )
    status      = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Unpaid')
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    amount_paid  = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    remarks      = models.TextField(null=True, blank=True)

    # Generation metadata
    generated_by = models.ForeignKey('management.CustomUser', on_delete=models.SET_NULL, null=True, blank=True, related_name='generated_bills')
    is_sent      = models.BooleanField(default=False)
    sent_at      = models.DateTimeField(null=True, blank=True)
    sent_method  = models.CharField(max_length=30, null=True, blank=True)

    class Meta:
        ordering = ('-issue_date',)

    def __str__(self):
        return f"{self.invoice_number} - {self.member.name}"

    @property
    def balance_due(self):
        return self.total_amount - self.amount_paid


class BillItem(models.Model):
    """Line items for a specific bill"""
    FEE_TYPE_CHOICES = (
        ('monthly',   'Monthly Fee'),
        ('course',    'Course Fee'),
        ('admission', 'Admission Fee'),
        ('exam',      'Exam Fee'),
        ('transport', 'Transport Fee'),
        ('hostel',    'Hostel Fee'),
        ('misc',      'Miscellaneous'),
    )
    bill        = models.ForeignKey(Bill, on_delete=models.CASCADE, related_name="items")
    subject     = models.ForeignKey(Subject, on_delete=models.SET_NULL, null=True, blank=True, related_name='bill_items')
    description = models.CharField(max_length=255)
    fee_type    = models.CharField(max_length=20, choices=FEE_TYPE_CHOICES, default='monthly')
    amount      = models.DecimalField(max_digits=10, decimal_places=2)
    discount    = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    def __str__(self):
        return f"{self.description}: {self.amount}"

    @property
    def final_amount(self):
        return self.amount - self.discount


class BillSendLog(models.Model):
    """Tracks every bill-send attempt"""
    METHOD_CHOICES = (
        ('email',     'Email'),
        ('sms',       'SMS'),
        ('whatsapp',  'WhatsApp'),
        ('pdf',       'PDF Download'),
        ('in_app',    'In-App'),
    )
    STATUS_CHOICES = (
        ('sent',    'Sent'),
        ('failed',  'Failed'),
        ('pending', 'Pending'),
    )
    bill           = models.ForeignKey(Bill,   on_delete=models.CASCADE, related_name='send_logs')
    sent_to_email  = models.EmailField(null=True, blank=True)
    sent_to_phone  = models.CharField(max_length=20, null=True, blank=True)
    sent_method    = models.CharField(max_length=20, choices=METHOD_CHOICES, default='email')
    message_body   = models.TextField(null=True, blank=True)
    status         = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    sent_by        = models.ForeignKey('management.CustomUser', on_delete=models.SET_NULL, null=True, blank=True)
    sent_at        = models.DateTimeField(auto_now_add=True)
    error_message  = models.TextField(null=True, blank=True)

    class Meta:
        ordering = ('-sent_at',)

    def __str__(self):
        return f"BillSendLog #{self.pk} – {self.bill.invoice_number} via {self.sent_method}"


class ResultSendLog(models.Model):
    """Tracks every result-send attempt"""
    METHOD_CHOICES = (
        ('email',    'Email'),
        ('sms',      'SMS'),
        ('whatsapp', 'WhatsApp'),
        ('pdf',      'PDF Download'),
        ('in_app',   'In-App'),
    )
    STATUS_CHOICES = (
        ('sent',    'Sent'),
        ('failed',  'Failed'),
        ('pending', 'Pending'),
    )
    exam           = models.ForeignKey(ExamTerm, on_delete=models.CASCADE, related_name='send_logs')
    member         = models.ForeignKey(member,   on_delete=models.CASCADE, related_name='result_send_logs')
    sent_to_email  = models.EmailField(null=True, blank=True)
    sent_to_phone  = models.CharField(max_length=20, null=True, blank=True)
    sent_method    = models.CharField(max_length=20, choices=METHOD_CHOICES, default='email')
    message_body   = models.TextField(null=True, blank=True)
    status         = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    sent_by        = models.ForeignKey('management.CustomUser', on_delete=models.SET_NULL, null=True, blank=True)
    sent_at        = models.DateTimeField(auto_now_add=True)
    error_message  = models.TextField(null=True, blank=True)

    class Meta:
        ordering = ('-sent_at',)

    def __str__(self):
        return f"ResultSendLog #{self.pk} – {self.member.name} / {self.exam.name}"


# ---------------------------------------------------------
# EVENT MANAGEMENT
# ---------------------------------------------------------

class Event(models.Model):
    EVENT_TYPE_CHOICES = (
        ('sports', 'Sports Week'),
        ('seminar', 'Seminar'),
        ('meeting', 'Meeting'),
        ('exam', 'Exam Event'),
        ('program', 'Program'),
        ('holiday', 'Holiday Event'),
        ('other', 'Other'),
    )
    STATUS_CHOICES = (
        ('upcoming', 'Upcoming'),
        ('ongoing', 'Ongoing'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    )

    org = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='events')
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name='events')
    title = models.CharField(max_length=255)
    event_type = models.CharField(max_length=30, choices=EVENT_TYPE_CHOICES, default='other')
    start_date = models.DateField()
    end_date = models.DateField()
    location = models.CharField(max_length=255, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    responsible_staff = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='responsible_events')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='upcoming')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-start_date',)

    def __str__(self):
        return self.title

    @property
    def total_stock_cost(self):
        return sum(u.total_cost for u in self.stock_usages.all())


class EventStockUsage(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='stock_usages')
    item = models.ForeignKey(StockItem, on_delete=models.CASCADE, related_name='event_usages')
    quantity_used = models.DecimalField(max_digits=10, decimal_places=2)
    note = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.event.title} - {self.item.name} x{self.quantity_used}"

    @property
    def total_cost(self):
        return self.quantity_used * (self.item.purchase_cost or 0)

    def save(self, *args, **kwargs):
        if not self.pk:
            self.item.quantity -= Decimal(str(self.quantity_used))
            self.item.save(update_fields=['quantity'])
            StockMovement.objects.create(
                org=self.event.org,
                branch=self.event.branch or self.item.branch,
                item=self.item,
                created_by_id=None,
                movement_type='out',
                quantity=self.quantity_used,
                unit_cost=self.item.purchase_cost or 0,
                movement_date=self.event.start_date,
                note=f"Event usage: {self.event.title}",
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        self.item.quantity += self.quantity_used
        self.item.save(update_fields=['quantity'])
        super().delete(*args, **kwargs)


# ---------------------------------------------------------
# COMPLAINT SYSTEM
# ---------------------------------------------------------

class Complaint(models.Model):
    PRIORITY_CHOICES = (
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
    )
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('reviewing', 'Reviewing'),
        ('resolved', 'Resolved'),
        ('rejected', 'Rejected'),
    )

    org = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='complaints')
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name='complaints')
    filed_by = models.ForeignKey(member, on_delete=models.CASCADE, related_name='filed_complaints')
    complaint_type = models.CharField(max_length=100)
    subject = models.CharField(max_length=255)
    description = models.TextField()
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    admin_remarks = models.TextField(null=True, blank=True)
    resolution_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('-created_at',)

    def __str__(self):
        return f"{self.subject} - {self.filed_by.name}"


# ---------------------------------------------------------
# HRMS EXTENDED
# ---------------------------------------------------------

class ResignationRecord(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('completed', 'Completed'),
    )

    org = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='resignations')
    member = models.ForeignKey('member', on_delete=models.CASCADE, related_name='resignations')
    resignation_date = models.DateField()
    notice_period_days = models.PositiveIntegerField(default=30)
    last_working_day = models.DateField(null=True, blank=True)
    reason = models.TextField()
    exit_interview_note = models.TextField(null=True, blank=True)
    clearance_status = models.BooleanField(default=False)
    final_settlement_status = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    self_applied = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-created_at',)

    def __str__(self):
        return f"{self.member.name} - {self.resignation_date}"


class StaffDocument(models.Model):
    DOC_TYPE_CHOICES = (
        ('id', 'ID Card'),
        ('contract', 'Contract'),
        ('certificate', 'Certificate'),
        ('degree', 'Degree'),
        ('passport', 'Passport'),
        ('other', 'Other'),
    )

    org = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='staff_documents')
    member = models.ForeignKey('member', on_delete=models.CASCADE, related_name='documents')
    document_type = models.CharField(max_length=30, choices=DOC_TYPE_CHOICES, default='other')
    title = models.CharField(max_length=255)
    file = models.FileField(upload_to='staff_documents/')
    expiry_date = models.DateField(null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.member.name} - {self.title}"


# ---------------------------------------------------------
# ABSENCE CORRECTION (Mark wrong-present as absent)
# ---------------------------------------------------------

class AbsenceCorrection(models.Model):
    """Record when an attendance entry is removed and why."""
    org = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='absence_corrections')
    member = models.ForeignKey('member', on_delete=models.CASCADE, related_name='absence_corrections')
    date = models.DateField()
    reason = models.CharField(max_length=500)
    corrected_by = models.ForeignKey('management.CustomUser', on_delete=models.SET_NULL, null=True, blank=True)
    corrected_at = models.DateTimeField(auto_now_add=True)
    original_scan_time = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ('-corrected_at',)

    def __str__(self):
        return f"{self.member.name} absent on {self.date} - {self.reason[:40]}"


# ---------------------------------------------------------
# PRIVILEGE LABELS (on member.privilege int field)
# 1=Self Only, 2=Class Level, 3=Branch Level, 4=Org Level, 5=Full Admin
# ---------------------------------------------------------
PRIVILEGE_LEVEL_CHOICES = (
    (1, 'Self Only — view own data'),
    (2, 'Class Level — view class data'),
    (3, 'Branch Level — view branch data'),
    (4, 'Org Level — view finance & HR data'),
    (5, 'Full Admin — all access'),
)


# =============================================================
# TASK MANAGEMENT MODULE
# =============================================================

class Task(models.Model):
    PRIORITY_CHOICES = (
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    )
    TASK_TYPE_CHOICES = (
        ('one_time', 'One Time'),
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('recurring', 'Recurring / Custom'),
    )

    org = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='tasks')
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name='tasks')
    title = models.CharField(max_length=300)
    description = models.TextField(blank=True)
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium')
    task_type = models.CharField(max_length=15, choices=TASK_TYPE_CHOICES, default='one_time')
    start_date = models.DateField()
    due_date = models.DateField()
    due_time = models.TimeField(null=True, blank=True)
    assigned_to = models.ManyToManyField('member', related_name='assigned_tasks', blank=True)
    created_by = models.ForeignKey('management.CustomUser', on_delete=models.SET_NULL, null=True, related_name='created_tasks')
    created_at = models.DateTimeField(auto_now_add=True)
    attachment = models.FileField(upload_to='task_attachments/', null=True, blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    requires_approval = models.BooleanField(default=False)

    class Meta:
        ordering = ('-created_at',)

    def __str__(self):
        return f"[{self.get_priority_display()}] {self.title}"

    def generate_instances(self):
        """Create TaskInstance records for each assigned member and each date."""
        import datetime as _dt

        dates = []
        if self.task_type == 'one_time':
            dates = [self.due_date]
        elif self.task_type == 'daily':
            d = self.start_date
            while d <= self.due_date:
                dates.append(d)
                d += _dt.timedelta(days=1)
        elif self.task_type == 'weekly':
            d = self.start_date
            while d <= self.due_date:
                dates.append(d)
                d += _dt.timedelta(weeks=1)
        elif self.task_type == 'monthly':
            d = self.start_date
            while d <= self.due_date:
                dates.append(d)
                month = d.month + 1
                year = d.year + (month - 1) // 12
                month = ((month - 1) % 12) + 1
                try:
                    d = d.replace(year=year, month=month)
                except ValueError:
                    import calendar
                    d = d.replace(year=year, month=month, day=calendar.monthrange(year, month)[1])
        elif self.task_type == 'recurring':
            d = self.start_date
            while d <= self.due_date:
                dates.append(d)
                d += _dt.timedelta(days=1)

        for member_obj in self.assigned_to.all():
            for date in dates:
                TaskInstance.objects.get_or_create(
                    task=self,
                    assigned_member=member_obj,
                    due_date=date,
                    defaults={'due_time': self.due_time}
                )


class TaskInstance(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('not_completed', 'Not Completed'),
        ('overdue', 'Overdue'),
        ('cancelled', 'Cancelled'),
        ('missed_absence', 'Missed Due To Absence'),
        ('rework_required', 'Rework Required'),
    )

    NOT_DONE_REASONS = (
        ('workload', 'Could not complete due to workload'),
        ('waiting_approval', 'Waiting for approval'),
        ('material_unavailable', 'Required material unavailable'),
        ('assigned_late', 'Assigned late'),
        ('absence', 'Staff absent on assigned task date'),
        ('other', 'Other reason'),
    )

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='instances')
    assigned_member = models.ForeignKey('member', on_delete=models.CASCADE, related_name='task_instances')
    due_date = models.DateField()
    due_time = models.TimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    completion_note = models.TextField(blank=True)
    not_done_reason = models.CharField(max_length=30, choices=NOT_DONE_REASONS, blank=True)
    not_done_detail = models.TextField(blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    proof_attachment = models.FileField(upload_to='task_proofs/', null=True, blank=True)

    approval_status = models.CharField(
        max_length=20,
        choices=(
            ('not_required', 'Not Required'),
            ('pending_approval', 'Pending Approval'),
            ('approved', 'Approved'),
            ('rejected', 'Rejected'),
        ),
        default='not_required'
    )
    approved_by = models.ForeignKey('management.CustomUser', on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_task_instances')
    approved_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)

    staff_was_absent = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('due_date', 'task__priority')
        unique_together = ('task', 'assigned_member', 'due_date')

    def __str__(self):
        return f"{self.task.title} — {self.assigned_member.name} [{self.due_date}]"

    def refresh_overdue_status(self):
        """Auto-update status to overdue or missed_absence if past due."""
        import datetime as _dt
        today = _dt.date.today()
        if self.due_date < today and self.status in ('pending', 'in_progress'):
            was_absent = not AttendanceRecord.objects.filter(
                mem=self.assigned_member,
                scanned_time__date=self.due_date
            ).exists()
            if was_absent:
                self.status = 'missed_absence'
                self.staff_was_absent = True
                if not self.not_done_reason:
                    self.not_done_reason = 'absence'
                if not self.not_done_detail:
                    self.not_done_detail = 'Staff absent on assigned task date.'
            else:
                self.status = 'overdue'
            self.save(update_fields=['status', 'staff_was_absent', 'not_done_reason', 'not_done_detail'])
        return self.status


class TaskUpdateLog(models.Model):
    instance = models.ForeignKey(TaskInstance, on_delete=models.CASCADE, related_name='update_logs')
    changed_by = models.ForeignKey('management.CustomUser', on_delete=models.SET_NULL, null=True)
    old_status = models.CharField(max_length=20)
    new_status = models.CharField(max_length=20)
    note = models.TextField(blank=True)
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-changed_at',)

    def __str__(self):
        return f"{self.instance} {self.old_status} → {self.new_status}"


class TaskAttachment(models.Model):
    instance = models.ForeignKey(TaskInstance, on_delete=models.CASCADE, related_name='attachments')
    file = models.FileField(upload_to='task_attachments/proof/')
    label = models.CharField(max_length=200, blank=True)
    uploaded_by = models.ForeignKey('management.CustomUser', on_delete=models.SET_NULL, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Attachment for {self.instance}"


# =============================================================
# STAFF PERMISSION MODULE
# Granular per-feature permissions for staff users.
# Admin sets these per staff member via the privilege page.
# Template context: {{ perms.can_view_payroll }}, etc.
# =============================================================

class StaffPermission(models.Model):
    """
    One row per staff member. Stores every granular boolean permission.
    Admin edits via schooladmin/hrms/staff-permissions/<member_id>/.
    Context processor injects this as `staff_perms` on every request.
    If no row exists, all permissions default to False.
    """
    member = models.OneToOneField(
        'handle.member',
        on_delete=models.CASCADE,
        related_name='staff_permission',
    )
    org = models.ForeignKey(
        'management.Organization',
        on_delete=models.CASCADE,
        related_name='staff_permissions',
    )

    # ── Attendance ─────────────────────────────────────────────
    can_view_attendance   = models.BooleanField(default=True)
    can_add_attendance    = models.BooleanField(default=False)
    can_edit_attendance   = models.BooleanField(default=False)
    can_export_attendance = models.BooleanField(default=False)

    # ── Members / Students ────────────────────────────────────
    can_view_members   = models.BooleanField(default=False)
    can_add_members    = models.BooleanField(default=False)
    can_edit_members   = models.BooleanField(default=False)
    can_delete_members = models.BooleanField(default=False)

    # ── Payroll ───────────────────────────────────────────────
    can_view_payroll        = models.BooleanField(default=False)
    can_generate_payroll    = models.BooleanField(default=False)
    can_view_own_payslip    = models.BooleanField(default=True)
    can_manage_payroll_cfg  = models.BooleanField(default=False)

    # ── Leave ─────────────────────────────────────────────────
    can_view_leave       = models.BooleanField(default=True)
    can_request_leave    = models.BooleanField(default=True)
    can_approve_leave    = models.BooleanField(default=False)
    can_view_leave_report= models.BooleanField(default=False)

    # ── Stock ─────────────────────────────────────────────────
    can_view_stock    = models.BooleanField(default=False)
    can_add_stock     = models.BooleanField(default=False)
    can_edit_stock    = models.BooleanField(default=False)
    can_delete_stock  = models.BooleanField(default=False)
    can_stock_in_out  = models.BooleanField(default=False)

    # ── Tasks ─────────────────────────────────────────────────
    can_view_tasks        = models.BooleanField(default=True)
    can_assign_tasks      = models.BooleanField(default=False)
    can_manage_tasks      = models.BooleanField(default=False)
    can_view_task_report  = models.BooleanField(default=False)

    # ── Course / Result ───────────────────────────────────────
    can_view_courses      = models.BooleanField(default=False)
    can_manage_courses    = models.BooleanField(default=False)
    can_publish_results   = models.BooleanField(default=False)
    can_view_result_report= models.BooleanField(default=False)

    # ── Billing ───────────────────────────────────────────────
    can_view_billing      = models.BooleanField(default=False)
    can_generate_bills    = models.BooleanField(default=False)
    can_record_payment    = models.BooleanField(default=False)
    can_view_dues         = models.BooleanField(default=False)
    can_export_billing    = models.BooleanField(default=False)

    # ── Finance ───────────────────────────────────────────────
    can_view_finance   = models.BooleanField(default=False)
    can_manage_finance = models.BooleanField(default=False)

    # ── Events ────────────────────────────────────────────────
    can_view_events   = models.BooleanField(default=True)
    can_manage_events = models.BooleanField(default=False)

    # ── Complaints ────────────────────────────────────────────
    can_view_complaints   = models.BooleanField(default=True)
    can_manage_complaints = models.BooleanField(default=False)

    # ── HRMS ──────────────────────────────────────────────────
    can_view_hrms   = models.BooleanField(default=False)
    can_manage_hrms = models.BooleanField(default=False)

    # ── Branches ──────────────────────────────────────────────
    can_view_branches   = models.BooleanField(default=False)
    can_manage_branches = models.BooleanField(default=False)

    # ── Reports ───────────────────────────────────────────────
    can_view_reports   = models.BooleanField(default=False)
    can_export_reports = models.BooleanField(default=False)
    can_bulk_export    = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Staff Permission'
        verbose_name_plural = 'Staff Permissions'

    def __str__(self):
        return f"Permissions for {self.member.name}"
