import datetime
from decimal import Decimal
from management.models import LeaveReport, LeaveType, Organization, CustomUser, OrganizationShiftOverride
from django.db import models, transaction
from django.core.exceptions import ValidationError
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
    default_shift_start_time = models.TimeField(
        null=True, blank=True,
        help_text="Suggested check-in time for new members at this branch. Leave blank to use the organization default.",
    )
    default_shift_end_time = models.TimeField(
        null=True, blank=True,
        help_text="Suggested check-out time for new members at this branch. Leave blank to use the organization default.",
    )
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
    # Deprecated: superseded by `branches` (M2M) below, kept only so any code
    # still reading the old single value keeps working. Not written to by
    # new code — see `branches`.
    branch = models.ForeignKey(Branch, related_name='classifications', on_delete=models.SET_NULL, null=True, blank=True)
    branches = models.ManyToManyField(
        Branch, related_name='available_classifications', blank=True,
        help_text="Branches that can use this classification. Leave empty to make it available to all branches.",
    )
    default_shift_start_time = models.TimeField(
        null=True, blank=True,
        help_text="Suggested check-in time for new members in this classification. Leave blank to use the branch/organization default.",
    )
    default_shift_end_time = models.TimeField(
        null=True, blank=True,
        help_text="Suggested check-out time for new members in this classification. Leave blank to use the branch/organization default.",
    )
    name = models.CharField(max_length=200)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    objects = models.Manager()

    def __str__(self):
        return self.name

    def is_available_to_branch(self, branch_id):
        """No branches selected == available org-wide (all branches)."""
        if not branch_id:
            return True
        return not self.branches.exists() or self.branches.filter(pk=branch_id).exists()

    @property
    def primary_branch(self):
        """First of possibly-many available branches — for callers that need
        one single default branch (e.g. auto-populating another record's own
        `branch` FK). None for an org-wide (no branches selected) classification."""
        return self.branches.first()

    @property
    def primary_branch_id(self):
        branch = self.primary_branch
        return branch.id if branch else None


def resolve_default_shift(org, branch=None, classification=None):
    """The suggested (start, end) check-in/out time for a *new* member, in
    priority order: Classification default > Branch default > Organization
    default > hardcoded 9:00-17:00 fallback.

    This only decides what gets pre-filled at data-entry time — it never
    touches an existing member's own `shift_start_time`/`shift_end_time`,
    which always wins once set (see `member.shift_windows_detailed` for the
    separate, unrelated priority chain that resolves an *existing* member's
    actual daily schedule, including full Shift Management assignments)."""
    if classification is not None and classification.default_shift_start_time and classification.default_shift_end_time:
        return classification.default_shift_start_time, classification.default_shift_end_time
    if branch is not None and branch.default_shift_start_time and branch.default_shift_end_time:
        return branch.default_shift_start_time, branch.default_shift_end_time
    if org is not None and org.default_shift_start_time and org.default_shift_end_time:
        return org.default_shift_start_time, org.default_shift_end_time
    return datetime.time(9, 0), datetime.time(17, 0)


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


class Shift(models.Model):
    """A named work schedule made of one or more time windows (supports split shifts,
    e.g. 08:00–12:00 and 15:00–21:00)."""
    org = models.ForeignKey(Organization, related_name='shifts', on_delete=models.CASCADE)
    name = models.CharField(max_length=120)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('name',)

    def __str__(self):
        return f"{self.name} ({self.org.name})"

    def ordered_windows(self):
        return list(self.windows.order_by('order', 'start_time'))

    def expected_hours(self):
        """Total scheduled hours across all windows (excludes gaps between windows)."""
        total = 0.0
        for w in self.ordered_windows():
            total += w.duration_hours()
        return round(total, 2)

    def windows_display(self):
        return "  +  ".join(w.label() for w in self.ordered_windows())


class ShiftWindow(models.Model):
    shift = models.ForeignKey(Shift, related_name='windows', on_delete=models.CASCADE)
    order = models.PositiveIntegerField(default=1)
    start_time = models.TimeField()
    end_time = models.TimeField()

    class Meta:
        ordering = ('order', 'start_time')

    def __str__(self):
        return f"{self.shift.name}: {self.label()}"

    def duration_hours(self):
        s = datetime.datetime.combine(datetime.date.today(), self.start_time)
        e = datetime.datetime.combine(datetime.date.today(), self.end_time)
        if e <= s:  # overnight window
            e += datetime.timedelta(days=1)
        return (e - s).total_seconds() / 3600.0

    def label(self):
        return f"{self.start_time.strftime('%I:%M %p').lstrip('0')}–{self.end_time.strftime('%I:%M %p').lstrip('0')}"


