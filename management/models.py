from django.db import models
from django.contrib.auth.models import AbstractUser
from django.dispatch import receiver
from django.db.models.signals import post_save
from django.core.validators import MinValueValidator
from django.utils import timezone
import uuid as _uuid

import datetime
from decimal import Decimal

# Create your models here.

class CustomUser(AbstractUser):
    user_type_data = (("1", "superadmin"), ("2", 'schooladmin'), ("3", 'staff'), ("4", "agent"))
    user_type = models.CharField(default = "1", choices = user_type_data, max_length = 10)
    email = models.EmailField(unique = True)
    

def default_allowed_features():
    # New organizations start with only the FREE features (attendance methods,
    # payroll, leave). Paid modules are granted by the superadmin per org.
    from school.features import FREE_FEATURES
    return sorted(FREE_FEATURES)


class Organization(models.Model):
    id = models.AutoField(primary_key= True)
    CATEGORY_CHOICES = (
        ('school', 'School'),
        ('college', 'College'),
        ('bachelor', 'Bachelor'),
        ('institute', 'Institute/Consultancy'),
        ('office', 'Office'),
        ('industry', 'Industry'),
        ('others', 'Others'),
       
    )
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES, default='others')
    rfid_based = models.BooleanField(default=False)
    image = models.ImageField(upload_to="image", null= True, blank=True)
    address = models.CharField(max_length=200, null= True, blank= True)
    email = models.EmailField(max_length=254, null=True, blank=True, help_text="Organization's contact email, shown on the profile page and used as a reply-to for org-wide notices.")
    name = models.CharField(max_length=300)
    member_limit = models.IntegerField(default=25)
    default_shift_start_time = models.TimeField(default=datetime.time(9, 0), help_text="Company-wide default check-in time for new members.")
    default_shift_end_time = models.TimeField(default=datetime.time(17, 0), help_text="Company-wide default check-out time for new members.")
    expire_on = models.DateTimeField()
    serial_key = models.CharField(max_length=100)
    new_serial_key = models.CharField(max_length=100)
    activate = models.BooleanField(default=True)
    mutifeature_enable = models.BooleanField(default=False)
    location_based = models.BooleanField(default=False)
    qr_based = models.BooleanField(default=False)
    manual_attendance = models.BooleanField(default=False)
    auto_checkin = models.BooleanField(default=False)
    objects = models.Manager()
    # New update for Nepali Date
    nepali_date = models.BooleanField(default=False)
    free_demo = models.BooleanField(default=False)
    course_based_attendance = models.BooleanField(default=False)

    # ── Module Feature Flags ──────────────────────────────────────────────────
    # Each flag gates a full module in both admin sidebar and staff dashboard.
    # Defaults are False so new orgs start with a clean slate.
    feature_finance    = models.BooleanField(default=False, verbose_name="Finance (Income / Expense)")
    feature_billing    = models.BooleanField(default=False, verbose_name="Billing (Student Invoices)")
    feature_stock      = models.BooleanField(default=False, verbose_name="Stock Management")
    feature_tasks      = models.BooleanField(default=False, verbose_name="Task Management")
    feature_results    = models.BooleanField(default=False, verbose_name="Results & Exams")
    feature_hrms       = models.BooleanField(default=False, verbose_name="HR Module (Resignation / Documents)")
    feature_payroll    = models.BooleanField(default=False, verbose_name="Payroll & Payslips")
    feature_complaints = models.BooleanField(default=False, verbose_name="Complaints")
    feature_events     = models.BooleanField(default=False, verbose_name="Events")
    feature_branches   = models.BooleanField(default=False, verbose_name="Branch Management")
    feature_leave      = models.BooleanField(default=False, verbose_name="Leave Management")
    # Extended feature flags
    feature_study_gap       = models.BooleanField(default=False, verbose_name="Study Gap / Teaching Log")
    feature_bulk_export     = models.BooleanField(default=False, verbose_name="Bulk Data Export")
    feature_notifications   = models.BooleanField(default=False, verbose_name="Notifications / SMS Alerts")
    feature_courses         = models.BooleanField(default=False, verbose_name="Course Management")
    feature_student_mgmt    = models.BooleanField(default=False, verbose_name="Student Management")
    feature_member_mgmt     = models.BooleanField(default=True,  verbose_name="Member / Staff Management")
    enable_qr_attendance    = models.BooleanField(default=False, verbose_name="Dynamic QR Attendance")
    feature_timesheet       = models.BooleanField(default=False, verbose_name="Timesheet Management")
    feature_id_cards        = models.BooleanField(default=False, verbose_name="ID Card Generation")
    feature_field_visits    = models.BooleanField(default=False, verbose_name="Field Visit / Location Sharing")
    feature_clients         = models.BooleanField(default=False, verbose_name="Client Follow-Up (CRM)")
    feature_face_attendance = models.BooleanField(default=False, verbose_name="Face Attendance")
    feature_notices         = models.BooleanField(default=False, verbose_name="Notice Board / Announcements")
    # ─────────────────────────────────────────────────────────────────────────

    # ── Org Type Presets ─────────────────────────────────────────────────────
    ORG_TYPE_PRESETS = {
        'school':    ['feature_leave', 'feature_results', 'feature_billing', 'feature_student_mgmt', 'feature_courses', 'feature_complaints', 'feature_events'],
        'college':   ['feature_leave', 'feature_results', 'feature_billing', 'feature_student_mgmt', 'feature_courses', 'feature_complaints', 'feature_finance'],
        'bachelor':  ['feature_leave', 'feature_results', 'feature_billing', 'feature_student_mgmt', 'feature_courses', 'feature_finance'],
        'institute': ['feature_leave', 'feature_payroll', 'feature_hrms', 'feature_finance', 'feature_student_mgmt', 'feature_courses'],
        'office':    ['feature_leave', 'feature_payroll', 'feature_hrms', 'feature_tasks', 'feature_finance', 'feature_bulk_export'],
        'industry':  ['feature_leave', 'feature_payroll', 'feature_hrms', 'feature_tasks', 'feature_finance', 'feature_stock', 'feature_timesheet', 'feature_branches'],
        'others':    [],
    }

    # ── Agent / Subscription Fields ──────────────────────────────────────────
    agent = models.ForeignKey(
        'AgentProfile', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='organizations'
    )
    created_by_agent = models.BooleanField(default=False)
    subscription_plan = models.CharField(max_length=100, blank=True, default='')
    allowed_features = models.JSONField(
        default=default_allowed_features, blank=True,
        help_text="Feature keys this org's plan is allowed to use. Superadmin-controlled; schooladmin can only toggle features within this list.",
    )
    subscription_start = models.DateField(null=True, blank=True)
    subscription_end = models.DateField(null=True, blank=True)
    PAYMENT_STATUS_CHOICES = (
        ('paid', 'Paid'),
        ('unpaid', 'Unpaid'),
        ('partial', 'Partial'),
        ('trial', 'Trial'),
        ('expired', 'Expired'),
    )
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='trial')
    ORG_STATUS_CHOICES = (
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('suspended', 'Suspended'),
        ('trial', 'Trial'),
        ('expired', 'Expired'),
    )
    org_status = models.CharField(max_length=20, choices=ORG_STATUS_CHOICES, default='trial')
    created_at = models.DateTimeField(
        default=timezone.now,
        null=True,
        blank=True,
        editable=False,
        help_text="Immutable organization creation timestamp used as the subscription start date.",
    )
    custom_subscription_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Optional superadmin-defined annual amount. Overrides the calculated package and feature total.",
    )
    custom_amount_note = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Internal note explaining an agreed custom subscription amount.",
    )
    # ─────────────────────────────────────────────────────────────────────────

    def __str__(self):
        return self.name


class WifiBased(models.Model):
    """Allowed WiFi networks for attendance"""
    org = models.ForeignKey(
        'Organization',
        related_name="org_wifi",
        on_delete=models.CASCADE
    )
    name = models.CharField(max_length=200)
    bssid = models.CharField(max_length=100, help_text="WiFi BSSID/MAC address")
    ssid = models.CharField(max_length=200, help_text="WiFi network name")
 
    def __str__(self):
        return f"{self.name} ({self.ssid})"
 
 
class AttendanceMethod(models.TextChoices):
    MANUAL = 'manual', 'Manual'
    QR = 'qr', 'QR Code'
    LOCATION = 'location', 'Location'
    WIFI = 'wifi', 'WiFi'
    AUTO = 'auto', 'Auto Check-in'
    

class LocationBased(models.Model):
    org = models.ForeignKey(Organization, related_name="org_location", on_delete=models.CASCADE)
    name = models.CharField(max_length=200)
    latitude = models.FloatField()
    longitude = models.FloatField()
    radius = models.FloatField()

    def __str__(self):
        return self.name
    
    
class QRCode(models.Model):
    org = models.ForeignKey(Organization, related_name="org_qrcode", on_delete=models.CASCADE)
    name = models.CharField(max_length=200)
    qr_code = models.ImageField(upload_to='qrcodes/', null=True, blank=True)

    def __str__(self):
        return self.name