class MemberWeekdayShift(models.Model):
    """The member's effective shift for one weekday (Sunday-first convention)."""

    WEEKDAY_CHOICES = (
        (0, 'Sunday'), (1, 'Monday'), (2, 'Tuesday'), (3, 'Wednesday'),
        (4, 'Thursday'), (5, 'Friday'), (6, 'Saturday'),
    )
    org = models.ForeignKey(Organization, related_name='member_weekday_shifts', on_delete=models.CASCADE)
    member = models.ForeignKey('member', related_name='weekday_shifts', on_delete=models.CASCADE)
    weekday = models.PositiveSmallIntegerField(choices=WEEKDAY_CHOICES)
    shift = models.ForeignKey(Shift, related_name='weekday_assignments', on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('member__name', 'weekday')
        constraints = [
            models.UniqueConstraint(
                fields=('member', 'weekday', 'shift'),
                name='unique_member_weekday_shift_row',
            ),
            models.CheckConstraint(
                check=models.Q(weekday__gte=0, weekday__lte=6),
                name='member_weekday_shift_valid_day',
            ),
        ]
        indexes = [models.Index(fields=('org', 'weekday'))]

    def clean(self):
        super().clean()
        if self.member_id and self.org_id != self.member.org_id:
            raise ValidationError({'member': 'Member must belong to this organization.'})
        if self.shift_id and self.org_id != self.shift.org_id:
            raise ValidationError({'shift': 'Shift must belong to this organization.'})

    def __str__(self):
        return f"{self.member.name} — {self.get_weekday_display()}: {self.shift.name}"


class MemberShiftOverride(models.Model):
    """A one-off extra shift for a member on a specific calendar date, added on
    top of (never replacing) the recurring weekday pattern in `MemberWeekdayShift`."""

    org = models.ForeignKey(Organization, related_name='member_shift_overrides', on_delete=models.CASCADE)
    member = models.ForeignKey('member', related_name='shift_overrides', on_delete=models.CASCADE)
    date = models.DateField(db_index=True)
    shift = models.ForeignKey(Shift, related_name='date_overrides', on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('member__name', 'date')
        constraints = [
            models.UniqueConstraint(
                fields=('member', 'date', 'shift'),
                name='unique_member_date_shift_row',
            ),
        ]
        indexes = [models.Index(fields=('org', 'date'))]

    def clean(self):
        super().clean()
        if self.member_id and self.org_id != self.member.org_id:
            raise ValidationError({'member': 'Member must belong to this organization.'})
        if self.shift_id and self.org_id != self.shift.org_id:
            raise ValidationError({'shift': 'Shift must belong to this organization.'})

    def __str__(self):
        return f"{self.member.name} — {self.date}: {self.shift.name} (extra)"


class DutyType(models.Model):
    """A named category of duty (e.g. "Regular", "On-Call", "Field Duty",
    "Overtime") recorded on a Duty Roster entry alongside a Shift. A Shift
    says WHEN (a time window); a DutyType says WHAT KIND — the two are
    independent, so a roster cell can carry either, both, or neither.
    `is_default` marks the one org-wide default pre-selected when building
    a new roster; only one should be flagged per org (enforced in the view
    that toggles it, not at the DB level, matching how `is_active` flags
    elsewhere in this codebase aren't DB-constrained either)."""

    org = models.ForeignKey(Organization, related_name='duty_types', on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    is_default = models.BooleanField(default=False, help_text="Pre-selected when building a new roster entry.")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('name',)
        unique_together = ('org', 'name')

    def __str__(self):
        return f"{self.name} ({self.org.name})"


class TemporaryShiftAssignment(models.Model):
    """Duty Roster: a temporary REPLACEMENT of a member's regular weekday
    pattern for a date range (e.g. covering a colleague's shift while they're
    on leave, or a planned rotation) — distinct from `MemberShiftOverride`,
    which only ever adds an extra shift on top of the pattern, never replaces
    it. `shift=None` means "off" for the whole range (e.g. planned leave)
    rather than falling back to the regular pattern.

    Takes priority over `MemberWeekdayShift`/`MemberShiftOverride` for any
    date inside [start_date, end_date] while `is_active=True`. `end_date=None`
    means open-ended ("ongoing until cancelled")."""

    org = models.ForeignKey(Organization, related_name='temporary_shift_assignments', on_delete=models.CASCADE)
    member = models.ForeignKey('member', related_name='temporary_shift_assignments', on_delete=models.CASCADE)
    start_date = models.DateField(db_index=True)
    end_date = models.DateField(null=True, blank=True, db_index=True, help_text="Leave blank for an open-ended (ongoing) change.")
    shift = models.ForeignKey(
        Shift, related_name='temporary_assignments', on_delete=models.PROTECT, null=True, blank=True,
        help_text="Leave blank to mark the member off-duty for this whole date range.",
    )
    duty_type = models.ForeignKey(
        DutyType, related_name='temporary_assignments', on_delete=models.SET_NULL, null=True, blank=True,
        help_text="What kind of duty this is (e.g. Regular, On-Call) - independent of the shift's time window.",
    )
    notes = models.CharField(max_length=255, blank=True, default='')
    is_active = models.BooleanField(default=True, help_text="Cancelled changes are kept (not deleted) so roster history stays intact.")
    created_by = models.ForeignKey(CustomUser, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-start_date',)
        indexes = [models.Index(fields=('org', 'member', 'is_active'))]

    def clean(self):
        super().clean()
        if self.member_id and self.org_id != self.member.org_id:
            raise ValidationError({'member': 'Member must belong to this organization.'})
        if self.shift_id and self.org_id != self.shift.org_id:
            raise ValidationError({'shift': 'Shift must belong to this organization.'})
        if self.duty_type_id and self.org_id != self.duty_type.org_id:
            raise ValidationError({'duty_type': 'Duty type must belong to this organization.'})
        if self.end_date and self.start_date and self.end_date < self.start_date:
            raise ValidationError({'end_date': 'End date cannot be before start date.'})

    def covers(self, target_date):
        return self.is_active and self.start_date <= target_date and (self.end_date is None or target_date <= self.end_date)

    def __str__(self):
        span = f"{self.start_date} → {self.end_date or 'ongoing'}"
        label = self.shift.name if self.shift else 'Off'
        if self.duty_type:
            label += f" / {self.duty_type.name}"
        return f"{self.member.name} — {span}: {label}"


def default_checkin_reminder_offsets():
    """Minutes after shift start used for missed check-in reminders."""
    return [0, 20, 30]


def default_checkout_reminder_offsets():
    """Minutes after shift end used for missed check-out reminders."""
    return [0, 15, 30]


class AttendanceReminderPolicy(models.Model):
    """Organisation-owned reminder timings consumed by web and mobile clients.

    Offsets stay server-side so reminder behaviour can be changed without
    publishing a new mobile build. Clients receive concrete ISO datetimes, not
    business rules.
    """

    org = models.OneToOneField(
        Organization,
        related_name='attendance_reminder_policy',
        on_delete=models.CASCADE,
    )
    enabled = models.BooleanField(default=True)
    checkin_enabled = models.BooleanField(default=True)
    checkout_enabled = models.BooleanField(default=True)
    checkin_offsets = models.JSONField(default=default_checkin_reminder_offsets)
    checkout_offsets = models.JSONField(default=default_checkout_reminder_offsets)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = 'attendance reminder policies'

    @staticmethod
    def normalize_offsets(value):
        if not isinstance(value, list):
            return []
        normalized = []
        for raw in value:
            if isinstance(raw, bool):
                continue
            try:
                minutes = int(raw)
            except (TypeError, ValueError):
                continue
            if 0 <= minutes <= 180 and minutes not in normalized:
                normalized.append(minutes)
        return sorted(normalized)[:3]

    def clean(self):
        super().clean()
        self.checkin_offsets = self.normalize_offsets(self.checkin_offsets)
        self.checkout_offsets = self.normalize_offsets(self.checkout_offsets)
        if self.checkin_enabled and not self.checkin_offsets:
            raise ValidationError({
                'checkin_offsets': 'Add at least one check-in reminder offset.'
            })
        if self.checkout_enabled and not self.checkout_offsets:
            raise ValidationError({
                'checkout_offsets': 'Add at least one check-out reminder offset.'
            })

    def __str__(self):
        return f"Attendance reminders — {self.org.name}"


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
        ('driver', 'Driver'),
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
        ('dumped', 'Dumped'),
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
    shifts = models.ManyToManyField('Shift', related_name='members', blank=True, help_text="One or more shifts. Their windows combine to form the member's daily schedule (supports split / multiple shifts).")
    live_tracking_enabled = models.BooleanField(default=False, help_text="Allow live GPS trail tracking for this member (field staff / marketers).")
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
    photo = models.ImageField(upload_to='member_photos', null=True, blank=True, help_text="Used on ID cards and profile.")
    roll_number = models.CharField(max_length=30, null=True, blank=True, help_text="Roll / registration number, shown on ID cards.")

    BLOOD_GROUP_CHOICES = (
        ('A+', 'A+'), ('A-', 'A-'), ('B+', 'B+'), ('B-', 'B-'),
        ('AB+', 'AB+'), ('AB-', 'AB-'), ('O+', 'O+'), ('O-', 'O-'),
    )
    designation = models.CharField(max_length=100, null=True, blank=True, help_text="Job title / role, shown on ID cards.")
    blood_group = models.CharField(max_length=5, choices=BLOOD_GROUP_CHOICES, null=True, blank=True)
    signature = models.ImageField(upload_to='member_signatures', null=True, blank=True, help_text="Signature image, shown on ID cards.")
    id_card_valid_until = models.DateField(null=True, blank=True, help_text="ID card expiry date.")

    # --- UPGRADED FEATURES ---
    salary_type = models.CharField(max_length=20, choices=SALARY_CHOICES, default='monthly')
    salary_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    salary_per_hour = models.IntegerField(default=15) # Kept for legacy fallback
    overtime_rate_multiplier_override = models.DecimalField(
        max_digits=4, decimal_places=2, null=True, blank=True,
        help_text="Per-member overtime multiplier override (e.g. 1.50 = 1.5x). Leave blank to use the org default.")
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
    previous_status = models.CharField(
        max_length=20, null=True, blank=True,
        help_text="Status held right before being dumped — restored on rejoin.",
    )
    archive_file = models.CharField(
        max_length=255, null=True, blank=True,
        help_text="Relative media path to the JSON archive of this member's records while dumped.",
    )

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
            

        
    def day_punch_times(self, target_date):
        """All punch times for a given date as ordered local (Nepal) `time` objects."""
        recs = self.member_record.filter(scanned_time__date=target_date).order_by('scanned_time')
        return [timezone.localtime(r.scanned_time).time() for r in recs]

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

    @staticmethod
    def weekday_number(target_date):
        """Convert Python's Monday-first weekday to Mero's Sunday-first value."""
        return (target_date.weekday() + 1) % 7

    def temporary_shift_assignment_for(self, target_date):
        """The Duty Roster change covering `target_date`, if any — takes
        priority over the regular weekday pattern. Most-recently-created wins
        if two ever overlap (e.g. a correction to an earlier entry)."""
        if not self.pk or target_date is None:
            return None
        return self.temporary_shift_assignments.filter(
            is_active=True, start_date__lte=target_date,
        ).filter(
            models.Q(end_date__isnull=True) | models.Q(end_date__gte=target_date),
        ).select_related('shift').order_by('-created_at').first()

    def active_shifts(self, target_date=None):
        """All active shifts assigned to this member. When `target_date` is given,
        a Duty Roster `TemporaryShiftAssignment` covering that date takes full
        priority (replacing, not adding to, the pattern below) — either a
        specific shift or `[]` for an explicit off-duty change. Otherwise this
        is the union of the recurring weekday shift(s) for that weekday and
        any one-off `MemberShiftOverride` shift(s) for that exact date."""
        if not self.pk:
            return []
        if target_date is not None:
            temp_assignment = self.temporary_shift_assignment_for(target_date)
            if temp_assignment is not None:
                return [temp_assignment.shift] if temp_assignment.shift_id else []
            seen = set()
            result = []
            weekday_rows = self.weekday_shifts.select_related('shift').filter(
                weekday=self.weekday_number(target_date), shift__is_active=True,
            ).order_by('shift__name')
            override_rows = self.shift_overrides.select_related('shift').filter(
                date=target_date, shift__is_active=True,
            ).order_by('shift__name')
            for row in list(weekday_rows) + list(override_rows):
                if row.shift_id not in seen:
                    seen.add(row.shift_id)
                    result.append(row.shift)
            if result:
                return result
            # Once a weekday schedule exists, an unassigned day is an off-day.
            if self.weekday_shifts.exists():
                return []
        return list(self.shifts.filter(is_active=True).order_by('name'))

    def has_active_shift(self, target_date=None):
        if not self.pk:
            return False
        if target_date is not None:
            temp_assignment = self.temporary_shift_assignment_for(target_date)
            if temp_assignment is not None:
                return temp_assignment.shift_id is not None
            if self.weekday_shifts.filter(
                weekday=self.weekday_number(target_date), shift__is_active=True,
            ).exists():
                return True
            if self.shift_overrides.filter(date=target_date, shift__is_active=True).exists():
                return True
            if self.weekday_shifts.exists():
                return False
        return self.shifts.filter(is_active=True).exists()

    def shift_windows_detailed(self, target_date=None):
        """Ordered [{'shift_id','shift_name','start_time','end_time'}, ...] combining
        the windows of every assigned active shift (weekday pattern + date overrides),
        or a single window from shift_start_time/shift_end_time when no shift is assigned
        (itself superseded by a company-wide `OrganizationShiftOverride` for `target_date`,
        if one exists — plain-default members only, members with a Shift Management
        assignment are governed entirely by the branches above). A Duty Roster
        `TemporaryShiftAssignment` covering `target_date` overrides everything,
        including a plain-default member's own shift_start_time/shift_end_time."""
        temp_assignment = self.temporary_shift_assignment_for(target_date) if target_date is not None else None
        wins = []
        for sh in self.active_shifts(target_date):
            for w in sh.ordered_windows():
                wins.append({
                    'shift_id': sh.id, 'shift_name': sh.name,
                    'start_time': w.start_time, 'end_time': w.end_time,
                })
        if wins:
            wins.sort(key=lambda w: w['start_time'])
            return wins
        if temp_assignment is not None:
            return []  # explicit off-duty change, regardless of Shift Management usage
        if target_date is not None and self.weekday_shifts.exists():
            return []
        start_t, end_t, label = self.shift_start_time, self.shift_end_time, None
        if target_date is not None and self.org_id:
            override = OrganizationShiftOverride.objects.filter(org_id=self.org_id, date=target_date).first()
            if override:
                start_t, end_t = override.start_time, override.end_time
                label = f"Company-wide change ({override.note})" if override.note else "Company-wide change"
        return [{
            'shift_id': None, 'shift_name': label,
            'start_time': start_t, 'end_time': end_t,
        }]

    def shift_windows(self, target_date=None):
        """Ordered [(start_time, end_time), ...] — see `shift_windows_detailed`."""
        return [(w['start_time'], w['end_time']) for w in self.shift_windows_detailed(target_date)]

    def shifts_display(self):
        names = [s.name for s in self.active_shifts()]
        return ", ".join(names) if names else "Default"

    def combined_windows_display(self):
        return "  +  ".join(
            f"{s.strftime('%I:%M %p').lstrip('0')}–{e.strftime('%I:%M %p').lstrip('0')}"
            for s, e in self.shift_windows()
        )

    def weekly_shifts_display(self):
        rows = self.weekday_shifts.select_related('shift').order_by('weekday', 'shift__name')
        if not rows:
            return self.shifts_display()
        by_day = {}
        for row in rows:
            by_day.setdefault(row.weekday, []).append(row.shift.name)
        day_labels = dict(MemberWeekdayShift.WEEKDAY_CHOICES)
        return ', '.join(
            f"{day_labels[day]}: {' + '.join(names)}" for day, names in sorted(by_day.items())
        )

    def effective_shift_start(self, target_date=None):
        """Start of the first shift window (the day's expected check-in), or
        None on a day with zero shift windows — a Shift-Management member's
        day off, or an explicit Duty Roster off-duty change (see
        `shift_windows_detailed`, both documented `return []` cases)."""
        windows = self.shift_windows(target_date)
        return windows[0][0] if windows else None

    def effective_shift_end(self, target_date=None):
        """End of the last shift window (the day's expected check-out), or
        None on a day with zero shift windows (see `effective_shift_start`)."""
        windows = self.shift_windows(target_date)
        return windows[-1][1] if windows else None

    def expected_daily_hours(self):
        """Total scheduled hours for the day (sum of window durations)."""
        total = 0.0
        for start, end in self.shift_windows():
            s = datetime.datetime.combine(datetime.date.today(), start)
            e = datetime.datetime.combine(datetime.date.today(), end)
            if e <= s:
                e += datetime.timedelta(days=1)
            total += (e - s).total_seconds() / 3600.0
        return round(total, 2)

    def late_in(self):
        """Calculates how late the member checked in"""
        actual_in = self.first_daily_time()
        expected_in = self.effective_shift_start(self.date)
        if actual_in and expected_in and actual_in > expected_in:
            return self.get_time_difference(actual_in, expected_in)
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
        expected_out = self.effective_shift_end(self.date)
        if actual_out and expected_out and actual_out < expected_out:
            return self.get_time_difference(expected_out, actual_out)
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


class MemberHistory(models.Model):
    """Append-only audit trail for profile, employment and academic changes."""

    member = models.ForeignKey(member, related_name='change_history', on_delete=models.CASCADE)
    org = models.ForeignKey(Organization, related_name='member_history', on_delete=models.CASCADE)
    action = models.CharField(max_length=80, default='profile_updated')
    field_name = models.CharField(max_length=100, blank=True)
    old_value = models.TextField(blank=True)
    new_value = models.TextField(blank=True)
    description = models.CharField(max_length=500, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    changed_by = models.ForeignKey(
        CustomUser, related_name='member_changes', on_delete=models.SET_NULL,
        null=True, blank=True,
    )
    changed_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ('-changed_at', '-id')
        indexes = [models.Index(fields=('org', 'member', 'changed_at'))]

    def __str__(self):
        return f"{self.member.name}: {self.description or self.action}"
    


class DailyNote(models.Model):
    """A short free-text note pinned to one member+date, added from the
    Monthly Report / Gap Report calendar view (e.g. "left early - doctor
    appointment", "forgot to punch out"). Purely informational — unlike
    LeaveReport, it never affects attendance/payroll calculations. One note
    per member+date; re-adding a note on the same day edits it in place."""

    member = models.ForeignKey(member, related_name='daily_notes', on_delete=models.CASCADE)
    org = models.ForeignKey(Organization, related_name='daily_notes', on_delete=models.CASCADE)
    date = models.DateField()
    text = models.CharField(max_length=500)
    created_by = models.ForeignKey(
        CustomUser, related_name='daily_notes_created', on_delete=models.SET_NULL,
        null=True, blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('member', 'date')
        ordering = ('-date',)
        indexes = [models.Index(fields=('org', 'member', 'date'))]

    def __str__(self):
        return f"{self.member.name} — {self.date}: {self.text[:40]}"


class MemberFace(models.Model):
    """Stores enrolled face descriptors (128-float vectors from face-api.js) for a
    member, used for client-side facial-recognition attendance."""
    member = models.OneToOneField(member, related_name='face_profile', on_delete=models.CASCADE)
    org = models.ForeignKey(Organization, related_name='member_faces', on_delete=models.CASCADE)
    descriptors = models.JSONField(default=list, help_text="List of 128-float face descriptors (one per enrolled sample).")
    sample_image = models.ImageField(upload_to='member_faces/', null=True, blank=True)
    enrolled_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def sample_count(self):
        try:
            return len(self.descriptors or [])
        except Exception:
            return 0

    def __str__(self):
        return f"Face profile — {self.member.name}"


class LocationPing(models.Model):
    """A single live-location sample used to build a member's travel trail."""
    member = models.ForeignKey(member, related_name='location_pings', on_delete=models.CASCADE)
    org = models.ForeignKey(Organization, related_name='location_pings', on_delete=models.CASCADE)
    session = models.ForeignKey(
        'LiveTrackingSession',
        related_name='pings',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    latitude = models.FloatField()
    longitude = models.FloatField()
    accuracy_meters = models.FloatField(null=True, blank=True)
    ping_type = models.CharField(
        max_length=20,
        choices=(
            ('regular', 'Regular'),
            ('break_start', 'Break start'),
            ('break_end', 'Break end'),
            ('checkpoint', 'Checkpoint'),
        ),
        default='regular',
    )
    battery_percentage = models.PositiveSmallIntegerField(null=True, blank=True)
    tracked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('tracked_at',)
        indexes = [models.Index(fields=['member', 'tracked_at'])]

    def __str__(self):
        return f"{self.member.name} @ ({self.latitude}, {self.longitude}) {self.tracked_at:%Y-%m-%d %H:%M}"


class LiveTrackingSession(models.Model):
    """A user-visible start/stop boundary grouping authorised location pings."""

    STATUS_CHOICES = (
        ('active', 'Active'),
        ('stopped', 'Stopped'),
    )
    org = models.ForeignKey(
        Organization,
        related_name='live_tracking_sessions',
        on_delete=models.CASCADE,
    )
    member = models.ForeignKey(
        member,
        related_name='live_tracking_sessions',
        on_delete=models.CASCADE,
    )
    started_by = models.ForeignKey(
        CustomUser,
        related_name='started_live_tracking_sessions',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='active')
    started_at = models.DateTimeField(auto_now_add=True)
    stopped_at = models.DateTimeField(null=True, blank=True)
    break_started_at = models.DateTimeField(null=True, blank=True)
    last_ping_at = models.DateTimeField(null=True, blank=True)
    last_latitude = models.FloatField(null=True, blank=True)
    last_longitude = models.FloatField(null=True, blank=True)

    class Meta:
        ordering = ('-started_at',)
        indexes = [
            models.Index(fields=['org', 'member', 'status']),
        ]

    def __str__(self):
        return f"{self.member.name} — {self.started_at:%Y-%m-%d %H:%M} ({self.status})"


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
    overtime_hours = models.DecimalField(max_digits=8, decimal_places=4, default=Decimal('0'))
    overtime_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    overtime_rate_multiplier = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('1.00'))
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
    payment_date = models.DateField(null=True, blank=True)
    notes = models.TextField(null=True, blank=True)
    journal_entry = models.ForeignKey('JournalEntry', related_name='+', on_delete=models.SET_NULL, null=True, blank=True,
                                       help_text="Payroll accrual entry (Dr Salary Expense / Cr Salary Payable), posted when finalized.")
    payment_journal_entry = models.ForeignKey('JournalEntry', related_name='+', on_delete=models.SET_NULL, null=True, blank=True,
                                               help_text="Payroll payment entry (Dr Salary Payable / Cr Cash-Bank), posted when marked paid.")

    class Meta:
        ordering = ('-from_date', '-id')
        constraints = [
            models.UniqueConstraint(
                fields=['member', 'org', 'from_date', 'to_date'],
                name='unique_payslip_per_member_period',
            )
        ]

    def __str__(self):
        return f"Payslip: {self.member.name} - {self.month_name}"


class PayrollPolicy(models.Model):
    org = models.OneToOneField(Organization, related_name='payroll_policy', on_delete=models.CASCADE)
    pf_employee_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('10.00'))
    pf_employer_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('10.00'))
    ssf_employee_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('11.00'))
    ssf_employer_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('20.00'))
    probation_salary_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('80.00'))
    probation_leave_cut_enabled = models.BooleanField(default=True)
    probation_reminder_days = models.PositiveIntegerField(default=7)
    overtime_rate_multiplier = models.DecimalField(
        max_digits=4, decimal_places=2, default=Decimal('1.50'),
        help_text="Default overtime pay multiplier (e.g. 1.50 = 1.5x normal hourly rate)")
    late_grace_minutes = models.PositiveIntegerField(
        default=0,
        help_text="Grace period for late check-in (minutes). Lateness within this window is not deducted from salary.")
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
    journal_entry = models.ForeignKey('JournalEntry', related_name='+', on_delete=models.SET_NULL, null=True, blank=True)
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

    def apply_installment(self, payslip=None):
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
        AdvanceInstallmentPayment.objects.create(
            advance=self, payslip=payslip, amount=self.installment_amount,
        )


class AdvanceInstallmentPayment(models.Model):
    """One row per installment actually applied to an AdvanceSalary, so admins can see
    a paid-on date history instead of just a cumulative counter/balance."""
    advance = models.ForeignKey(AdvanceSalary, on_delete=models.CASCADE, related_name='payments')
    payslip = models.ForeignKey('PaySlip', on_delete=models.SET_NULL, null=True, blank=True, related_name='advance_payments')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    paid_on = models.DateField(default=timezone.localdate)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-paid_on', '-id')

    def __str__(self):
        return f"{self.advance.member.name} — {self.amount} on {self.paid_on}"


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
    CONNECTION_MODE_CHOICES = (
        ('pull', 'Local SDK / Puller'),
        ('adms', 'ADMS Cloud Push'),
    )

    org = models.ForeignKey(Organization, on_delete=models.CASCADE, null = True)
    name = models.CharField(max_length=200)
    ip_address = models.CharField(max_length=255, blank=True, default='')
    port_no = models.IntegerField(default=4370)
    connection_mode = models.CharField(
        max_length=10,
        choices=CONNECTION_MODE_CHOICES,
        default='pull',
    )
    serial_number = models.CharField(
        max_length=100,
        unique=True,
        null=True,
        blank=True,
        help_text='Device serial number (SN) shown in Device Information.',
    )
    last_seen_at = models.DateTimeField(null=True, blank=True)
    last_push_at = models.DateTimeField(null=True, blank=True)
    last_ip_address = models.GenericIPAddressField(null=True, blank=True)
    push_version = models.CharField(max_length=50, blank=True, default='')

    def __str__(self):
        return f"{self.org}- {self.name}"

    def save(self, *args, **kwargs):
        self.serial_number = (
            self.serial_number.strip().upper()
            if self.serial_number else None
        )
        super().save(*args, **kwargs)

    @property
    def is_online(self):
        if not self.last_seen_at:
            return False
        return self.last_seen_at >= timezone.now() - datetime.timedelta(minutes=5)


class ADMSAttendanceEvent(models.Model):
    STATUS_CHOICES = (
        ('stored', 'Stored'),
        ('unmatched', 'Unmatched member'),
        ('ambiguous', 'Ambiguous member PIN'),
        ('inactive', 'Inactive member'),
        ('invalid', 'Invalid row'),
    )

    device = models.ForeignKey(
        Device,
        on_delete=models.CASCADE,
        related_name='adms_events',
    )
    org = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='adms_events',
    )
    member = models.ForeignKey(
        member,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='adms_events',
    )
    attendance_record = models.ForeignKey(
        'AttendanceRecord',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='adms_events',
    )
    event_hash = models.CharField(max_length=64)
    device_user_id = models.CharField(max_length=50, blank=True)
    event_time = models.DateTimeField(null=True, blank=True)
    punch_state = models.CharField(max_length=20, blank=True)
    verify_mode = models.CharField(max_length=20, blank=True)
    work_code = models.CharField(max_length=50, blank=True)
    status = models.CharField(
        max_length=12,
        choices=STATUS_CHOICES,
        default='stored',
    )
    raw_payload = models.TextField(blank=True)
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-received_at', '-id')
        constraints = [
            models.UniqueConstraint(
                fields=('device', 'event_hash'),
                name='unique_adms_event_per_device',
            ),
        ]
        indexes = [
            models.Index(fields=('org', 'received_at')),
            models.Index(fields=('device_user_id', 'event_time')),
        ]

    def __str__(self):
        return f'{self.device} / {self.device_user_id} / {self.status}'



class AttendanceRecord(models.Model):
    ATTENDANCE_METHOD_CHOICES = (
        ('manual', 'Manual'),
        ('biometric', 'Biometric/RFID'),
        ('gps', 'GPS'),
        ('wifi', 'WiFi'),
        ('qr', 'QR Attendance'),
        ('facial', 'Facial Recognition'),
        ('auto', 'Auto Checkin'),
        ('field_visit', 'Field Visit Approval'),
    )
    mem = models.ForeignKey(member, related_name="member_record", on_delete=models.CASCADE)
    org = models.ForeignKey(Organization, on_delete=models.CASCADE, null=True)
    scanned_time = models.DateTimeField()
    got_time = datetime.datetime.today()
    scanned_time_np = models.CharField(max_length=50, blank=True)  # Store Nepali datetime as string
    attendance_method = models.CharField(max_length=20, blank=True, default='', choices=ATTENDANCE_METHOD_CHOICES)
    field_visit = models.ForeignKey('FieldVisit', on_delete=models.SET_NULL, null=True, blank=True, related_name='attendance_records')
    
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
    journal_entry = models.ForeignKey('JournalEntry', related_name='+', on_delete=models.SET_NULL, null=True, blank=True)
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
            previous.item.quantity = Decimal(str(previous.item.quantity)) - previous.signed_quantity()
            previous.item.save(update_fields=['quantity', 'updated_at'])
        self.item.quantity = Decimal(str(self.item.quantity)) + self.signed_quantity()
        self.item.save(update_fields=['quantity', 'updated_at'])

    def signed_quantity(self):
        qty = Decimal(str(self.quantity))
        if self.movement_type in ('in', 'adjustment'):
            return qty
        return -qty

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
    journal_entry = models.ForeignKey('JournalEntry', related_name='+', on_delete=models.SET_NULL, null=True, blank=True)
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
    """A subject inside a course/program, scoped to a class and optionally a section."""
    STATUS_CHOICES = (('active', 'Active'), ('inactive', 'Inactive'))

    org = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="org_subjects")
    course = models.ForeignKey(
        Course,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='subjects',
        help_text="Parent course/program, for example BSc Computing or Class 9.",
    )
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
        unique_together = ('org', 'course', 'classification', 'section', 'name')
        ordering = ('classification', 'name')

    def __str__(self):
        course_name = f"{self.course.name} / " if self.course else ""
        base = f"{course_name}{self.name} — {self.classification.name}"
        return f"{base} ({self.section.name})" if self.section else base

    def clean(self):
        errors = {}
        if self.course_id:
            if self.course.org_id != self.org_id:
                errors['course'] = "Course must belong to the subject organization."
            elif self.classification_id and not self.course.classifications.filter(
                pk=self.classification_id
            ).exists():
                errors['classification'] = "Classification must be linked to the selected course."
        if self.classification_id and self.classification.org_id != self.org_id:
            errors['classification'] = "Classification must belong to the subject organization."
        if self.section_id:
            if (
                self.section.org_id != self.org_id
                or self.section.classification_id != self.classification_id
            ):
                errors['section'] = "Section must belong to the selected classification and organization."
            elif self.course_id and self.course.sections.exists() and not self.course.sections.filter(
                pk=self.section_id
            ).exists():
                errors['section'] = "Section must be linked to the selected course."
        if self.teacher_id:
            staff_org_id = Staff.objects.filter(
                admin_id=self.teacher_id
            ).values_list('org_id', flat=True).first()
            if staff_org_id != self.org_id:
                errors['teacher'] = "Teacher must belong to the subject organization."
        if errors:
            raise ValidationError(errors)


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
        elif self.obtained_marks < 0:
            raise ValidationError({'obtained_marks': "Marks cannot be negative."})
        elif self.subject_id and self.obtained_marks > self.subject.full_marks:
            raise ValidationError({
                'obtained_marks': f"Marks cannot exceed {self.subject.full_marks}."
            })
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
        ('in_progress', 'In Progress'),
        ('resolved', 'Resolved'),
        ('rejected', 'Rejected'),
        ('closed', 'Closed'),
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