class AutoCheckin(models.Model):
    org = models.ForeignKey(Organization, related_name="org_auto_checkin", on_delete=models.CASCADE)
    member = models.ForeignKey('handle.member', related_name="member_auto_checkin", on_delete=models.CASCADE)
    auto_checked_in_by =models.ForeignKey(CustomUser, related_name="user_auto_checkin", on_delete=models.CASCADE, null=True, blank=True)
    name = models.CharField(max_length=200)
    checkin_time = models.DateTimeField()
    checkout_time = models.DateTimeField()

    def __str__(self):
        return self.name

class Holiday(models.Model):
    org = models.ForeignKey(Organization, related_name="org_holiday", on_delete=models.CASCADE)
    holiday = models.CharField(max_length=300)

    def __str__(self):
        return self.holiday


class OrganizationShiftOverride(models.Model):
    """A company-wide shift-time change for one specific date (e.g. a half-day
    Friday). Applies only to members on the plain default-shift path — i.e.
    members with no active Shift Management assignment of their own."""
    org = models.ForeignKey(Organization, related_name='shift_overrides', on_delete=models.CASCADE)
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    note = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-date',)
        constraints = [
            models.UniqueConstraint(fields=('org', 'date'), name='unique_org_shift_override_per_date'),
        ]

    def __str__(self):
        return f"{self.org.name} — {self.date}: {self.start_time}–{self.end_time}"


class Occasion(models.Model):
    name = models.CharField(max_length=200)
    org = models.ForeignKey(Organization, related_name="org_occasion", on_delete=models.CASCADE)
    date = models.DateField()
    end_date = models.DateField(null=True, blank=True)  # Optional end date for gap holidays

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=('org', 'name', 'date'),
                name='unique_occasion_name_date_per_org',
            ),
        ]

    def __str__(self):
        return self.name
    

class Superadmin(models.Model):
    id = models.AutoField(primary_key = True)
    admin = models.OneToOneField(CustomUser, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add= True)
    updated_at = models.DateTimeField(auto_now_add=True)
    objects = models.Manager()
    def __str__(self):
        return self.admin.username


class Schooladmin(models.Model):
    id = models.AutoField(primary_key = True)
    admin = models.OneToOneField(CustomUser, on_delete=models.CASCADE)
    org = models.ForeignKey(Organization, on_delete=models.CASCADE)
    number = models.BigIntegerField(null = True)
    objects = models.Manager()
    
    def __str__(self):
        return self.admin.first_name

class ContactUs(models.Model):
    fullname = models.CharField(max_length=200)
    email = models.EmailField(null= True, blank=True)
    number = models.BigIntegerField()
    message = models.TextField(null= True, blank= True)
    created_at = models.DateTimeField(auto_now_add=True, null=True)

    class Meta:
        ordering = ('-created_at', '-id')

    def __str__(self) -> str:
        return self.fullname


class PackageRequest(models.Model):
    """A visitor's 'Request this package' submission from the Pricing page —
    captures the exact quote (member count, chosen features, computed price)
    alongside their contact info, distinct from a generic ContactUs message."""
    full_name = models.CharField(max_length=200)
    email = models.EmailField()
    phone = models.CharField(max_length=30, blank=True, default='')
    member_limit = models.PositiveIntegerField()
    selected_feature_keys = models.JSONField(default=list, blank=True)
    package_name = models.CharField(max_length=200, blank=True, default='')
    base_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    feature_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    annual_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    note = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-created_at', '-id')

    def __str__(self):
        return f"{self.full_name} — {self.package_name} (Rs {self.annual_total})"


class Pricing(models.Model):
    name = models.CharField(max_length=200)
    price = models.IntegerField()
    limit = models.IntegerField()
    device = models.CharField(max_length=200)
    image = models.ImageField(upload_to='devices/', null=True, blank=True)

    def __str__(self) -> str:
        return self.name