class ComplaintMessage(models.Model):
    complaint = models.ForeignKey(
        Complaint,
        related_name='messages',
        on_delete=models.CASCADE,
    )
    author = models.ForeignKey(
        CustomUser,
        related_name='complaint_messages',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    message = models.TextField()
    attachment = models.FileField(
        upload_to='complaint_evidence/',
        null=True,
        blank=True,
    )
    is_staff_reply = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('created_at',)

    def __str__(self):
        return f"Complaint #{self.complaint_id} message"


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
# FIELD VISITS (send-my-location for field staff)
# =============================================================

class FieldVisit(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    )

    org = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='field_visits')
    member = models.ForeignKey('member', on_delete=models.CASCADE, related_name='field_visits')
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    end_latitude = models.FloatField(null=True, blank=True)
    end_longitude = models.FloatField(null=True, blank=True)
    area_name = models.CharField(max_length=300, blank=True, help_text="Reverse-geocoded address / area name of the shared location.")
    accuracy_meters = models.FloatField(null=True, blank=True)
    client = models.ForeignKey('Client', on_delete=models.SET_NULL, null=True, blank=True, related_name='field_visits', help_text="Optional client visited on this trip.")
    purpose = models.CharField(max_length=300, blank=True)
    destination = models.CharField(max_length=300, blank=True)
    scheduled_for = models.DateTimeField(null=True, blank=True)
    visit_state = models.CharField(
        max_length=20,
        choices=(
            ('not_started', 'Not Started'),
            ('in_progress', 'In Progress'),
            ('completed', 'Completed'),
            ('cancelled', 'Cancelled'),
        ),
        default='completed',
    )
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    visited_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey('management.CustomUser', on_delete=models.SET_NULL, null=True, blank=True, related_name='created_field_visits')

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    reviewed_by = models.ForeignKey('management.CustomUser', on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_field_visits')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ('-visited_at',)

    def __str__(self):
        return f"{self.member.name} @ ({self.latitude}, {self.longitude}) on {self.visited_at:%Y-%m-%d %H:%M}"


class FieldVisitReport(models.Model):
    visit = models.OneToOneField(FieldVisit, on_delete=models.CASCADE, related_name='report')
    note = models.TextField(blank=True)
    attachment = models.FileField(upload_to='field_visit_reports/', null=True, blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Report for {self.visit}"


# =============================================================
# CLIENT FOLLOW-UP MODULE (CRM-lite)
# =============================================================

class Client(models.Model):
    STATUS_CHOICES = (
        ('inquiry', 'Inquiry'),
        ('customer', 'Customer'),
    )
    PRIORITY_CHOICES = (
        ('high', 'High'),
        ('medium', 'Medium'),
        ('low', 'Low'),
    )
    BILLING_CYCLE_CHOICES = (
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('yearly', 'Yearly'),
        ('one_time', 'One Time'),
    )

    org = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='clients')
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name='clients')
    client_number = models.CharField(max_length=50)
    client_org_name = models.CharField(max_length=300)
    contact_person = models.CharField(max_length=200, blank=True)
    phone = models.BigIntegerField(null=True, blank=True)
    email = models.EmailField(null=True, blank=True)
    address = models.CharField(max_length=300, blank=True)
    website = models.CharField(max_length=255, blank=True)
    industry = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    # CRM billing fields
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='inquiry')
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium')
    billing_cycle = models.CharField(max_length=20, choices=BILLING_CYCLE_CHOICES, null=True, blank=True)
    billing_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    contract_start = models.DateField(null=True, blank=True)
    contract_end = models.DateField(null=True, blank=True)
    next_billing_date = models.DateField(null=True, blank=True)
    monthly_target = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    yearly_target = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    created_by = models.ForeignKey('management.CustomUser', on_delete=models.SET_NULL, null=True, blank=True, related_name='created_clients')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ('client_org_name',)
        constraints = [
            models.UniqueConstraint(fields=['org', 'client_number'], name='unique_client_number_per_org'),
        ]
        indexes = [
            models.Index(fields=['org', 'branch', 'status'], name='client_org_branch_status_idx'),
            models.Index(fields=['org', 'priority'], name='client_org_priority_idx'),
        ]

    def __str__(self):
        return f"{self.client_number} — {self.client_org_name}"

    @classmethod
    def create_for_org(cls, *, org, client_number=None, **kwargs):
        """Create a client with a concurrency-safe organisation number.

        Locking the organisation serializes number allocation without adding
        a second counter table. Manually supplied legacy numbers remain
        supported and are checked under the same lock.
        """
        with transaction.atomic():
            locked_org = Organization.objects.select_for_update().get(pk=org.pk)
            number = (client_number or '').strip()
            if number:
                if cls.objects.filter(org=locked_org, client_number=number).exists():
                    raise ValidationError({'client_number': f"Client number '{number}' already exists."})
            else:
                prefix = 'CLI-'
                highest = 0
                for existing in cls.objects.filter(
                    org=locked_org, client_number__startswith=prefix,
                ).values_list('client_number', flat=True):
                    suffix = existing[len(prefix):]
                    if suffix.isdigit():
                        highest = max(highest, int(suffix))
                number = f'{prefix}{highest + 1:05d}'
            return cls.objects.create(
                org=locked_org, client_number=number, **kwargs,
            )

    @property
    def can_be_billed(self):
        return self.status == 'customer'

    def follow_up_count(self):
        return self.follow_ups.count()

    def latest_follow_up(self):
        return self.follow_ups.order_by('-follow_up_date', '-id').first()

    def total_sales(self):
        return self.sales.exclude(status='cancelled').aggregate(t=models.Sum('total_amount'))['t'] or Decimal('0.00')

    def total_returns(self):
        return self.sales_returns.filter(status='completed').aggregate(t=models.Sum('total_amount'))['t'] or Decimal('0.00')

    def total_paid(self):
        return self.sale_payments.aggregate(t=models.Sum('amount'))['t'] or Decimal('0.00')

    def outstanding_balance(self):
        return self.total_sales() - self.total_returns() - self.total_paid()

    def recent_transactions(self, limit=10):
        """Chronological merge of Sale/SalesReturn/SalePayment rows, newest first."""
        rows = []
        for s in self.sales.all():
            rows.append({'date': s.sale_date, 'kind': 'Sale', 'ref': s, 'amount': s.total_amount})
        for r in self.sales_returns.filter(status='completed'):
            rows.append({'date': r.return_date, 'kind': 'Return', 'ref': r, 'amount': -r.total_amount})
        for p in self.sale_payments.all():
            rows.append({'date': p.payment_date, 'kind': 'Payment', 'ref': p, 'amount': -p.amount})
        rows.sort(key=lambda r: r['date'], reverse=True)
        return rows[:limit]


class ClientFollowUp(models.Model):
    PRIORITY_CHOICES = Client.PRIORITY_CHOICES
    STATUS_CHOICES = (
        ('open', 'Open'),
        ('closed', 'Closed'),
    )

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='follow_ups')
    org = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='client_follow_ups')
    visited_by = models.ForeignKey('member', on_delete=models.SET_NULL, null=True, blank=True, related_name='client_follow_ups')
    feedback = models.TextField()
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='open')
    follow_up_date = models.DateField()
    next_follow_up_date = models.DateField(null=True, blank=True)
    field_visit = models.ForeignKey('FieldVisit', on_delete=models.SET_NULL, null=True, blank=True, related_name='follow_ups', help_text="The field visit (GPS location) this follow-up was logged from, if any.")
    created_by = models.ForeignKey('management.CustomUser', on_delete=models.SET_NULL, null=True, blank=True, related_name='created_follow_ups')
    created_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey('management.CustomUser', on_delete=models.SET_NULL, null=True, blank=True, related_name='closed_follow_ups')

    class Meta:
        ordering = ('-follow_up_date', '-id')
        indexes = [
            models.Index(fields=['org', 'priority', 'next_follow_up_date']),
            models.Index(fields=['org', 'status']),
        ]

    def __str__(self):
        return f"{self.client.client_org_name} follow-up on {self.follow_up_date}"


class Supplier(models.Model):
    """A vendor Purchases are made from. Can be created standalone or
    converted from an existing Client (source_client traces that origin —
    the Client row itself is never mutated by the conversion)."""
    STATUS_CHOICES = (
        ('active', 'Active'),
        ('inactive', 'Inactive'),
    )

    org = models.ForeignKey(Organization, related_name='suppliers', on_delete=models.CASCADE)
    branch = models.ForeignKey(Branch, related_name='suppliers', on_delete=models.SET_NULL, null=True, blank=True)
    source_client = models.ForeignKey(Client, related_name='supplier_profile', on_delete=models.SET_NULL, null=True, blank=True)
    supplier_number = models.CharField(max_length=50, blank=True)
    name = models.CharField(max_length=300)
    contact_person = models.CharField(max_length=200, blank=True)
    phone = models.BigIntegerField(null=True, blank=True)
    mobile = models.BigIntegerField(null=True, blank=True)
    email = models.EmailField(null=True, blank=True)
    website = models.CharField(max_length=255, blank=True)
    pan_vat_number = models.CharField(max_length=50, blank=True, verbose_name="PAN/VAT Number")
    registration_number = models.CharField(max_length=50, blank=True)
    address = models.CharField(max_length=300, blank=True)
    country = models.CharField(max_length=100, blank=True, default='Nepal')
    province = models.CharField(max_length=100, blank=True)
    district = models.CharField(max_length=100, blank=True)
    municipality = models.CharField(max_length=100, blank=True)
    bank_name = models.CharField(max_length=200, blank=True)
    bank_account_number = models.CharField(max_length=100, blank=True)
    bank_branch = models.CharField(max_length=200, blank=True)
    payment_terms = models.CharField(max_length=100, blank=True, help_text="e.g. Net 30")
    credit_limit = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    opening_balance = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    created_by = models.ForeignKey(CustomUser, related_name='suppliers_created', on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('name',)

    def __str__(self):
        return self.name

    def total_purchases(self):
        return self.purchases.exclude(status='cancelled').aggregate(t=models.Sum('total_amount'))['t'] or Decimal('0.00')

    def total_returns(self):
        return self.returns.filter(status='completed').aggregate(t=models.Sum('total_amount'))['t'] or Decimal('0.00')

    def total_paid(self):
        return self.payments.aggregate(t=models.Sum('amount'))['t'] or Decimal('0.00')

    def outstanding_balance(self):
        return self.opening_balance + self.total_purchases() - self.total_returns() - self.total_paid()


class SupplierDocument(models.Model):
    org = models.ForeignKey(Organization, related_name='supplier_documents', on_delete=models.CASCADE)
    supplier = models.ForeignKey(Supplier, related_name='documents', on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    doc_type = models.CharField(max_length=50, blank=True, default='other')
    file = models.FileField(upload_to='supplier_documents/')
    uploaded_by = models.ForeignKey(CustomUser, related_name='supplier_documents_uploaded', on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-created_at',)

    def __str__(self):
        return self.title


class SupplierPayment(models.Model):
    PAYMENT_METHOD_CHOICES = (
        ('cash', 'Cash'),
        ('bank', 'Bank'),
        ('card', 'Card'),
        ('online', 'Online'),
        ('other', 'Other'),
    )

    org = models.ForeignKey(Organization, related_name='supplier_payments', on_delete=models.CASCADE)
    branch = models.ForeignKey(Branch, related_name='supplier_payments', on_delete=models.SET_NULL, null=True, blank=True)
    supplier = models.ForeignKey(Supplier, related_name='payments', on_delete=models.CASCADE)
    purchase = models.ForeignKey(
        'Purchase', related_name='allocated_payments', on_delete=models.SET_NULL, null=True, blank=True,
        help_text="Optionally tie this payment to one specific bill, instead of just the supplier's running balance.",
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_date = models.DateField(default=timezone.localdate)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, default='cash')
    reference_number = models.CharField(max_length=120, blank=True)
    note = models.TextField(blank=True)
    journal_entry = models.ForeignKey('JournalEntry', related_name='+', on_delete=models.SET_NULL, null=True, blank=True)
    created_by = models.ForeignKey(CustomUser, related_name='supplier_payments_created', on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-payment_date', '-id')

    def clean(self):
        super().clean()
        if self.purchase_id and self.supplier_id and self.purchase.supplier_id != self.supplier_id:
            raise ValidationError({'purchase': 'That bill belongs to a different supplier.'})

    def __str__(self):
        return f"Payment #{self.pk} — {self.supplier.name} — Rs.{self.amount}"


class Purchase(models.Model):
    STATUS_CHOICES = (
        ('draft', 'Draft'),
        ('received', 'Received'),
        ('paid', 'Paid'),
        ('cancelled', 'Cancelled'),
    )
    PAYMENT_METHOD_CHOICES = (
        ('cash', 'Cash'),
        ('bank', 'Bank'),
        ('card', 'Card'),
        ('online', 'Online'),
        ('other', 'Other'),
    )

    org = models.ForeignKey(Organization, related_name='purchases', on_delete=models.CASCADE)
    branch = models.ForeignKey(Branch, related_name='purchases', on_delete=models.SET_NULL, null=True, blank=True)
    supplier = models.ForeignKey(Supplier, related_name='purchases', on_delete=models.PROTECT)
    purchase_date = models.DateField(default=timezone.localdate)
    due_date = models.DateField(null=True, blank=True, help_text="When payment to the supplier is due for this specific bill.")
    invoice_number = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, default='cash')
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    notes = models.TextField(blank=True)
    attachment = models.FileField(upload_to='purchase_bills/', null=True, blank=True, help_text="Scanned bill / invoice document from the supplier.")
    journal_entry = models.ForeignKey('JournalEntry', related_name='purchase_source', on_delete=models.SET_NULL, null=True, blank=True)
    created_by = models.ForeignKey(CustomUser, related_name='purchases_created', on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('-purchase_date', '-id')

    def __str__(self):
        return f"Purchase #{self.pk} — {self.supplier.name}"

    def recalc_totals(self):
        self.subtotal = self.items.aggregate(t=models.Sum('line_total'))['t'] or Decimal('0.00')
        self.total_amount = self.subtotal - self.discount_amount + self.tax_amount
        self.save(update_fields=['subtotal', 'total_amount', 'updated_at'])

    @property
    def paid_amount(self):
        """Sum of SupplierPayment rows explicitly allocated to this bill.
        A supplier payment doesn't have to be allocated to any specific
        purchase (see Supplier.outstanding_balance for the running-account
        view) — this only reflects payments someone chose to tie to this
        exact bill."""
        return self.allocated_payments.aggregate(t=models.Sum('amount'))['t'] or Decimal('0.00')

    @property
    def due_amount(self):
        return max(self.total_amount - self.paid_amount, Decimal('0.00'))

    @property
    def payment_status(self):
        if self.status == 'cancelled':
            return 'Cancelled'
        paid = self.paid_amount
        if paid <= Decimal('0.00'):
            return 'Unpaid'
        if paid >= self.total_amount:
            return 'Paid'
        return 'Partial'


class PurchaseItem(models.Model):
    purchase = models.ForeignKey(Purchase, related_name='items', on_delete=models.CASCADE)
    stock_item = models.ForeignKey(StockItem, related_name='purchase_items', on_delete=models.SET_NULL, null=True, blank=True)
    description = models.CharField(max_length=255, blank=True)
    quantity = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('1.00'))
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    line_total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))

    def __str__(self):
        return self.description or (self.stock_item.name if self.stock_item else f"Line #{self.pk}")

    def save(self, *args, **kwargs):
        self.line_total = Decimal(str(self.quantity)) * Decimal(str(self.unit_cost))
        super().save(*args, **kwargs)


class PurchaseReturn(models.Model):
    STATUS_CHOICES = (
        ('draft', 'Draft'),
        ('completed', 'Completed'),
    )

    org = models.ForeignKey(Organization, related_name='purchase_returns', on_delete=models.CASCADE)
    branch = models.ForeignKey(Branch, related_name='purchase_returns', on_delete=models.SET_NULL, null=True, blank=True)
    purchase = models.ForeignKey(Purchase, related_name='returns', on_delete=models.CASCADE)
    supplier = models.ForeignKey(Supplier, related_name='returns', on_delete=models.PROTECT)
    return_date = models.DateField(default=timezone.localdate)
    reason = models.CharField(max_length=255, blank=True)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    journal_entry = models.ForeignKey('JournalEntry', related_name='+', on_delete=models.SET_NULL, null=True, blank=True)
    created_by = models.ForeignKey(CustomUser, related_name='purchase_returns_created', on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('-return_date', '-id')

    def __str__(self):
        return f"Return #{self.pk} — Purchase #{self.purchase_id}"

    def recalc_totals(self):
        self.subtotal = self.items.aggregate(t=models.Sum('line_total'))['t'] or Decimal('0.00')
        self.total_amount = self.subtotal
        self.save(update_fields=['subtotal', 'total_amount', 'updated_at'])


class PurchaseReturnItem(models.Model):
    return_doc = models.ForeignKey(PurchaseReturn, related_name='items', on_delete=models.CASCADE)
    purchase_item = models.ForeignKey(PurchaseItem, related_name='return_items', on_delete=models.SET_NULL, null=True, blank=True)
    stock_item = models.ForeignKey(StockItem, related_name='purchase_return_items', on_delete=models.SET_NULL, null=True, blank=True)
    quantity = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('1.00'))
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    line_total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))

    def __str__(self):
        return self.stock_item.name if self.stock_item else f"Line #{self.pk}"

    def save(self, *args, **kwargs):
        self.line_total = Decimal(str(self.quantity)) * Decimal(str(self.unit_cost))
        super().save(*args, **kwargs)


class Sale(models.Model):
    STATUS_CHOICES = (
        ('draft', 'Draft'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    )
    PAYMENT_STATUS_CHOICES = (
        ('paid', 'Paid'),
        ('partial', 'Partial'),
        ('unpaid', 'Unpaid'),
    )
    PAYMENT_METHOD_CHOICES = Purchase.PAYMENT_METHOD_CHOICES

    org = models.ForeignKey(Organization, related_name='sales', on_delete=models.CASCADE)
    branch = models.ForeignKey(Branch, related_name='sales', on_delete=models.SET_NULL, null=True, blank=True)
    client = models.ForeignKey(Client, related_name='sales', on_delete=models.SET_NULL, null=True, blank=True)
    customer_name = models.CharField(max_length=200, blank=True, help_text="Used when there's no linked Client (walk-in sale).")
    sale_date = models.DateField(default=timezone.localdate)
    invoice_number = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='unpaid')
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, default='cash')
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    notes = models.TextField(blank=True)
    journal_entry = models.ForeignKey('JournalEntry', related_name='sale_source', on_delete=models.SET_NULL, null=True, blank=True)
    created_by = models.ForeignKey(CustomUser, related_name='sales_created', on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('-sale_date', '-id')

    def __str__(self):
        return f"Sale #{self.pk} — {self.client.client_org_name if self.client else self.customer_name or 'Walk-in'}"

    def recalc_totals(self):
        self.subtotal = self.items.aggregate(t=models.Sum('line_total'))['t'] or Decimal('0.00')
        self.total_amount = self.subtotal + self.tax_amount
        self.save(update_fields=['subtotal', 'total_amount', 'updated_at'])


class SaleItem(models.Model):
    sale = models.ForeignKey(Sale, related_name='items', on_delete=models.CASCADE)
    stock_item = models.ForeignKey(StockItem, related_name='sale_items', on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('1.00'))
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    line_total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))

    def __str__(self):
        return f"{self.stock_item.name} x{self.quantity}"

    def save(self, *args, **kwargs):
        self.line_total = Decimal(str(self.quantity)) * Decimal(str(self.unit_price))
        super().save(*args, **kwargs)


class SalePayment(models.Model):
    PAYMENT_METHOD_CHOICES = Purchase.PAYMENT_METHOD_CHOICES

    org = models.ForeignKey(Organization, related_name='sale_payments', on_delete=models.CASCADE)
    branch = models.ForeignKey(Branch, related_name='sale_payments', on_delete=models.SET_NULL, null=True, blank=True)
    sale = models.ForeignKey(Sale, related_name='payments', on_delete=models.CASCADE)
    client = models.ForeignKey(Client, related_name='sale_payments', on_delete=models.SET_NULL, null=True, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_date = models.DateField(default=timezone.localdate)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, default='cash')
    reference_number = models.CharField(max_length=120, blank=True)
    note = models.TextField(blank=True)
    journal_entry = models.ForeignKey('JournalEntry', related_name='+', on_delete=models.SET_NULL, null=True, blank=True)
    created_by = models.ForeignKey(CustomUser, related_name='sale_payments_created', on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-payment_date', '-id')

    def __str__(self):
        return f"Payment #{self.pk} — Sale #{self.sale_id} — Rs.{self.amount}"


class SalesReturn(models.Model):
    STATUS_CHOICES = (
        ('draft', 'Draft'),
        ('completed', 'Completed'),
    )

    org = models.ForeignKey(Organization, related_name='sales_returns', on_delete=models.CASCADE)
    branch = models.ForeignKey(Branch, related_name='sales_returns', on_delete=models.SET_NULL, null=True, blank=True)
    sale = models.ForeignKey(Sale, related_name='returns', on_delete=models.CASCADE)
    client = models.ForeignKey(Client, related_name='sales_returns', on_delete=models.SET_NULL, null=True, blank=True)
    return_date = models.DateField(default=timezone.localdate)
    reason = models.CharField(max_length=255, blank=True)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    journal_entry = models.ForeignKey('JournalEntry', related_name='+', on_delete=models.SET_NULL, null=True, blank=True)
    created_by = models.ForeignKey(CustomUser, related_name='sales_returns_created', on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('-return_date', '-id')

    def __str__(self):
        return f"Return #{self.pk} — Sale #{self.sale_id}"

    def recalc_totals(self):
        self.subtotal = self.items.aggregate(t=models.Sum('line_total'))['t'] or Decimal('0.00')
        self.total_amount = self.subtotal
        self.save(update_fields=['subtotal', 'total_amount', 'updated_at'])


class SalesReturnItem(models.Model):
    return_doc = models.ForeignKey(SalesReturn, related_name='items', on_delete=models.CASCADE)
    sale_item = models.ForeignKey(SaleItem, related_name='return_items', on_delete=models.SET_NULL, null=True, blank=True)
    stock_item = models.ForeignKey(StockItem, related_name='sale_return_items', on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('1.00'))
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    line_total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))

    def __str__(self):
        return f"{self.stock_item.name} x{self.quantity}"

    def save(self, *args, **kwargs):
        self.line_total = Decimal(str(self.quantity)) * Decimal(str(self.unit_price))
        super().save(*args, **kwargs)


class AssetPurchase(models.Model):
    PAYMENT_METHOD_CHOICES = Purchase.PAYMENT_METHOD_CHOICES

    org = models.ForeignKey(Organization, related_name='asset_purchases', on_delete=models.CASCADE)
    branch = models.ForeignKey(Branch, related_name='asset_purchases', on_delete=models.SET_NULL, null=True, blank=True)
    name = models.CharField(max_length=255)
    category = models.CharField(max_length=100, blank=True, help_text="e.g. Furniture, Equipment, Vehicle")
    cost = models.DecimalField(max_digits=12, decimal_places=2)
    purchase_date = models.DateField(default=timezone.localdate)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, default='cash')
    vendor = models.ForeignKey(Supplier, related_name='asset_purchases', on_delete=models.SET_NULL, null=True, blank=True)
    notes = models.TextField(blank=True)
    journal_entry = models.ForeignKey('JournalEntry', related_name='+', on_delete=models.SET_NULL, null=True, blank=True)
    created_by = models.ForeignKey(CustomUser, related_name='asset_purchases_created', on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-purchase_date', '-id')

    def __str__(self):
        return self.name


class CustomerBill(models.Model):
    STATUS_CHOICES = (
        ('draft', 'Draft'),
        ('unpaid', 'Unpaid'),
        ('partial', 'Partially Paid'),
        ('paid', 'Paid'),
        ('overdue', 'Overdue'),
        ('cancelled', 'Cancelled'),
        ('sent', 'Sent (Legacy)'),
    )

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='customer_bills')
    org = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='customer_bills')
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name='customer_bills')
    invoice_number = models.CharField(max_length=50)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.TextField(blank=True)
    issue_date = models.DateField()
    due_date = models.DateField()
    paid_date = models.DateField(null=True, blank=True)
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    bill_image = models.ImageField(upload_to='bill_images/', null=True, blank=True)
    created_by = models.ForeignKey('management.CustomUser', on_delete=models.SET_NULL, null=True, blank=True, related_name='customer_bills_created')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-issue_date', '-id')
        constraints = [
            models.UniqueConstraint(fields=['org', 'invoice_number'], name='unique_customer_invoice_per_org'),
        ]
        indexes = [
            models.Index(fields=['org', 'branch', 'status'], name='custbill_org_branch_status_idx'),
            models.Index(fields=['org', 'client', 'due_date'], name='custbill_client_due_idx'),
        ]

    def __str__(self):
        return f"{self.invoice_number} - {self.client.client_org_name}"

    @property
    def is_overdue(self):
        import datetime
        return self.status not in ('paid', 'cancelled') and self.due_date < datetime.date.today()

    @property
    def remaining_amount(self):
        return max(self.amount - self.paid_amount, Decimal('0.00'))

    def clean(self):
        super().clean()
        if self.client_id and self.org_id and self.client.org_id != self.org_id:
            raise ValidationError({'client': 'The customer must belong to the same organisation.'})
        if self.branch_id and self.branch.org_id != self.org_id:
            raise ValidationError({'branch': 'The branch must belong to the same organisation.'})
        if self.amount is not None and self.amount < 0:
            raise ValidationError({'amount': 'Invoice amount cannot be negative.'})
        if self.paid_amount is not None and self.paid_amount < 0:
            raise ValidationError({'paid_amount': 'Paid amount cannot be negative.'})
        if self.amount is not None and self.paid_amount is not None and self.paid_amount > self.amount:
            raise ValidationError({'paid_amount': 'Paid amount cannot exceed the invoice amount.'})


class CustomerBillPayment(models.Model):
    PAYMENT_METHOD_CHOICES = FinancialTransaction.METHOD_CHOICES

    org = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='customer_bill_payments')
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name='customer_bill_payments')
    bill = models.ForeignKey(CustomerBill, on_delete=models.PROTECT, related_name='payments')
    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name='bill_payments')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_date = models.DateField(default=timezone.localdate)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, default='cash')
    payment_reference = models.CharField(max_length=120, blank=True)
    note = models.TextField(blank=True)
    income_transaction = models.OneToOneField(
        FinancialTransaction, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='customer_bill_payment',
    )
    created_by = models.ForeignKey(
        CustomUser, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='customer_bill_payments_created',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-payment_date', '-id')
        indexes = [
            models.Index(fields=['org', 'branch', 'payment_date'], name='custpay_org_branch_date_idx'),
            models.Index(fields=['org', 'client'], name='custpay_org_client_idx'),
        ]

    def __str__(self):
        return f"Payment #{self.pk} — {self.bill.invoice_number} — {self.amount}"

    def clean(self):
        super().clean()
        if self.amount is None or self.amount <= 0:
            raise ValidationError({'amount': 'Payment amount must be greater than zero.'})
        if self.bill_id:
            if self.bill.org_id != self.org_id or self.bill.client_id != self.client_id:
                raise ValidationError('Payment, bill, customer, and organisation must match.')
            if self.branch_id and self.branch.org_id != self.org_id:
                raise ValidationError({'branch': 'The branch must belong to the same organisation.'})


class CustomerContract(models.Model):
    STATUS_CHOICES = (
        ('active', 'Active'),
        ('expired', 'Expired'),
        ('terminated', 'Terminated'),
        ('draft', 'Draft'),
    )

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='contracts')
    org = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='customer_contracts')
    title = models.CharField(max_length=255)
    contract_value = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    document = models.FileField(upload_to='customer_contracts/', null=True, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey('management.CustomUser', on_delete=models.SET_NULL, null=True, blank=True, related_name='customer_contracts_created')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-start_date', '-id')

    def __str__(self):
        return f"{self.title} - {self.client.client_org_name}"


class CustomerProposal(models.Model):
    STATUS_CHOICES = (
        ('draft', 'Draft'),
        ('sent', 'Sent'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
        ('expired', 'Expired'),
    )

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='proposals')
    org = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='customer_proposals')
    title = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    sent_date = models.DateField(null=True, blank=True)
    valid_until = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    document = models.FileField(upload_to='customer_proposals/', null=True, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey('management.CustomUser', on_delete=models.SET_NULL, null=True, blank=True, related_name='customer_proposals_created')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-created_at',)

    def __str__(self):
        return f"{self.title} - {self.client.client_org_name}"


class CustomerDocument(models.Model):
    DOC_TYPE_CHOICES = (
        ('contract', 'Contract'),
        ('invoice', 'Invoice'),
        ('proposal', 'Proposal'),
        ('agreement', 'Agreement'),
        ('report', 'Report'),
        ('other', 'Other'),
    )

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='documents')
    org = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='customer_documents')
    doc_type = models.CharField(max_length=20, choices=DOC_TYPE_CHOICES, default='other')
    title = models.CharField(max_length=255)
    file = models.FileField(upload_to='customer_documents/')
    notes = models.CharField(max_length=500, blank=True)
    uploaded_by = models.ForeignKey('management.CustomUser', on_delete=models.SET_NULL, null=True, blank=True, related_name='customer_docs_uploaded')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-uploaded_at',)

    def __str__(self):
        return f"{self.title} - {self.client.client_org_name}"


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
    can_view_purchases = models.BooleanField(default=False)
    can_manage_purchases = models.BooleanField(default=False)
    can_view_sales = models.BooleanField(default=False)
    can_manage_sales = models.BooleanField(default=False)
    can_manage_purchase_returns = models.BooleanField(default=False)
    can_manage_sales_returns = models.BooleanField(default=False)

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

    # ── Notices ───────────────────────────────────────────────
    can_view_notices   = models.BooleanField(default=True)
    can_manage_notices = models.BooleanField(default=False)

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

    # ── QR Attendance ─────────────────────────────────────────
    can_scan_qr_attendance = models.BooleanField(default=True)

    # ── Timesheet ─────────────────────────────────────────────
    can_view_timesheets   = models.BooleanField(default=True)
    can_submit_timesheets = models.BooleanField(default=True)

    # ── Field Visits ──────────────────────────────────────────
    can_send_location      = models.BooleanField(default=False)
    can_view_field_visits  = models.BooleanField(default=False)

    # ── Clients ───────────────────────────────────────────────
    can_view_clients   = models.BooleanField(default=False)
    can_manage_clients = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Staff Permission'
        verbose_name_plural = 'Staff Permissions'

    def __str__(self):
        return f"Permissions for {self.member.name}"


class DynamicFeature(models.Model):
    """
    Superadmin-defined feature that needs no migration to add.
    Sits alongside the legacy hardcoded `Organization.feature_x` columns
    (see school/features.py FEATURE_MAP) — has_feature() falls through to
    this table only for keys that aren't in the legacy map.
    """
    key = models.SlugField(unique=True)
    label = models.CharField(max_length=100)
    icon = models.CharField(max_length=50, blank=True, default='fa-puzzle-piece')
    category = models.SlugField(max_length=50, blank=True, help_text="Matches a PERMISSION_REGISTRY category slug, or left blank for 'Custom'.")
    description = models.CharField(max_length=255, blank=True)
    requires = models.JSONField(default=list, blank=True, help_text="Other feature keys (legacy or dynamic) this depends on.")
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True,
                                 help_text="Annual price in Rs. Leave blank to use the standard paid-feature price.")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Dynamic Feature'
        ordering = ['label']

    def __str__(self):
        return self.label


class OrganizationFeatureGrant(models.Model):
    org = models.ForeignKey('management.Organization', on_delete=models.CASCADE, related_name='dynamic_features')
    feature = models.ForeignKey(DynamicFeature, on_delete=models.CASCADE, related_name='org_grants')
    enabled = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('org', 'feature')
        verbose_name = 'Organization Feature Grant'

    def __str__(self):
        return f"{self.org} — {self.feature.key} ({'on' if self.enabled else 'off'})"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        from school.features import invalidate_org_feature_cache
        invalidate_org_feature_cache(self.org_id)

    def delete(self, *args, **kwargs):
        org_id = self.org_id
        result = super().delete(*args, **kwargs)
        from school.features import invalidate_org_feature_cache
        invalidate_org_feature_cache(org_id)
        return result


class DynamicPermission(models.Model):
    """Staff-level permission flag scoped to a DynamicFeature. Companion to StaffPermission's boolean columns."""
    flag = models.SlugField(unique=True)
    label = models.CharField(max_length=100)
    icon = models.CharField(max_length=50, blank=True, default='fa-check-circle')
    feature = models.ForeignKey(DynamicFeature, on_delete=models.CASCADE, related_name='permissions')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Dynamic Permission'
        ordering = ['label']

    def __str__(self):
        return self.label


class StaffPermissionGrant(models.Model):
    member = models.ForeignKey('handle.member', on_delete=models.CASCADE, related_name='dynamic_perm_grants')
    permission = models.ForeignKey(DynamicPermission, on_delete=models.CASCADE, related_name='member_grants')
    granted = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('member', 'permission')
        verbose_name = 'Staff Permission Grant'

    def __str__(self):
        return f"{self.member} — {self.permission.flag} ({'granted' if self.granted else 'revoked'})"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        from school.features import invalidate_member_perm_cache
        invalidate_member_perm_cache(self.member_id)

    def delete(self, *args, **kwargs):
        member_id = self.member_id
        result = super().delete(*args, **kwargs)
        from school.features import invalidate_member_perm_cache
        invalidate_member_perm_cache(member_id)
        return result