class FeaturePrice(models.Model):
    """Superadmin-owned annual price catalog for built-in and dynamic features."""

    feature_key = models.SlugField(max_length=100, unique=True)
    label = models.CharField(max_length=150)
    annual_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(Decimal("0"))],
    )
    is_active = models.BooleanField(default=True)
    is_public = models.BooleanField(
        default=True,
        help_text="Show this feature in the public quotation calculator.",
    )
    display_order = models.PositiveIntegerField(default=100)
    updated_by = models.ForeignKey(
        CustomUser,
        related_name="feature_prices_updated",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("display_order", "label", "feature_key")

    def __str__(self):
        return f"{self.label} — Rs {self.annual_price}/year"

class LeaveType(models.Model):
    org = models.ForeignKey(Organization, on_delete=models.CASCADE)
    name = models.CharField(max_length=150, help_text="e.g., Sick Leave, Maternity Leave")
    annual_allocation = models.PositiveIntegerField(default=12, help_text="Days allowed per year")
    is_paid = models.BooleanField(
        default=True,
        help_text="If unchecked, approved leave of this type will be unpaid (deducted from salary)."
    )

    def __str__(self):
        return f"{self.name} ({'Paid' if self.is_paid else 'Unpaid'}, {self.annual_allocation}d)"


# 2. UPDATED: Your existing LeaveReport model
class LeaveReport(models.Model):
    member = models.ForeignKey('handle.member', on_delete=models.CASCADE) # Changed to lower-case 'member' based on your previous code
    org = models.ForeignKey(Organization, on_delete=models.CASCADE)
    
    # NEW: Link to LeaveType
    leave_type = models.ForeignKey(LeaveType, on_delete=models.SET_NULL, null=True, blank=True)
    
    gap_start = models.DateField(null=True, blank=True)
    gap_end = models.DateField(null=True, blank=True)
    approved = models.BooleanField(default=False)
    rejected = models.BooleanField(default=False)
    reason = models.TextField()
    seen = models.BooleanField(default=False)
    objects = models.Manager()

    def __str__(self):
        return f"{self.member.name} - {self.org.name}"
    
    def total_leave_days(self):
        if not self.gap_start:
            return 0
        if self.gap_end:
            return (self.gap_end - self.gap_start).days + 1
        return 0
    
# ============================================================
# APPOINTMENT BOOKING SYSTEM
# ============================================================

class AppointmentType(models.Model):
    org = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='appointment_types')
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    duration_minutes = models.PositiveIntegerField(default=30)
    color = models.CharField(max_length=20, default='#e11d48')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.org.name})"


class Appointment(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('cancelled', 'Cancelled'),
        ('completed', 'Completed'),
    )
    org = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='appointments')
    appointment_type = models.ForeignKey(AppointmentType, on_delete=models.SET_NULL, null=True, blank=True, related_name='appointments')
    token = models.UUIDField(default=_uuid.uuid4, editable=False, unique=True)
    # Visitor info
    name = models.CharField(max_length=200)
    email = models.EmailField()
    phone = models.CharField(max_length=20, blank=True)
    date = models.DateField()
    time = models.TimeField()
    message = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    admin_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-date', '-time')

    def __str__(self):
        return f"{self.name} — {self.date} {self.time}"


# ============================================================
# FORM BUILDER SYSTEM
# ============================================================

class CustomForm(models.Model):
    org = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='custom_forms')
    uuid = models.UUIDField(default=_uuid.uuid4, editable=False, unique=True)
    title = models.CharField(max_length=300)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    success_message = models.TextField(default='Thank you! Your response has been submitted.')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title} ({self.org.name})"

    def get_public_url(self):
        return f"/forms/{self.uuid}/"


class FormField(models.Model):
    FIELD_TYPES = (
        ('text', 'Short Text'),
        ('textarea', 'Long Text'),
        ('email', 'Email'),
        ('tel', 'Phone'),
        ('number', 'Number'),
        ('date', 'Date'),
        ('select', 'Dropdown'),
        ('radio', 'Radio Buttons'),
        ('checkbox', 'Checkboxes'),
    )
    form = models.ForeignKey(CustomForm, on_delete=models.CASCADE, related_name='fields')
    label = models.CharField(max_length=300)
    field_type = models.CharField(max_length=20, choices=FIELD_TYPES, default='text')
    placeholder = models.CharField(max_length=300, blank=True)
    options = models.TextField(blank=True, help_text='Comma-separated options for select/radio/checkbox')
    required = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ('order',)

    def get_options_list(self):
        return [o.strip() for o in self.options.split(',') if o.strip()]


class FormSubmission(models.Model):
    form = models.ForeignKey(CustomForm, on_delete=models.CASCADE, related_name='submissions')
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-submitted_at',)

    def __str__(self):
        return f"Submission #{self.pk} for {self.form.title}"


class FieldResponse(models.Model):
    submission = models.ForeignKey(FormSubmission, on_delete=models.CASCADE, related_name='responses')
    field_label = models.CharField(max_length=300)
    value = models.TextField(blank=True)


# ============================================================
# BLOG
# ============================================================