class QRAttendanceSession(models.Model):
    SESSION_TYPE_CHOICES = (
        ('dynamic', 'Time-limited Dynamic QR'),
        ('permanent', 'Permanent Geofenced QR'),
    )
    STATUS_CHOICES = (
        ('active', 'Active'),
        ('expired', 'Expired'),
        ('closed', 'Closed'),
    )
    org = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name='qr_attendance_sessions'
    )
    branch = models.ForeignKey(
        Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name='qr_attendance_sessions'
    )
    generated_by = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE, related_name='generated_qr_sessions'
    )
    token = models.CharField(max_length=128, unique=True, db_index=True)
    session_type = models.CharField(
        max_length=12,
        choices=SESSION_TYPE_CHOICES,
        default='dynamic',
        db_index=True,
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='active')
    valid_from = models.DateTimeField()
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    date = models.DateField(null=True, blank=True)
    location_name = models.CharField(max_length=200, blank=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    radius_meters = models.PositiveIntegerField(default=100)
    total_scans = models.PositiveIntegerField(default=0)
    successful_scans = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ('-created_at',)

    def __str__(self):
        return f"QR Session {self.token[:8]}… ({self.org.name})"

    def is_valid(self):
        from django.utils import timezone
        if self.status != 'active':
            return False
        now = timezone.now()
        if now < self.valid_from:
            return False
        if self.session_type == 'permanent':
            return True
        return bool(self.expires_at and now <= self.expires_at)

    def refresh_status(self):
        from django.utils import timezone
        if (
            self.session_type == 'dynamic'
            and self.status == 'active'
            and self.expires_at
            and timezone.now() > self.expires_at
        ):
            self.status = 'expired'
            self.save(update_fields=['status'])
        return self.status


class QRAttendanceScanLog(models.Model):
    SCAN_STATUS_CHOICES = (
        ('success', 'Success'),
        ('expired', 'Expired'),
        ('duplicate', 'Duplicate'),
        ('invalid_org', 'Invalid Org'),
        ('inactive_member', 'Inactive Member'),
        ('session_closed', 'Session Closed'),
        ('outside_geofence', 'Outside Geofence'),
        ('location_required', 'Location Required'),
        ('error', 'Error'),
    )
    session = models.ForeignKey(
        QRAttendanceSession, on_delete=models.CASCADE, related_name='scan_logs'
    )
    member = models.ForeignKey(
        member, on_delete=models.CASCADE, related_name='qr_scan_logs', null=True
    )
    org = models.ForeignKey(Organization, on_delete=models.CASCADE)
    attendance_record = models.ForeignKey(
        AttendanceRecord, on_delete=models.SET_NULL, null=True, blank=True
    )
    scanned_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=SCAN_STATUS_CHOICES, default='success')
    failure_reason = models.CharField(max_length=300, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ('-scanned_at',)

    def __str__(self):
        name = self.member.name if self.member else 'Unknown'
        return f"Scan by {name} — {self.status}"


class SchoolBus(models.Model):
    org = models.ForeignKey(
        Organization,
        related_name='school_buses',
        on_delete=models.CASCADE,
    )
    branch = models.ForeignKey(
        Branch,
        related_name='school_buses',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=120)
    registration_number = models.CharField(max_length=50)
    route_name = models.CharField(max_length=180, blank=True)
    capacity = models.PositiveIntegerField(default=1)
    driver = models.ForeignKey(
        member,
        related_name='assigned_buses',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        limit_choices_to={'member_type': 'driver'},
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('name', 'registration_number')
        constraints = [
            models.UniqueConstraint(
                fields=['org', 'registration_number'],
                name='unique_bus_registration_per_org',
            ),
        ]

    def __str__(self):
        return f'{self.name} — {self.registration_number}'


class StudentBusAssignment(models.Model):
    STATUS_CHOICES = (
        ('active', 'Active'),
        ('inactive', 'Inactive'),
    )
    org = models.ForeignKey(
        Organization,
        related_name='student_bus_assignments',
        on_delete=models.CASCADE,
    )
    student = models.ForeignKey(
        member,
        related_name='bus_assignments',
        on_delete=models.CASCADE,
        limit_choices_to={'member_type__in': ('student', 'trainee')},
    )
    bus = models.ForeignKey(
        SchoolBus,
        related_name='student_assignments',
        on_delete=models.CASCADE,
    )
    stop_name = models.CharField(max_length=180, blank=True)
    stop_latitude = models.FloatField(null=True, blank=True)
    stop_longitude = models.FloatField(null=True, blank=True)
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='active',
    )
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('student__name',)
        constraints = [
            models.UniqueConstraint(
                fields=['student'],
                condition=models.Q(status='active'),
                name='one_active_bus_per_student',
            ),
        ]

    def __str__(self):
        return f'{self.student} → {self.bus}'


class BusTrackingSession(models.Model):
    STATUS_CHOICES = (
        ('active', 'Active'),
        ('stopped', 'Stopped'),
    )
    org = models.ForeignKey(
        Organization,
        related_name='bus_tracking_sessions',
        on_delete=models.CASCADE,
    )
    bus = models.ForeignKey(
        SchoolBus,
        related_name='tracking_sessions',
        on_delete=models.CASCADE,
    )
    driver = models.ForeignKey(
        member,
        related_name='bus_tracking_sessions',
        on_delete=models.CASCADE,
        limit_choices_to={'member_type': 'driver'},
    )
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='active',
    )
    started_at = models.DateTimeField(auto_now_add=True)
    stopped_at = models.DateTimeField(null=True, blank=True)
    last_ping_at = models.DateTimeField(null=True, blank=True)
    last_latitude = models.FloatField(null=True, blank=True)
    last_longitude = models.FloatField(null=True, blank=True)
    last_accuracy_meters = models.FloatField(null=True, blank=True)

    class Meta:
        ordering = ('-started_at',)
        constraints = [
            models.UniqueConstraint(
                fields=['bus'],
                condition=models.Q(status='active'),
                name='one_active_tracking_session_per_bus',
            ),
        ]


class BusLocationPing(models.Model):
    session = models.ForeignKey(
        BusTrackingSession,
        related_name='pings',
        on_delete=models.CASCADE,
    )
    org = models.ForeignKey(
        Organization,
        related_name='bus_location_pings',
        on_delete=models.CASCADE,
    )
    bus = models.ForeignKey(
        SchoolBus,
        related_name='location_pings',
        on_delete=models.CASCADE,
    )
    driver = models.ForeignKey(
        member,
        related_name='bus_location_pings',
        on_delete=models.CASCADE,
    )
    latitude = models.FloatField()
    longitude = models.FloatField()
    accuracy_meters = models.FloatField(null=True, blank=True)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-recorded_at',)
        indexes = [
            models.Index(fields=['bus', 'recorded_at']),
            models.Index(fields=['driver', 'recorded_at']),
        ]


class BusStudentTripStatus(models.Model):
    """One student's pickup lifecycle within one live bus trip.

    The assignment remains the source of route/stop ownership while this row
    preserves what the driver did during a particular trip.  Keeping this
    separate from ``StudentBusAssignment`` prevents today's pickup state from
    leaking into tomorrow's trip.
    """

    STATUS_CHOICES = (
        ('waiting', 'Waiting'),
        ('picked_up', 'Picked Up'),
        ('dropped_off', 'Dropped Off'),
        ('skipped', 'Skipped'),
    )
    session = models.ForeignKey(
        BusTrackingSession,
        related_name='student_statuses',
        on_delete=models.CASCADE,
    )
    assignment = models.ForeignKey(
        StudentBusAssignment,
        related_name='trip_statuses',
        on_delete=models.CASCADE,
    )
    org = models.ForeignKey(
        Organization,
        related_name='bus_student_trip_statuses',
        on_delete=models.CASCADE,
    )
    bus = models.ForeignKey(
        SchoolBus,
        related_name='student_trip_statuses',
        on_delete=models.CASCADE,
    )
    student = models.ForeignKey(
        member,
        related_name='bus_trip_statuses',
        on_delete=models.CASCADE,
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='waiting',
    )
    note = models.CharField(max_length=250, blank=True)
    marked_by = models.ForeignKey(
        member,
        related_name='marked_bus_student_statuses',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    picked_up_at = models.DateTimeField(null=True, blank=True)
    dropped_off_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('assignment__student__name',)
        constraints = [
            models.UniqueConstraint(
                fields=['session', 'assignment'],
                name='unique_student_state_per_bus_trip',
            ),
        ]
        indexes = [
            models.Index(fields=['org', 'session', 'status']),
            models.Index(fields=['student', 'updated_at']),
        ]


# ── Timesheet ─────────────────────────────────────────────────────────────────

class Timesheet(models.Model):
    STATUS_CHOICES = (
        ('draft',     'Draft'),
        ('submitted', 'Submitted'),
        ('approved',  'Approved'),
        ('rejected',  'Rejected'),
    )
    member      = models.ForeignKey('handle.member',            on_delete=models.CASCADE,  related_name='timesheets')
    org         = models.ForeignKey('management.Organization',  on_delete=models.CASCADE,  related_name='timesheets')
    date         = models.DateField()
    title        = models.CharField(max_length=200, blank=True)
    status       = models.CharField(max_length=15, choices=STATUS_CHOICES, default='draft')
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_by  = models.ForeignKey('management.CustomUser', null=True, blank=True,
                                     on_delete=models.SET_NULL, related_name='approved_timesheets')
    approved_at  = models.DateTimeField(null=True, blank=True)
    admin_comment = models.TextField(blank=True)
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('-date', '-id')
        constraints = [
            models.UniqueConstraint(fields=['member', 'org', 'date'], name='uniq_timesheet_member_org_date'),
        ]

    def __str__(self):
        return f"{self.member.name} — {self.date}"

    def total_hours(self):
        from django.db.models import Sum
        return self.entries.aggregate(t=Sum('hours'))['t'] or 0

    def can_edit(self):
        return self.status in ('draft', 'rejected')


class TimesheetEntry(models.Model):
    timesheet = models.ForeignKey(Timesheet, on_delete=models.CASCADE, related_name='entries')
    task      = models.CharField(max_length=300)
    hours     = models.DecimalField(max_digits=5, decimal_places=2)
    notes     = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('task',)

    def __str__(self):
        return f"{self.timesheet.member.name} — {self.timesheet.date} — {self.task} ({self.hours}h)"


class IDCardTemplate(models.Model):
    """
    Per-organization ID card design config. An org can save multiple named
    designs (one row per `name`) — get_or_create'd on (org, name), same
    pattern PayrollPolicy uses for the single-row case.
    """

    CARD_SIZE_CHOICES = (
        ('cr80', 'Standard CR80 (85.6mm x 54mm / 3.375in x 2.125in)'),
        ('custom', 'Custom size'),
    )
    PHOTO_SIZE_CHOICES = (
        ('small', 'Small (20mm x 20mm)'),
        ('medium', 'Medium (25mm x 25mm)'),
        ('large', 'Large (30mm x 30mm)'),
        ('custom', 'Custom size'),
    )
    DESIGN_CHOICES = (
        ('modern_corporate_vertical', 'Modern Corporate (Vertical)'),
        ('minimal_clean_vertical', 'Minimal Clean (Vertical)'),
        ('school_style_vertical', 'School Style (Vertical)'),
        ('corporate_landscape', 'Corporate Landscape (Horizontal)'),
        ('employee_professional_landscape', 'Employee Professional (Horizontal)'),
        ('student_landscape', 'Student Landscape (Horizontal)'),
    )
    ORIENTATION_BY_DESIGN = {
        'modern_corporate_vertical': 'vertical',
        'minimal_clean_vertical': 'vertical',
        'school_style_vertical': 'vertical',
        'corporate_landscape': 'horizontal',
        'employee_professional_landscape': 'horizontal',
        'student_landscape': 'horizontal',
    }
    ORIENTATION_CHOICES = (
        ('vertical', 'Vertical'),
        ('horizontal', 'Horizontal'),
    )
    FONT_CHOICES = (
        ('inter', 'Inter / Arial'),
        ('poppins', 'Poppins / Arial'),
        ('roboto', 'Roboto / Arial'),
        ('montserrat', 'Montserrat / Arial'),
        ('georgia', 'Georgia / Serif'),
        ('times', 'Times New Roman / Serif'),
    )
    FONT_STACKS = {
        'inter': "Inter, Arial, sans-serif",
        'poppins': "Poppins, Arial, sans-serif",
        'roboto': "Roboto, Arial, sans-serif",
        'montserrat': "Montserrat, Arial, sans-serif",
        'georgia': "Georgia, 'Times New Roman', serif",
        'times': "'Times New Roman', Times, serif",
    }

    org = models.ForeignKey(Organization, related_name='id_card_templates', on_delete=models.CASCADE)
    name = models.CharField(max_length=40, choices=DESIGN_CHOICES, default='modern_corporate_vertical')
    orientation = models.CharField(max_length=10, choices=ORIENTATION_CHOICES, default='vertical')
    primary_color = models.CharField(max_length=7, default='#1e293b', help_text="Hex color, e.g. #1e293b")
    secondary_color = models.CharField(max_length=7, default='#6366f1', help_text="Hex color, e.g. #6366f1")
    text_color = models.CharField(max_length=7, default='#111827', help_text="Main card text color.")
    font_family = models.CharField(max_length=20, choices=FONT_CHOICES, default='inter')
    base_font_size = models.PositiveSmallIntegerField(default=10, help_text="Detail text size in pixels.")
    name_font_size = models.PositiveSmallIntegerField(default=14, help_text="Member name size in pixels.")
    org_font_size = models.PositiveSmallIntegerField(default=13, help_text="Organization name size in pixels.")
    line_height = models.DecimalField(max_digits=3, decimal_places=2, default=1.35)
    card_title = models.CharField(max_length=80, blank=True, default='', help_text="Optional heading such as STUDENT ID CARD.")
    footer_text = models.CharField(max_length=180, blank=True, default='', help_text="Optional text printed on the back of the card.")
    is_default = models.BooleanField(default=False, help_text="Pre-selected design on the Generate ID Cards page.")

    card_size = models.CharField(max_length=10, choices=CARD_SIZE_CHOICES, default='cr80')
    custom_width_mm = models.PositiveIntegerField(default=86, help_text="Only used when card size is Custom.")
    custom_height_mm = models.PositiveIntegerField(default=54, help_text="Only used when card size is Custom.")

    photo_size = models.CharField(max_length=10, choices=PHOTO_SIZE_CHOICES, default='medium')
    custom_photo_size_mm = models.PositiveIntegerField(default=25, help_text="Only used when photo size is Custom.")

    front_background = models.ImageField(upload_to='id_card_backgrounds', null=True, blank=True)
    back_background = models.ImageField(upload_to='id_card_backgrounds', null=True, blank=True)

    # Which fields to print on the card — all default on so a freshly
    # generated card is useful without any configuration.
    show_logo = models.BooleanField(default=True)
    show_org_name = models.BooleanField(default=True)
    show_photo = models.BooleanField(default=True)
    show_member_id = models.BooleanField(default=True)
    show_roll_number = models.BooleanField(default=True)
    show_address = models.BooleanField(default=True)
    show_phone = models.BooleanField(default=True)
    show_email = models.BooleanField(default=True)
    show_classification = models.BooleanField(default=True, verbose_name="Show classification / department")
    show_qr_code = models.BooleanField(default=True)
    show_barcode = models.BooleanField(default=True)
    show_designation = models.BooleanField(default=True)
    # Retained for database compatibility with old saved designs. These
    # medical/signature/expiry fields are no longer exposed by the active
    # designer or renderer because they are not part of the core member data
    # required for an identity card.
    show_blood_group = models.BooleanField(default=False)
    show_signature = models.BooleanField(default=False)
    show_valid_until = models.BooleanField(default=False)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('org', 'name')
        verbose_name = 'ID Card Template'

    def __str__(self):
        return f"{self.get_name_display()} - {self.org.name}"

    def save(self, *args, **kwargs):
        # orientation always tracks the chosen design — never independently editable.
        self.orientation = self.ORIENTATION_BY_DESIGN.get(self.name, 'vertical')
        super().save(*args, **kwargs)

    def card_dimensions_mm(self):
        if self.card_size == 'custom':
            return self.custom_width_mm, self.custom_height_mm
        if self.orientation == 'vertical':
            return 54, 86
        return 86, 54

    def photo_dimensions_mm(self):
        if self.photo_size == 'custom':
            return self.custom_photo_size_mm, self.custom_photo_size_mm
        return {'small': (20, 20), 'medium': (25, 25), 'large': (30, 30)}.get(self.photo_size, (25, 25))

    @property
    def font_css_stack(self):
        return self.FONT_STACKS.get(self.font_family, self.FONT_STACKS['inter'])


class CertificateTemplate(models.Model):
    """Organization-owned, reusable certificate layout and rich-text content."""

    TYPE_CHOICES = (
        ('completion', 'Course Completion'),
        ('achievement', 'Achievement'),
        ('participation', 'Participation'),
        ('training', 'Training'),
        ('experience', 'Experience'),
        ('appreciation', 'Appreciation'),
        ('character', 'Character / Conduct'),
        ('membership', 'Membership'),
        ('custom', 'Custom Certificate'),
    )
    ORIENTATION_CHOICES = (
        ('landscape', 'A4 Landscape'),
        ('portrait', 'A4 Portrait'),
    )
    BORDER_CHOICES = (
        ('classic', 'Classic Double Border'),
        ('modern', 'Modern Corner Border'),
        ('minimal', 'Minimal Single Border'),
        ('none', 'No Border'),
    )
    FONT_CHOICES = IDCardTemplate.FONT_CHOICES

    org = models.ForeignKey(Organization, related_name='certificate_templates', on_delete=models.CASCADE)
    name = models.CharField(max_length=120)
    certificate_type = models.CharField(max_length=30, choices=TYPE_CHOICES, default='completion')
    orientation = models.CharField(max_length=12, choices=ORIENTATION_CHOICES, default='landscape')
    title = models.CharField(max_length=160, default='Certificate of Completion')
    subtitle = models.CharField(max_length=200, blank=True, default='This certificate is proudly presented to')
    body_html = models.TextField(
        default='<p>For successfully completing the prescribed programme at <strong>[[organization]]</strong>.</p>',
        help_text='Rich text. Use the supported [[tokens]] for member data.',
    )
    footer_text = models.CharField(max_length=240, blank=True, default='')
    serial_prefix = models.CharField(max_length=20, blank=True, default='CERT')

    primary_color = models.CharField(max_length=7, default='#172554')
    secondary_color = models.CharField(max_length=7, default='#c59d3f')
    text_color = models.CharField(max_length=7, default='#1f2937')
    border_style = models.CharField(max_length=20, choices=BORDER_CHOICES, default='classic')
    font_family = models.CharField(max_length=20, choices=FONT_CHOICES, default='georgia')
    title_font_size = models.PositiveSmallIntegerField(default=38)
    recipient_font_size = models.PositiveSmallIntegerField(default=34)
    body_font_size = models.PositiveSmallIntegerField(default=17)
    line_height = models.DecimalField(max_digits=3, decimal_places=2, default=1.60)

    background_image = models.ImageField(upload_to='certificate_backgrounds', null=True, blank=True)
    letterhead_image = models.ImageField(upload_to='certificate_letterheads', null=True, blank=True)
    show_logo = models.BooleanField(default=True)
    show_issue_date = models.BooleanField(default=True)
    show_certificate_number = models.BooleanField(default=True)
    signature_one_name = models.CharField(max_length=100, blank=True, default='')
    signature_one_title = models.CharField(max_length=100, blank=True, default='Authorized Signature')
    signature_one_image = models.ImageField(upload_to='certificate_signatures', null=True, blank=True)
    signature_two_name = models.CharField(max_length=100, blank=True, default='')
    signature_two_title = models.CharField(max_length=100, blank=True, default='')
    signature_two_image = models.ImageField(upload_to='certificate_signatures', null=True, blank=True)
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        CustomUser, related_name='created_certificate_templates', on_delete=models.SET_NULL,
        null=True, blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('-is_default', 'name')
        constraints = [
            models.UniqueConstraint(fields=('org', 'name'), name='unique_certificate_template_name_per_org'),
        ]
        indexes = [models.Index(fields=('org', 'is_active'))]

    def __str__(self):
        return f"{self.name} - {self.org.name}"

    @property
    def font_css_stack(self):
        return IDCardTemplate.FONT_STACKS.get(self.font_family, IDCardTemplate.FONT_STACKS['georgia'])


class EmailLog(models.Model):
    """
    A record of every outgoing notification email — delivery status, so a
    failed send is never silent, and a dedup check against
    (recipient_email, email_type, related_object_id) so the same event can't
    double-send.
    """
    EMAIL_TYPE_CHOICES = (
        ('welcome', 'Welcome / Login Credentials'),
        ('leave_submitted', 'Leave Submitted'),
        ('leave_approved', 'Leave Approved'),
        ('leave_rejected', 'Leave Rejected'),
        ('leave_cancelled', 'Leave Cancelled'),
        ('payslip', 'Payslip Generated'),
        ('bill', 'Student Fee Bill'),
        ('payment_receipt', 'Payment Receipt'),
        ('result', 'Exam Result Published'),
        ('resignation', 'Resignation Status'),
        ('complaint', 'Complaint Update'),
        ('task_assigned', 'Task Assigned'),
        ('task_completed', 'Task Completed'),
        ('task_overdue', 'Task Overdue'),
        ('task_approval', 'Task Approval'),
        ('password_reset', 'Password Reset'),
        ('attendance_summary', 'Attendance Summary'),
        ('notice', 'Notice / Announcement'),
        ('broadcast_message', 'Operations Broadcast Message'),
        ('homework_assigned', 'Homework Assigned'),
        ('assignment_assigned', 'Assignment Assigned'),
        ('assignment_due', 'Assignment Due Reminder'),
        ('submission_received', 'Assignment Submission Received'),
        ('marks_published', 'Assignment Marks Published'),
        ('course_material_added', 'New Course Material'),
        ('teaching_log_reviewed', 'Teaching Log Reviewed'),
        ('other', 'Other'),
    )
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('sent', 'Sent'),
        ('failed', 'Failed'),
    )

    org = models.ForeignKey('management.Organization', on_delete=models.CASCADE, null=True, blank=True, related_name='email_logs')
    recipient_email = models.EmailField()
    recipient_name = models.CharField(max_length=200, blank=True)
    email_type = models.CharField(max_length=30, choices=EMAIL_TYPE_CHOICES, default='other')
    subject = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    error_message = models.TextField(blank=True)
    related_object_type = models.CharField(max_length=50, blank=True, help_text="e.g. 'PaySlip', 'Bill', 'LeaveReport'")
    related_object_id = models.PositiveIntegerField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-created_at',)
        indexes = [
            models.Index(fields=['recipient_email', 'email_type', 'related_object_id']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"{self.get_email_type_display()} -> {self.recipient_email} ({self.status})"


# ---------------------------------------------------------
# PRINT SETTINGS (persisted per user, per report type)
# ---------------------------------------------------------

class PrintPreference(models.Model):
    """
    Remembers one user's print configuration (paper size, orientation,
    margin, fit-to-width, hidden columns...) for a given printable report,
    so it doesn't reset on every visit. `report_key` is a short slug such as
    'daily_report', 'monthly_report', 'payslip', 'id_card' — any print-enabled
    page can adopt this by picking its own key.
    """
    user = models.ForeignKey(CustomUser, related_name='print_preferences', on_delete=models.CASCADE)
    report_key = models.CharField(max_length=50)
    settings = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'report_key')

    def __str__(self):
        return f"{self.user} · {self.report_key}"


class OrgPrintDefault(models.Model):
    """
    Org-wide default print configuration for a report (paper size,
    orientation, margin, fit-to-width) — set once by an admin from the
    Organization Profile page. `school.print_settings.get_print_preference`
    layers these under any per-user `PrintPreference`: hardcoded fallback ->
    this org default -> the viewing user's own saved override, so a fresh
    user who has never touched the print panel still gets the org's chosen
    layout instead of the generic app default.
    """
    org = models.ForeignKey(Organization, related_name='print_defaults', on_delete=models.CASCADE)
    report_key = models.CharField(max_length=50)
    settings = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('org', 'report_key')

    def __str__(self):
        return f"{self.org} · {self.report_key} (org default)"


# ---------------------------------------------------------
# NOTICE BOARD / ANNOUNCEMENTS
# ---------------------------------------------------------

class Notice(models.Model):
    """An announcement published by an org admin to a chosen audience.

    Targeting is a single `audience` choice plus (for the scoped choices) one
    matching FK. Keeping one audience field instead of a pile of independent
    filters means "who receives this" is always unambiguous, and
    `recipient_members()` is the single place that resolves it.
    """

    PRIORITY_CHOICES = (
        ('low', 'Low'),
        ('normal', 'Normal'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    )

    AUDIENCE_CHOICES = (
        ('org', 'Entire Organization'),
        ('branch', 'Specific Branch'),
        ('department', 'Specific Department / Class'),
        ('section', 'Specific Section'),
        ('course', 'Specific Course'),
        ('shift', 'Specific Shift'),
        ('member', 'Individual Employee / Student'),
        ('staff_only', 'All Staff / Employees'),
        ('students_only', 'All Students'),
    )

    org = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='notices')
    title = models.CharField(max_length=255)
    body = models.TextField()
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='normal')
    attachment = models.FileField(upload_to='notice_attachments/', null=True, blank=True)

    audience = models.CharField(max_length=20, choices=AUDIENCE_CHOICES, default='org')
    # Only the FK matching `audience` is used; the rest stay null.
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, null=True, blank=True, related_name='notices')
    classification = models.ForeignKey(Classification, on_delete=models.CASCADE, null=True, blank=True, related_name='notices')
    section = models.ForeignKey(Section, on_delete=models.CASCADE, null=True, blank=True, related_name='notices')
    course = models.ForeignKey('Course', on_delete=models.CASCADE, null=True, blank=True, related_name='notices')
    shift = models.ForeignKey('Shift', on_delete=models.CASCADE, null=True, blank=True, related_name='notices')
    target_member = models.ForeignKey('member', on_delete=models.CASCADE, null=True, blank=True, related_name='targeted_notices')

    # Scheduling: publish_at in the future keeps it hidden until then; a past
    # expires_at hides it again. Both null => visible immediately, forever.
    publish_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField(null=True, blank=True)

    send_email = models.BooleanField(default=False, help_text="Email this notice to its recipients when published.")
    email_sent_at = models.DateTimeField(null=True, blank=True)

    created_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_notices')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('-publish_at', '-id')
        indexes = [
            models.Index(fields=['org', 'publish_at']),
            models.Index(fields=['org', 'audience']),
        ]

    def __str__(self):
        return f"{self.title} ({self.org.name})"

    # ── State helpers ────────────────────────────────────────────────────────
    def is_scheduled(self):
        """Still waiting for its publish time."""
        return self.publish_at is not None and self.publish_at > timezone.now()

    def is_expired(self):
        return self.expires_at is not None and self.expires_at <= timezone.now()

    def is_live(self):
        return not self.is_scheduled() and not self.is_expired()

    def state(self):
        if self.is_scheduled():
            return 'scheduled'
        if self.is_expired():
            return 'expired'
        return 'live'

    def audience_label(self):
        """Human-readable description of who this notice reaches."""
        target = {
            'branch': self.branch, 'department': self.classification,
            'section': self.section, 'course': self.course,
            'shift': self.shift, 'member': self.target_member,
        }.get(self.audience)
        if target is not None:
            return f"{self.get_audience_display()}: {target}"
        return self.get_audience_display()

    def recipient_members(self):
        """Members this notice is addressed to, scoped to its own org."""
        qs = member.objects.filter(org=self.org, status='active')
        a = self.audience
        if a == 'branch' and self.branch_id:
            return qs.filter(branch_id=self.branch_id)
        if a == 'department' and self.classification_id:
            return qs.filter(classification_id=self.classification_id)
        if a == 'section' and self.section_id:
            return qs.filter(section_id=self.section_id)
        if a == 'course' and self.course_id:
            return qs.filter(courses__id=self.course_id).distinct()
        if a == 'shift' and self.shift_id:
            return qs.filter(shifts__id=self.shift_id).distinct()
        if a == 'member' and self.target_member_id:
            return qs.filter(id=self.target_member_id)
        if a == 'staff_only':
            return qs.exclude(member_type__in=('student', 'trainee'))
        if a == 'students_only':
            return qs.filter(member_type__in=('student', 'trainee'))
        return qs  # 'org' — everyone

    def is_for_member(self, memb):
        """Whether `memb` should see this notice (audience + live window)."""
        if memb is None or memb.org_id != self.org_id or not self.is_live():
            return False
        return self.recipient_members().filter(id=memb.id).exists()

    def read_count(self):
        return self.reads.count()


class NoticeRead(models.Model):
    """One row per (notice, member) that has been marked read. Absence of a
    row means unread, so nothing needs backfilling when a notice is created."""

    notice = models.ForeignKey(Notice, on_delete=models.CASCADE, related_name='reads')
    member = models.ForeignKey('member', on_delete=models.CASCADE, related_name='notice_reads')
    read_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('notice', 'member')
        ordering = ('-read_at',)

    def __str__(self):
        return f"{self.member.name} read {self.notice.title}"


# =============================================================
# LIBRARY MANAGEMENT (premium — gated by the 'library' DynamicFeature)
# =============================================================

class LibraryCategory(models.Model):
    org = models.ForeignKey(Organization, related_name='library_categories', on_delete=models.CASCADE)
    name = models.CharField(max_length=150)
    description = models.TextField(null=True, blank=True)

    class Meta:
        unique_together = ('org', 'name')
        ordering = ('name',)
        verbose_name_plural = 'Library Categories'

    def __str__(self):
        return self.name


class LibraryAuthor(models.Model):
    org = models.ForeignKey(Organization, related_name='library_authors', on_delete=models.CASCADE)
    name = models.CharField(max_length=200)
    bio = models.TextField(null=True, blank=True)

    class Meta:
        unique_together = ('org', 'name')
        ordering = ('name',)

    def __str__(self):
        return self.name


class LibraryPublisher(models.Model):
    org = models.ForeignKey(Organization, related_name='library_publishers', on_delete=models.CASCADE)
    name = models.CharField(max_length=200)
    address = models.CharField(max_length=255, null=True, blank=True)
    contact = models.CharField(max_length=50, null=True, blank=True)

    class Meta:
        unique_together = ('org', 'name')
        ordering = ('name',)

    def __str__(self):
        return self.name


class LibraryRack(models.Model):
    org = models.ForeignKey(Organization, related_name='library_racks', on_delete=models.CASCADE)
    branch = models.ForeignKey(Branch, related_name='library_racks', on_delete=models.SET_NULL, null=True, blank=True)
    code = models.CharField(max_length=50)
    name = models.CharField(max_length=150, null=True, blank=True)

    class Meta:
        unique_together = ('org', 'code')
        ordering = ('code',)

    def __str__(self):
        return self.name or self.code


class LibraryShelf(models.Model):
    org = models.ForeignKey(Organization, related_name='library_shelves', on_delete=models.CASCADE)
    rack = models.ForeignKey(LibraryRack, related_name='shelves', on_delete=models.CASCADE)
    code = models.CharField(max_length=50)
    name = models.CharField(max_length=150, null=True, blank=True)

    class Meta:
        unique_together = ('rack', 'code')
        ordering = ('code',)

    def __str__(self):
        return f"{self.rack.code}/{self.code}"


class LibrarySettings(models.Model):
    """Per-org configuration for loan period, fines and borrowing limits."""
    org = models.OneToOneField(Organization, related_name='library_settings', on_delete=models.CASCADE)
    loan_period_days = models.PositiveIntegerField(default=14, help_text="Default days a book may be held before it is due.")
    fine_per_day = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('5.00'), help_text="Fine charged per day overdue.")
    max_books_per_member = models.PositiveIntegerField(default=3, help_text="Maximum books a member may hold at once.")

    def __str__(self):
        return f"Library settings — {self.org}"

    @classmethod
    def for_org(cls, org):
        settings_obj, _ = cls.objects.get_or_create(org=org)
        return settings_obj


class Book(models.Model):
    STATUS_CHOICES = (
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('archived', 'Archived'),
    )

    org = models.ForeignKey(Organization, related_name='library_books', on_delete=models.CASCADE)
    branch = models.ForeignKey(Branch, related_name='library_books', on_delete=models.SET_NULL, null=True, blank=True)

    book_code = models.CharField(max_length=50, help_text="Internal accession number / book code.")
    isbn = models.CharField(max_length=20, null=True, blank=True, verbose_name="ISBN")

    title = models.CharField(max_length=300)
    subtitle = models.CharField(max_length=300, null=True, blank=True)
    category = models.ForeignKey(LibraryCategory, related_name='books', on_delete=models.SET_NULL, null=True, blank=True)
    subject = models.CharField(max_length=150, null=True, blank=True)
    author = models.ForeignKey(LibraryAuthor, related_name='books', on_delete=models.SET_NULL, null=True, blank=True)
    publisher = models.ForeignKey(LibraryPublisher, related_name='books', on_delete=models.SET_NULL, null=True, blank=True)
    edition = models.CharField(max_length=50, null=True, blank=True)
    language = models.CharField(max_length=50, null=True, blank=True)

    rack = models.ForeignKey(LibraryRack, related_name='books', on_delete=models.SET_NULL, null=True, blank=True)
    shelf = models.ForeignKey(LibraryShelf, related_name='books', on_delete=models.SET_NULL, null=True, blank=True)

    purchase_date = models.DateField(null=True, blank=True)
    purchase_price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))

    quantity = models.PositiveIntegerField(default=1, help_text="Total copies owned.")
    available_quantity = models.PositiveIntegerField(default=1, help_text="Copies currently on the shelf (not issued).")
    lost_quantity = models.PositiveIntegerField(default=0)
    damaged_quantity = models.PositiveIntegerField(default=0)

    cover_image = models.ImageField(upload_to='library_covers/', null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('org', 'book_code')
        ordering = ('title',)

    def __str__(self):
        return f"{self.title} ({self.book_code})"

    @property
    def issued_quantity(self):
        return max(self.quantity - self.available_quantity - self.lost_quantity - self.damaged_quantity, 0)

    @property
    def is_available(self):
        return self.status == 'active' and self.available_quantity > 0

    def qr_payload(self):
        """String encoded into the book's QR — resolved back to this book by book_code."""
        return f"BOOK-{self.org_id}-{self.book_code}"


class BookIssue(models.Model):
    STATUS_CHOICES = (
        ('issued', 'Issued'),
        ('returned', 'Returned'),
        ('overdue', 'Overdue'),
        ('lost', 'Lost'),
    )

    org = models.ForeignKey(Organization, related_name='book_issues', on_delete=models.CASCADE)
    branch = models.ForeignKey(Branch, related_name='book_issues', on_delete=models.SET_NULL, null=True, blank=True)
    book = models.ForeignKey(Book, related_name='issues', on_delete=models.CASCADE)
    member = models.ForeignKey('member', related_name='book_issues', on_delete=models.CASCADE)

    issue_date = models.DateField()
    due_date = models.DateField()
    return_date = models.DateField(null=True, blank=True)

    fine = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('0.00'))
    fine_paid = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('0.00'))
    late_days = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='issued')

    issued_by = models.ForeignKey(CustomUser, related_name='books_issued', on_delete=models.SET_NULL, null=True, blank=True)
    returned_by = models.ForeignKey(CustomUser, related_name='books_returned', on_delete=models.SET_NULL, null=True, blank=True)
    remarks = models.CharField(max_length=255, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-issue_date', '-id')

    def __str__(self):
        return f"{self.book.title} → {self.member.name} ({self.get_status_display()})"

    @property
    def is_overdue(self):
        if self.status not in ('issued', 'overdue'):
            return False
        return datetime.date.today() > self.due_date

    def compute_fine(self, as_of=None, fine_per_day=None):
        """Fine accrued so far (or as of the given date), without saving."""
        as_of = as_of or datetime.date.today()
        if self.return_date:
            as_of = min(as_of, self.return_date) if as_of > self.return_date else self.return_date
        late_days = max((as_of - self.due_date).days, 0)
        rate = fine_per_day if fine_per_day is not None else LibrarySettings.for_org(self.org).fine_per_day
        return late_days, (Decimal(late_days) * rate)

    def mark_returned(self, returned_by=None, return_date=None, condition='good'):
        """Return a copy: updates issue row + Book counters. `condition` is 'good'/'damaged'/'lost'."""
        return_date = return_date or datetime.date.today()
        late_days, fine_amount = self.compute_fine(as_of=return_date)
        self.return_date = return_date
        self.late_days = late_days
        self.fine = fine_amount
        self.returned_by = returned_by
        book = self.book
        if condition == 'lost':
            self.status = 'lost'
            book.lost_quantity += 1
        elif condition == 'damaged':
            self.status = 'returned'
            book.damaged_quantity += 1
            book.available_quantity += 1
        else:
            self.status = 'returned'
            book.available_quantity += 1
        book.save(update_fields=['available_quantity', 'lost_quantity', 'damaged_quantity'])
        self.save()


# =============================================================
# ACCOUNTING CORE (premium — gated by the 'accounting' DynamicFeature)
# Double-entry ledger: Chart of Accounts, Journal Entries, Journal Lines.
# Deliberately independent of FinancialTransaction/TransactionCategory —
# those keep working exactly as today; this is a parallel system.
# =============================================================

class Account(models.Model):
    """Chart-of-Accounts node. Hierarchical (self-FK parent); every node
    carries an explicit account_type so reports never need a recursive
    parent walk. is_group nodes are headers only (e.g. 'Current Assets')
    and cannot be posted to; leaf nodes are postable."""
    TYPE_CHOICES = (
        ('asset', 'Asset'),
        ('liability', 'Liability'),
        ('equity', 'Equity'),
        ('income', 'Income'),
        ('expense', 'Expense'),
        ('cogs', 'Cost of Goods Sold'),
    )
    DEBIT_NORMAL_TYPES = ('asset', 'expense', 'cogs')

    org = models.ForeignKey(Organization, related_name='accounts', on_delete=models.CASCADE)
    parent = models.ForeignKey('self', related_name='children', on_delete=models.PROTECT, null=True, blank=True)
    code = models.CharField(max_length=20, blank=True, help_text="Optional account code (e.g. 1000).")
    name = models.CharField(max_length=150)
    account_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    is_group = models.BooleanField(default=False, help_text="Header/control account — cannot be posted to directly.")
    is_system = models.BooleanField(default=False, help_text="Seeded default account; cannot be deleted, only deactivated.")
    opening_balance = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'),
                                           help_text="On the account's normal-balance side.")
    description = models.CharField(max_length=255, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('org', 'name', 'parent')
        ordering = ('code', 'name')

    def __str__(self):
        return f"{self.code} — {self.name}" if self.code else self.name

    def is_debit_normal(self):
        return self.account_type in self.DEBIT_NORMAL_TYPES

    def full_path(self):
        parts, node = [self.name], self.parent
        while node:
            parts.append(node.name)
            node = node.parent
        return ' / '.join(reversed(parts))


class AccountingVoucherSequence(models.Model):
    """Per-org atomic counter for voucher numbers. Kept as its own row (not
    a field on Organization) so select_for_update() locks only this row."""
    org = models.OneToOneField(Organization, related_name='accounting_voucher_sequence', on_delete=models.CASCADE)
    last_number = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.org} — next #{self.last_number + 1}"