class BlogPost(models.Model):
    CATEGORY_CHOICES = (
        ('news', 'News & Updates'),
        ('guide', 'Guides & Tutorials'),
        ('feature', 'Feature Spotlight'),
        ('case_study', 'Case Study'),
        ('tip', 'Tips & Tricks'),
    )
    title = models.CharField(max_length=400)
    slug = models.SlugField(max_length=400, unique=True)
    excerpt = models.TextField(max_length=500)
    content = models.TextField()
    cover_image = models.ImageField(upload_to='blog/', null=True, blank=True)
    author = models.CharField(max_length=200, default='Mero Attendance Team')
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='news')
    published = models.BooleanField(default=False)
    meta_description = models.CharField(max_length=300, blank=True, help_text="Shown in search results and social previews. Falls back to excerpt if blank.")
    meta_keywords = models.CharField(max_length=300, blank=True, help_text="Comma-separated keywords.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('-created_at',)

    def __str__(self):
        return self.title


class FAQ(models.Model):
    """Platform-level FAQ (about the product) shown on the public landing
    page and managed from the superadmin panel — not per-organization."""
    question = models.CharField(max_length=300)
    answer = models.TextField()
    category = models.CharField(max_length=100, blank=True, default='general')
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('order', 'id')

    def __str__(self):
        return self.question


class AgentProfile(models.Model):
    COMMISSION_TYPE_CHOICES = (
        ('percent', 'Percentage'),
        ('fixed', 'Fixed Amount'),
    )
    STATUS_CHOICES = (
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('suspended', 'Suspended'),
    )
    admin = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='agent_profile')
    full_name = models.CharField(max_length=200)
    phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    photo = models.ImageField(upload_to='agents/', null=True, blank=True)
    company_name = models.CharField(max_length=300, blank=True)
    pan_number = models.CharField(max_length=50, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    commission_type = models.CharField(max_length=10, choices=COMMISSION_TYPE_CHOICES, default='percent')
    commission_value = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    allowed_to_create_org = models.BooleanField(default=True)
    allowed_to_manage_billing = models.BooleanField(default=False)
    allowed_to_manage_features = models.BooleanField(default=False)
    allowed_to_view_reports = models.BooleanField(default=True)
    max_organizations_allowed = models.PositiveIntegerField(default=10)
    created_by = models.ForeignKey(
        CustomUser, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='created_agents'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    objects = models.Manager()

    def __str__(self):
        return f"{self.full_name} ({self.admin.username})"

    def org_count(self):
        return self.organizations.count()

    def can_add_org(self):
        return self.allowed_to_create_org and self.org_count() < self.max_organizations_allowed


class AgentLedger(models.Model):
    PAYMENT_STATUS_CHOICES = (
        ('paid', 'Paid'),
        ('unpaid', 'Unpaid'),
        ('partial', 'Partial'),
    )
    agent = models.ForeignKey(AgentProfile, on_delete=models.CASCADE, related_name='ledger_entries')
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='ledger_entries')
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    commission_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    commission_type = models.CharField(max_length=10, blank=True)
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='unpaid')
    remarks = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    objects = models.Manager()

    def __str__(self):
        return f"{self.agent.full_name} - {self.organization.name} - {self.amount}"


class AgentActivityLog(models.Model):
    agent = models.ForeignKey(AgentProfile, on_delete=models.CASCADE, related_name='activity_logs')
    action = models.CharField(max_length=200)
    organization = models.ForeignKey(
        Organization, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='agent_activity_logs'
    )
    description = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    objects = models.Manager()

    class Meta:
        ordering = ('-created_at',)

    def __str__(self):
        return f"{self.agent.full_name} - {self.action}"


@receiver(post_save, sender=CustomUser)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        if instance.user_type == "1":
            Superadmin.objects.create(admin=instance)
        # Schooladmin is NOT auto-created here: it requires an `org` FK that
        # isn't known at CustomUser-creation time. Every real signup path
        # (superadmin/views.py, agent/views.py, handle/serializers.py)
        # creates Schooladmin explicitly right after the user, with the org.
        # Auto-creating it here without an org raised IntegrityError and
        # broke org signup via the agent portal and the mobile API.
        if instance.user_type == "4":
            AgentProfile.objects.get_or_create(
                admin=instance,
                defaults={'full_name': f"{instance.first_name} {instance.last_name}".strip() or instance.username}
            )


@receiver(post_save, sender=CustomUser)
def _post_save_receiver(sender, instance, **kwargs):
    if instance.user_type == "1" and hasattr(instance, "superadmin"):
        instance.superadmin.save()
    if instance.user_type == "2" and hasattr(instance, "schooladmin"):
        instance.schooladmin.save()
    if instance.user_type == "3" and hasattr(instance, "staff"):
        instance.staff.save()