class JournalEntry(models.Model):
    STATUS_CHOICES = (
        ('draft', 'Draft'),
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    )
    org = models.ForeignKey(Organization, related_name='journal_entries', on_delete=models.CASCADE)
    branch = models.ForeignKey(Branch, related_name='journal_entries', on_delete=models.SET_NULL, null=True, blank=True)
    voucher_number = models.CharField(max_length=30)
    entry_date = models.DateField(default=timezone.localdate)
    reference = models.CharField(max_length=120, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    source = models.CharField(max_length=30, default='manual',
                              help_text="'manual' or a future auto-poster key ('sales','purchase','payroll',...).")
    purchase = models.ForeignKey('Purchase', related_name='+', on_delete=models.SET_NULL, null=True, blank=True)
    sale = models.ForeignKey('Sale', related_name='+', on_delete=models.SET_NULL, null=True, blank=True)
    attachment = models.FileField(upload_to='journal_entries/', null=True, blank=True)
    created_by = models.ForeignKey(CustomUser, related_name='journal_entries_created', on_delete=models.SET_NULL, null=True, blank=True)
    approved_by = models.ForeignKey(CustomUser, related_name='journal_entries_approved', on_delete=models.SET_NULL, null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('org', 'voucher_number')
        ordering = ('-entry_date', '-id')

    def __str__(self):
        return f"{self.voucher_number} ({self.get_status_display()})"

    def total_debit(self):
        return self.lines.aggregate(t=models.Sum('debit'))['t'] or Decimal('0.00')

    def total_credit(self):
        return self.lines.aggregate(t=models.Sum('credit'))['t'] or Decimal('0.00')

    def is_balanced(self):
        return self.lines.count() >= 2 and self.total_debit() == self.total_credit() and self.total_debit() > 0


class JournalEntryLine(models.Model):
    entry = models.ForeignKey(JournalEntry, related_name='lines', on_delete=models.CASCADE)
    account = models.ForeignKey(Account, related_name='journal_lines', on_delete=models.PROTECT)
    debit = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    credit = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    remarks = models.CharField(max_length=255, null=True, blank=True)
    line_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ('line_order', 'id')

    def __str__(self):
        return f"{self.account.name}: Dr {self.debit} / Cr {self.credit}"

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.debit and self.credit:
            raise ValidationError("A line cannot have both a debit and a credit amount.")
        if not self.debit and not self.credit:
            raise ValidationError("A line must have either a debit or a credit amount.")
        if self.account_id and self.account.is_group:
            raise ValidationError(f"'{self.account.name}' is a header account and cannot be posted to directly.")


# =============================================================
# ACADEMIC MANAGEMENT (premium — gated by the 'academic_management'
# DynamicFeature). Course/Classification/Section/Subject stay exactly as
# they are; everything here is additive — Course.teacher/Subject.teacher
# remain the "primary teacher" FK, unchanged, for every existing reader.
# =============================================================

class AcademicYear(models.Model):
    STATUS_CHOICES = (('active', 'Active'), ('archived', 'Archived'))

    org = models.ForeignKey(Organization, related_name='academic_years', on_delete=models.CASCADE)
    name = models.CharField(max_length=50, help_text="e.g. 2082/83 or 2025-26")
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    is_current = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('org', 'name')
        ordering = ('-start_date', 'name')

    def __str__(self):
        return self.name


class Faculty(models.Model):
    """Science/Management/Humanities-style grouping — colleges use this,
    schools can simply leave it unused (nothing else requires it)."""
    STATUS_CHOICES = (('active', 'Active'), ('inactive', 'Inactive'))

    org = models.ForeignKey(Organization, related_name='faculties', on_delete=models.CASCADE)
    name = models.CharField(max_length=150)
    code = models.CharField(max_length=50, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')

    class Meta:
        unique_together = ('org', 'name')
        ordering = ('name',)

    def __str__(self):
        return self.name


class Semester(models.Model):
    STATUS_CHOICES = (('active', 'Active'), ('completed', 'Completed'), ('archived', 'Archived'))

    org = models.ForeignKey(Organization, related_name='semesters', on_delete=models.CASCADE)
    faculty = models.ForeignKey(Faculty, related_name='semesters', on_delete=models.SET_NULL, null=True, blank=True)
    academic_year = models.ForeignKey(AcademicYear, related_name='semesters', on_delete=models.SET_NULL, null=True, blank=True)
    name = models.CharField(max_length=100, help_text="e.g. Semester 1")
    order = models.PositiveIntegerField(default=1)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')

    class Meta:
        ordering = ('order', 'name')

    def __str__(self):
        return f"{self.name} ({self.academic_year})" if self.academic_year else self.name


class StudentCourseEnrollment(models.Model):
    """Historical academic placement for a student.

    member.courses/classification/section remain the current-placement
    compatibility fields. This model records the dated, academic-year-aware
    placement required for subject rosters and historical reporting.
    """
    STATUS_CHOICES = (
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('transferred', 'Transferred'),
        ('cancelled', 'Cancelled'),
    )

    org = models.ForeignKey(Organization, related_name='student_course_enrollments', on_delete=models.CASCADE)
    branch = models.ForeignKey(Branch, related_name='student_course_enrollments', on_delete=models.SET_NULL, null=True, blank=True)
    academic_year = models.ForeignKey(AcademicYear, related_name='student_enrollments', on_delete=models.SET_NULL, null=True, blank=True)
    student = models.ForeignKey(member, related_name='course_enrollments', on_delete=models.CASCADE)
    course = models.ForeignKey(Course, related_name='student_enrollments', on_delete=models.CASCADE)
    classification = models.ForeignKey(Classification, related_name='student_enrollments', on_delete=models.CASCADE)
    section = models.ForeignKey(Section, related_name='student_enrollments', on_delete=models.SET_NULL, null=True, blank=True)
    start_date = models.DateField(default=timezone.localdate)
    end_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    notes = models.TextField(null=True, blank=True)
    created_by = models.ForeignKey(CustomUser, related_name='+', on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('-start_date', 'student__name')
        indexes = [
            models.Index(fields=['org', 'academic_year', 'course', 'status']),
            models.Index(fields=['org', 'classification', 'section', 'status']),
            models.Index(fields=['student', 'status']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['student', 'course', 'classification', 'section', 'academic_year', 'start_date'],
                name='unique_student_academic_enrollment_start',
            ),
        ]

    def clean(self):
        errors = {}
        if self.student_id and self.org_id and self.student.org_id != self.org_id:
            errors['student'] = "Student must belong to the enrollment organization."
        if self.course_id and self.org_id and self.course.org_id != self.org_id:
            errors['course'] = "Course must belong to the enrollment organization."
        if self.classification_id:
            if self.classification.org_id != self.org_id:
                errors['classification'] = "Classification must belong to the enrollment organization."
            elif self.course_id and not self.course.classifications.filter(pk=self.classification_id).exists():
                errors['classification'] = "Classification is not linked to this course."
        if self.section_id:
            if self.section.org_id != self.org_id or self.section.classification_id != self.classification_id:
                errors['section'] = "Section must belong to the selected classification and organization."
            elif self.course_id and self.course.sections.exists() and not self.course.sections.filter(pk=self.section_id).exists():
                errors['section'] = "Section is not linked to this course."
        if self.branch_id and self.branch.org_id != self.org_id:
            errors['branch'] = "Branch must belong to the enrollment organization."
        if self.academic_year_id and self.academic_year.org_id != self.org_id:
            errors['academic_year'] = "Academic year must belong to the enrollment organization."
        if self.end_date and self.start_date and self.end_date < self.start_date:
            errors['end_date'] = "End date cannot be before start date."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.student} → {self.course} / {self.classification}"


class CourseTeacherAssignment(models.Model):
    """Additive many-to-many for Course teachers. Course.teacher (the
    existing single FK) stays as the 'primary teacher' for backward
    compatibility — assigning here with is_primary=True keeps it in sync."""
    course = models.ForeignKey(Course, related_name='teacher_assignments', on_delete=models.CASCADE)
    teacher = models.ForeignKey(CustomUser, related_name='course_assignments', on_delete=models.CASCADE)
    is_primary = models.BooleanField(default=False)
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('course', 'teacher')

    def __str__(self):
        return f"{self.teacher} → {self.course}" + (" (primary)" if self.is_primary else "")

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_primary:
            self.course.teacher = self.teacher
            self.course.save(update_fields=['teacher'])


class SubjectTeacherAssignment(models.Model):
    """Dated teacher authority for one subject/course/class/section scope."""
    STATUS_CHOICES = (
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('completed', 'Completed'),
    )

    org = models.ForeignKey(Organization, related_name='subject_teacher_assignments', on_delete=models.CASCADE, null=True, blank=True)
    branch = models.ForeignKey(Branch, related_name='subject_teacher_assignments', on_delete=models.SET_NULL, null=True, blank=True)
    academic_year = models.ForeignKey(AcademicYear, related_name='subject_teacher_assignments', on_delete=models.SET_NULL, null=True, blank=True)
    course = models.ForeignKey(Course, related_name='subject_teacher_assignments', on_delete=models.SET_NULL, null=True, blank=True)
    classification = models.ForeignKey(Classification, related_name='subject_teacher_assignments', on_delete=models.SET_NULL, null=True, blank=True)
    section = models.ForeignKey(Section, related_name='subject_teacher_assignments', on_delete=models.SET_NULL, null=True, blank=True)
    subject = models.ForeignKey(Subject, related_name='teacher_assignments', on_delete=models.CASCADE)
    teacher = models.ForeignKey(CustomUser, related_name='subject_assignments', on_delete=models.CASCADE)
    is_primary = models.BooleanField(default=False)
    start_date = models.DateField(default=timezone.localdate)
    end_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    notes = models.TextField(null=True, blank=True)
    assigned_by = models.ForeignKey(CustomUser, related_name='subject_assignments_created', on_delete=models.SET_NULL, null=True, blank=True)
    assigned_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('course__name', 'classification__name', 'section__name', 'subject__name')
        indexes = [
            models.Index(fields=['org', 'academic_year', 'course', 'status']),
            models.Index(fields=['org', 'classification', 'section', 'status']),
            models.Index(fields=['teacher', 'status', 'start_date', 'end_date']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['subject', 'teacher', 'academic_year', 'section', 'start_date'],
                name='unique_subject_teacher_year_start',
            ),
        ]

    def __str__(self):
        return f"{self.teacher} → {self.subject}" + (" (primary)" if self.is_primary else "")

    def clean(self):
        errors = {}
        subject_org_id = self.subject.org_id if self.subject_id else None
        if self.org_id and subject_org_id and self.org_id != subject_org_id:
            errors['org'] = "Assignment organization must match the subject."
        if self.teacher_id:
            staff_org_id = Staff.objects.filter(admin_id=self.teacher_id).values_list('org_id', flat=True).first()
            if staff_org_id != (self.org_id or subject_org_id):
                errors['teacher'] = "Teacher must belong to the subject organization."
        if self.academic_year_id and self.academic_year.org_id != (self.org_id or subject_org_id):
            errors['academic_year'] = "Academic year must belong to the assignment organization."
        if self.section_id:
            if self.section.org_id != (self.org_id or subject_org_id):
                errors['section'] = "Section must belong to the assignment organization."
            elif self.subject_id and self.section.classification_id != self.subject.classification_id:
                errors['section'] = "Section must belong to the subject classification."
            elif self.subject_id and self.subject.section_id and self.section_id != self.subject.section_id:
                errors['section'] = "A section-specific subject cannot be assigned to another section."
        if self.end_date and self.start_date and self.end_date < self.start_date:
            errors['end_date'] = "End date cannot be before start date."
        if errors:
            raise ValidationError(errors)

    def is_active_on(self, value=None):
        value = value or timezone.localdate()
        return (
            self.status == 'active'
            and self.start_date <= value
            and (self.end_date is None or self.end_date >= value)
        )

    def save(self, *args, **kwargs):
        if self.subject_id:
            self.org_id = self.subject.org_id
            self.course_id = self.subject.course_id
            self.classification_id = self.subject.classification_id
            # A section-neutral subject may be delegated per section. A
            # section-specific subject always keeps its own exact section.
            if self.subject.section_id:
                self.section_id = self.subject.section_id
            if not self.branch_id:
                self.branch_id = (
                    getattr(self.subject.course, 'branch_id', None)
                    or self.subject.classification.primary_branch_id
                )
        super().save(*args, **kwargs)
        if self.is_primary:
            self.subject.teacher = self.teacher
            self.subject.save(update_fields=['teacher'])


# ── Assignment Module ───────────────────────────────────────────────────

class Assignment(models.Model):
    VISIBILITY_CHOICES = (('draft', 'Draft'), ('published', 'Published'))
    STATUS_CHOICES = (('open', 'Open'), ('closed', 'Closed'), ('archived', 'Archived'))

    org = models.ForeignKey(Organization, related_name='assignments', on_delete=models.CASCADE)
    branch = models.ForeignKey(Branch, related_name='assignments', on_delete=models.SET_NULL, null=True, blank=True)
    classification = models.ForeignKey(Classification, related_name='assignments', on_delete=models.CASCADE)
    section = models.ForeignKey('Section', related_name='assignments', on_delete=models.SET_NULL, null=True, blank=True)
    subject = models.ForeignKey(Subject, related_name='assignments', on_delete=models.CASCADE)
    teacher_assignment = models.ForeignKey(
        SubjectTeacherAssignment,
        related_name='assignments',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    course = models.ForeignKey(Course, related_name='assignments', on_delete=models.SET_NULL, null=True, blank=True)
    semester = models.ForeignKey(Semester, related_name='assignments', on_delete=models.SET_NULL, null=True, blank=True)

    title = models.CharField(max_length=250)
    description = models.TextField(null=True, blank=True)
    instructions = models.TextField(null=True, blank=True)
    assigned_by = models.ForeignKey(CustomUser, related_name='assignments_created', on_delete=models.SET_NULL, null=True, blank=True)
    start_date = models.DateField(default=timezone.localdate)
    due_date = models.DateField()
    total_marks = models.DecimalField(max_digits=6, decimal_places=2, default=100)
    passing_marks = models.DecimalField(max_digits=6, decimal_places=2, default=40)
    visibility = models.CharField(max_length=20, choices=VISIBILITY_CHOICES, default='draft')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('-due_date', '-id')

    def __str__(self):
        return self.title

    def clean(self):
        errors = {}
        if self.subject_id:
            if self.subject.org_id != self.org_id:
                errors['subject'] = "Subject must belong to the assignment organization."
            if self.classification_id != self.subject.classification_id:
                errors['classification'] = "Classification must match the selected subject."
            if self.subject.course_id != self.course_id:
                errors['course'] = "Course must match the selected subject."
            if self.subject.section_id and self.section_id != self.subject.section_id:
                errors['section'] = "Section must match the selected subject."
            if self.section_id and self.section.classification_id != self.classification_id:
                errors['section'] = "Section must belong to the selected classification."
        if self.teacher_assignment_id:
            scope = self.teacher_assignment
            if (
                scope.org_id != self.org_id
                or scope.subject_id != self.subject_id
                or scope.classification_id != self.classification_id
                or scope.section_id != self.section_id
            ):
                errors['teacher_assignment'] = "Teacher assignment must match the exact academic scope."
        if self.due_date and self.start_date and self.due_date < self.start_date:
            errors['due_date'] = "Due date cannot be before the start date."
        if self.total_marks is not None and self.total_marks <= 0:
            errors['total_marks'] = "Total marks must be greater than zero."
        if self.passing_marks is not None and (
            self.passing_marks < 0 or self.passing_marks > self.total_marks
        ):
            errors['passing_marks'] = "Passing marks must be between zero and total marks."
        if errors:
            raise ValidationError(errors)

    def submission_count(self):
        return self.submissions.count()

    def graded_count(self):
        return self.submissions.filter(status='graded').count()


class AssignmentAttachment(models.Model):
    assignment = models.ForeignKey(Assignment, related_name='attachments', on_delete=models.CASCADE)
    file = models.FileField(upload_to='assignments/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.file.name


class AssignmentSubmission(models.Model):
    STATUS_CHOICES = (
        ('submitted', 'Submitted'),
        ('reviewed', 'Reviewed'),
        ('graded', 'Graded'),
        ('returned', 'Returned'),
        ('resubmission_requested', 'Resubmission Requested'),
    )

    assignment = models.ForeignKey(Assignment, related_name='submissions', on_delete=models.CASCADE)
    student = models.ForeignKey('member', related_name='assignment_submissions', on_delete=models.CASCADE)
    submitted_at = models.DateTimeField(null=True, blank=True)
    is_late = models.BooleanField(default=False)
    remarks = models.CharField(max_length=255, null=True, blank=True)
    student_comments = models.TextField(null=True, blank=True)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='submitted')
    obtained_marks = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    graded_by = models.ForeignKey(CustomUser, related_name='assignments_graded', on_delete=models.SET_NULL, null=True, blank=True)
    graded_at = models.DateTimeField(null=True, blank=True)
    teacher_remarks = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('assignment', 'student')
        ordering = ('-submitted_at',)

    def __str__(self):
        return f"{self.student.name} — {self.assignment.title}"

    def save(self, *args, **kwargs):
        if self.submitted_at and self.assignment_id:
            due = self.assignment.due_date
            submitted_date = self.submitted_at.date() if hasattr(self.submitted_at, 'date') else self.submitted_at
            self.is_late = submitted_date > due
        super().save(*args, **kwargs)


class AssignmentSubmissionAttachment(models.Model):
    submission = models.ForeignKey(AssignmentSubmission, related_name='attachments', on_delete=models.CASCADE)
    file = models.FileField(upload_to='assignment_submissions/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.file.name


class AssignmentSubmissionHistory(models.Model):
    """Append-only audit trail — every resubmission or grading change on a
    submission gets its own row here, so 'complete submission history' is a
    real log rather than an overwritten 'latest' record."""
    submission = models.ForeignKey(AssignmentSubmission, related_name='history', on_delete=models.CASCADE)
    action = models.CharField(max_length=30, help_text="submitted / resubmitted / graded / returned")
    status = models.CharField(max_length=30)
    obtained_marks = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    remarks = models.CharField(max_length=255, null=True, blank=True)
    performed_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('created_at',)

    def __str__(self):
        return f"{self.submission} — {self.action}"


# ── Homework Module ─────────────────────────────────────────────────────

class Homework(models.Model):
    PRIORITY_CHOICES = (('low', 'Low'), ('medium', 'Medium'), ('high', 'High'))
    FREQUENCY_CHOICES = (('one_time', 'One-time'), ('daily', 'Daily'), ('weekly', 'Weekly'))
    STATUS_CHOICES = (('active', 'Active'), ('closed', 'Closed'))

    org = models.ForeignKey(Organization, related_name='homeworks', on_delete=models.CASCADE)
    branch = models.ForeignKey(Branch, related_name='homeworks', on_delete=models.SET_NULL, null=True, blank=True)
    classification = models.ForeignKey(Classification, related_name='homeworks', on_delete=models.CASCADE)
    section = models.ForeignKey('Section', related_name='homeworks', on_delete=models.SET_NULL, null=True, blank=True)
    subject = models.ForeignKey(Subject, related_name='homeworks', on_delete=models.CASCADE)
    teacher_assignment = models.ForeignKey(
        SubjectTeacherAssignment,
        related_name='homeworks',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    assigned_by = models.ForeignKey(CustomUser, related_name='homeworks_created', on_delete=models.SET_NULL, null=True, blank=True)

    description = models.TextField()
    due_date = models.DateField()
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='medium')
    estimated_time_minutes = models.PositiveIntegerField(null=True, blank=True)
    frequency = models.CharField(max_length=20, choices=FREQUENCY_CHOICES, default='one_time')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-due_date', '-id')

    def __str__(self):
        return f"{self.subject.name} — {self.due_date}"

    def clean(self):
        errors = {}
        if self.subject_id:
            if self.subject.org_id != self.org_id:
                errors['subject'] = "Subject must belong to the homework organization."
            if self.classification_id != self.subject.classification_id:
                errors['classification'] = "Classification must match the selected subject."
            if self.subject.section_id and self.section_id != self.subject.section_id:
                errors['section'] = "Section must match the selected subject."
            if self.section_id and self.section.classification_id != self.classification_id:
                errors['section'] = "Section must belong to the selected classification."
        if self.teacher_assignment_id:
            scope = self.teacher_assignment
            if (
                scope.org_id != self.org_id
                or scope.subject_id != self.subject_id
                or scope.classification_id != self.classification_id
                or scope.section_id != self.section_id
            ):
                errors['teacher_assignment'] = "Teacher assignment must match the exact academic scope."
        if errors:
            raise ValidationError(errors)

    def completion_count(self):
        return self.statuses.filter(status='completed').count()


class HomeworkAttachment(models.Model):
    homework = models.ForeignKey(Homework, related_name='attachments', on_delete=models.CASCADE)
    file = models.FileField(upload_to='homework/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.file.name


class HomeworkStatus(models.Model):
    STATUS_CHOICES = (('pending', 'Pending'), ('completed', 'Completed'))

    homework = models.ForeignKey(Homework, related_name='statuses', on_delete=models.CASCADE)
    student = models.ForeignKey('member', related_name='homework_statuses', on_delete=models.CASCADE)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    completed_at = models.DateTimeField(null=True, blank=True)
    verified_by_teacher = models.BooleanField(default=False)
    verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('homework', 'student')

    def __str__(self):
        return f"{self.student.name} — {self.homework} ({self.status})"


# ── Course Material Module ──────────────────────────────────────────────

class CourseMaterial(models.Model):
    TYPE_CHOICES = (
        ('pdf', 'PDF'), ('ppt', 'PPT'), ('doc', 'Document'), ('video', 'Video'),
        ('audio', 'Audio'), ('image', 'Image'), ('link', 'External Link'), ('notes', 'Notes'),
    )

    org = models.ForeignKey(Organization, related_name='course_materials', on_delete=models.CASCADE)
    branch = models.ForeignKey(Branch, related_name='course_materials', on_delete=models.SET_NULL, null=True, blank=True)
    faculty = models.ForeignKey(Faculty, related_name='course_materials', on_delete=models.SET_NULL, null=True, blank=True)
    course = models.ForeignKey(Course, related_name='materials', on_delete=models.SET_NULL, null=True, blank=True)
    semester = models.ForeignKey(Semester, related_name='course_materials', on_delete=models.SET_NULL, null=True, blank=True)
    subject = models.ForeignKey(Subject, related_name='materials', on_delete=models.CASCADE)

    chapter = models.CharField(max_length=150, null=True, blank=True)
    unit = models.CharField(max_length=150, null=True, blank=True)
    title = models.CharField(max_length=250)
    material_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='notes')
    file = models.FileField(upload_to='course_materials/', null=True, blank=True)
    external_link = models.URLField(null=True, blank=True)
    uploaded_by = models.ForeignKey(CustomUser, related_name='materials_uploaded', on_delete=models.SET_NULL, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-created_at',)

    def __str__(self):
        return self.title

    def view_count(self):
        return self.access_logs.filter(access_type='view').count()

    def download_count(self):
        return self.access_logs.filter(access_type='download').count()


class CourseMaterialAccess(models.Model):
    ACCESS_CHOICES = (('view', 'View'), ('download', 'Download'))

    material = models.ForeignKey(CourseMaterial, related_name='access_logs', on_delete=models.CASCADE)
    student = models.ForeignKey('member', related_name='material_access_logs', on_delete=models.CASCADE)
    access_type = models.CharField(max_length=20, choices=ACCESS_CHOICES, default='view')
    accessed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-accessed_at',)

    def __str__(self):
        return f"{self.student.name} {self.access_type} {self.material.title}"


# ── Daily Teaching Log ──────────────────────────────────────────────────

class TeachingLog(models.Model):
    STATUS_CHOICES = (
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    )

    org = models.ForeignKey(Organization, related_name='teaching_logs', on_delete=models.CASCADE)
    branch = models.ForeignKey(Branch, related_name='teaching_logs', on_delete=models.SET_NULL, null=True, blank=True)
    academic_year = models.ForeignKey(AcademicYear, related_name='teaching_logs', on_delete=models.SET_NULL, null=True, blank=True)
    course = models.ForeignKey(Course, related_name='teaching_logs', on_delete=models.SET_NULL, null=True, blank=True)
    teacher_assignment = models.ForeignKey(SubjectTeacherAssignment, related_name='teaching_logs', on_delete=models.SET_NULL, null=True, blank=True)
    routine_period = models.ForeignKey('RoutinePeriod', related_name='teaching_logs', on_delete=models.SET_NULL, null=True, blank=True)
    teacher = models.ForeignKey(CustomUser, related_name='teaching_logs', on_delete=models.CASCADE)
    subject = models.ForeignKey(Subject, related_name='teaching_logs', on_delete=models.CASCADE)
    classification = models.ForeignKey(Classification, related_name='teaching_logs', on_delete=models.CASCADE)
    section = models.ForeignKey('Section', related_name='teaching_logs', on_delete=models.SET_NULL, null=True, blank=True)

    date = models.DateField(default=timezone.localdate)
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    period = models.PositiveIntegerField(null=True, blank=True)
    room = models.CharField(max_length=100, null=True, blank=True)
    topic_covered = models.CharField(max_length=255)
    chapter = models.CharField(max_length=150, null=True, blank=True)
    learning_objectives = models.TextField(null=True, blank=True)
    homework_given = models.ForeignKey(Homework, related_name='teaching_logs', on_delete=models.SET_NULL, null=True, blank=True)
    attendance_present = models.PositiveIntegerField(null=True, blank=True)
    attendance_absent = models.PositiveIntegerField(null=True, blank=True)
    attendance_late = models.PositiveIntegerField(default=0)
    attendance_excused = models.PositiveIntegerField(default=0)
    attendance_leave = models.PositiveIntegerField(default=0)
    remarks = models.TextField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='submitted')
    created_by = models.ForeignKey(CustomUser, related_name='teaching_logs_created', on_delete=models.SET_NULL, null=True, blank=True)
    submitted_by = models.ForeignKey(CustomUser, related_name='teaching_logs_submitted', on_delete=models.SET_NULL, null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(CustomUser, related_name='teaching_logs_approved', on_delete=models.SET_NULL, null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(CustomUser, related_name='teaching_logs_reviewed', on_delete=models.SET_NULL, null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-date', '-id')
        indexes = [
            models.Index(fields=['org', 'date', 'status']),
            models.Index(fields=['org', 'course', 'classification', 'section']),
            models.Index(fields=['teacher', 'date', 'status']),
            models.Index(fields=['subject', 'date', 'period']),
        ]

    def __str__(self):
        return f"{self.teacher} — {self.subject.name} — {self.date}"

    def recompute_attendance_counts(self):
        self.attendance_present = self.attendance_records.filter(status='present').count()
        self.attendance_absent = self.attendance_records.filter(status='absent').count()
        self.attendance_late = self.attendance_records.filter(status='late').count()
        self.attendance_excused = self.attendance_records.filter(status='excused').count()
        self.attendance_leave = self.attendance_records.filter(status='leave').count()
        self.save(update_fields=[
            'attendance_present', 'attendance_absent', 'attendance_late',
            'attendance_excused', 'attendance_leave',
        ])


class TeachingLogAttachment(models.Model):
    log = models.ForeignKey(TeachingLog, related_name='attachments', on_delete=models.CASCADE)
    file = models.FileField(upload_to='teaching_logs/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.file.name


class SubjectAttendanceRecord(models.Model):
    """Per-student attendance for one Teaching Log (one subject-period on one
    day) — a student can have several of these per day, one per subject."""
    STATUS_CHOICES = (
        ('present', 'Present'),
        ('absent', 'Absent'),
        ('late', 'Late'),
        ('excused', 'Excused'),
        ('leave', 'Leave'),
    )

    org = models.ForeignKey(Organization, related_name='subject_attendance_records', on_delete=models.CASCADE)
    teaching_log = models.ForeignKey(TeachingLog, related_name='attendance_records', on_delete=models.CASCADE)
    member = models.ForeignKey('member', related_name='subject_attendance_records', on_delete=models.CASCADE)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='present')
    remarks = models.CharField(max_length=255, null=True, blank=True)
    marked_by = models.ForeignKey(CustomUser, related_name='+', on_delete=models.SET_NULL, null=True, blank=True)
    marked_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('teaching_log', 'member')
        ordering = ('member__name',)
        indexes = [
            models.Index(fields=['org', 'status']),
            models.Index(fields=['member', 'status']),
        ]

    def __str__(self):
        return f"{self.member} — {self.teaching_log} — {self.status}"


# ── Class Routine ────────────────────────────────────────────────────────

class RoutinePeriod(models.Model):
    SHIFT_CHOICES = (('morning', 'Morning'), ('day', 'Day'), ('evening', 'Evening'))
    DAY_CHOICES = (
        (0, 'Sunday'), (1, 'Monday'), (2, 'Tuesday'), (3, 'Wednesday'),
        (4, 'Thursday'), (5, 'Friday'), (6, 'Saturday'),
    )

    org = models.ForeignKey(Organization, related_name='routine_periods', on_delete=models.CASCADE)
    branch = models.ForeignKey(Branch, related_name='routine_periods', on_delete=models.SET_NULL, null=True, blank=True)
    classification = models.ForeignKey(Classification, related_name='routine_periods', on_delete=models.CASCADE)
    section = models.ForeignKey('Section', related_name='routine_periods', on_delete=models.SET_NULL, null=True, blank=True)
    subject = models.ForeignKey(Subject, related_name='routine_periods', on_delete=models.CASCADE)
    teacher = models.ForeignKey(CustomUser, related_name='routine_periods', on_delete=models.CASCADE)
    teacher_assignment = models.ForeignKey(
        SubjectTeacherAssignment,
        related_name='routine_periods',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    academic_year = models.ForeignKey(AcademicYear, related_name='routine_periods', on_delete=models.SET_NULL, null=True, blank=True)

    day_of_week = models.PositiveSmallIntegerField(choices=DAY_CHOICES)
    period_number = models.PositiveIntegerField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    room = models.CharField(max_length=100, null=True, blank=True)
    shift = models.CharField(max_length=20, choices=SHIFT_CHOICES, default='day')
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ('day_of_week', 'period_number')

    def __str__(self):
        return f"{self.classification} — {self.get_day_of_week_display()} P{self.period_number}"

    def save(self, *args, **kwargs):
        if self.subject_id and self.teacher_id:
            selected_assignment = None
            if self.teacher_assignment_id:
                selected_assignment = SubjectTeacherAssignment.objects.filter(
                    pk=self.teacher_assignment_id,
                    org_id=self.org_id,
                    subject_id=self.subject_id,
                    teacher_id=self.teacher_id,
                    classification_id=self.classification_id,
                    status='active',
                ).first()
                if (
                    selected_assignment
                    and selected_assignment.section_id
                    and selected_assignment.section_id != self.section_id
                ):
                    selected_assignment = None
            if selected_assignment:
                self.teacher_assignment = selected_assignment
            else:
                assignment_qs = SubjectTeacherAssignment.objects.filter(
                    subject_id=self.subject_id,
                    teacher_id=self.teacher_id,
                    status='active',
                )
                if self.academic_year_id:
                    assignment_qs = assignment_qs.filter(
                        models.Q(academic_year_id=self.academic_year_id)
                        | models.Q(academic_year__isnull=True)
                    )
                if self.section_id:
                    assignment_qs = assignment_qs.filter(
                        models.Q(section_id=self.section_id)
                        | models.Q(section__isnull=True)
                    )
                else:
                    assignment_qs = assignment_qs.filter(section__isnull=True)
                self.teacher_assignment = assignment_qs.order_by(
                    '-section_id', '-is_primary', '-start_date', '-pk',
                ).first()
        super().save(*args, **kwargs)


# ── In-App Notifications (email uses the existing EmailLog/email_utils
# chokepoint; push is out of scope — see plan) ──────────────────────────

class InAppNotification(models.Model):
    EVENT_CHOICES = (
        ('homework_assigned', 'Homework Assigned'),
        ('assignment_assigned', 'Assignment Assigned'),
        ('assignment_due', 'Assignment Due'),
        ('submission_received', 'Submission Received'),
        ('marks_published', 'Marks Published'),
        ('course_material_added', 'New Course Material'),
        ('teaching_log_reviewed', 'Teaching Log Reviewed'),
        ('task_assigned', 'Task Assigned'),
        ('task_started', 'Task Started'),
        ('task_due_today', 'Task Due Today'),
        ('task_overdue', 'Task Overdue'),
        ('task_completed', 'Task Completed'),
        ('task_not_completed', 'Task Not Completed'),
        ('task_approved', 'Task Approved'),
        ('task_rejected', 'Task Rejected'),
        ('task_reassigned', 'Task Reassigned'),
        ('task_cancelled', 'Task Cancelled'),
    )
    PRIORITY_CHOICES = (
        ('low', 'Low'),
        ('normal', 'Normal'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    )

    org = models.ForeignKey(Organization, related_name='in_app_notifications', on_delete=models.CASCADE)
    # Keep the original member recipient for existing academic notifications,
    # while allowing school administrators (who have no member profile) to
    # receive the same notification stream.
    recipient = models.ForeignKey(
        'member', related_name='in_app_notifications',
        on_delete=models.CASCADE, null=True, blank=True,
    )
    recipient_user = models.ForeignKey(
        'management.CustomUser', related_name='direct_in_app_notifications',
        on_delete=models.CASCADE, null=True, blank=True,
    )
    actor = models.ForeignKey(
        'management.CustomUser', related_name='triggered_in_app_notifications',
        on_delete=models.SET_NULL, null=True, blank=True,
    )
    event_type = models.CharField(max_length=30, choices=EVENT_CHOICES)
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='normal')
    title = models.CharField(max_length=200)
    body = models.CharField(max_length=500, null=True, blank=True)
    link_url = models.CharField(max_length=255, null=True, blank=True)
    action_label = models.CharField(max_length=60, blank=True)
    dedupe_key = models.CharField(max_length=190, null=True, blank=True, unique=True)
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-created_at',)
        indexes = [
            models.Index(fields=('org', 'is_read', 'created_at'), name='notif_org_read_created_idx'),
            models.Index(fields=('recipient', 'is_read'), name='notif_member_read_idx'),
            models.Index(fields=('recipient_user', 'is_read'), name='notif_user_read_idx'),
        ]
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(recipient__isnull=False)
                    | models.Q(recipient_user__isnull=False)
                ),
                name='notification_has_recipient',
            ),
        ]

    def __str__(self):
        target = self.recipient.name if self.recipient_id else (
            self.recipient_user.get_full_name()
            or self.recipient_user.username
            if self.recipient_user_id else 'Unknown recipient'
        )
        return f"{target} — {self.title}"

    @property
    def icon_class(self):
        if self.event_type.startswith('task_'):
            return {
                'task_assigned': 'fa-clipboard-check',
                'task_started': 'fa-play',
                'task_due_today': 'fa-clock',
                'task_overdue': 'fa-triangle-exclamation',
                'task_completed': 'fa-circle-check',
                'task_not_completed': 'fa-circle-xmark',
                'task_approved': 'fa-thumbs-up',
                'task_rejected': 'fa-rotate-left',
                'task_reassigned': 'fa-user-pen',
                'task_cancelled': 'fa-ban',
            }.get(self.event_type, 'fa-list-check')
        return {
            'homework_assigned': 'fa-book-open',
            'assignment_assigned': 'fa-file-pen',
            'assignment_due': 'fa-hourglass-half',
            'submission_received': 'fa-file-circle-check',
            'marks_published': 'fa-award',
            'course_material_added': 'fa-folder-open',
            'teaching_log_reviewed': 'fa-chalkboard-user',
        }.get(self.event_type, 'fa-bell')

    @property
    def tone(self):
        if self.priority == 'urgent' or self.event_type in ('task_overdue', 'task_rejected'):
            return 'danger'
        if self.priority == 'high' or self.event_type in ('task_due_today', 'task_not_completed'):
            return 'warning'
        if self.event_type in ('task_completed', 'task_approved', 'marks_published'):
            return 'success'
        return 'primary'
