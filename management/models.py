from django.db import models
from django.contrib.auth.models import AbstractUser
from django.dispatch import receiver
from django.db.models.signals import post_save
import uuid as _uuid

import datetime

# Create your models here.

class CustomUser(AbstractUser):
    user_type_data = (("1", "superadmin"), ("2", 'schooladmin'), ("3", 'staff'))
    user_type = models.CharField(default = "1", choices = user_type_data, max_length = 10)
    email = models.EmailField(unique = True)
    

class Organization(models.Model):
    id = models.AutoField(primary_key= True)
    CATEGORY_CHOICES = (
        ('school', 'School'),
        ('college', 'College'),
        ('bachelor', 'Bachelor'),
        ('institute', 'Institute/Consultancy'),
        ('office', 'Office'),
        ('others', 'Others'),
       
    )
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES, default='others')
    rfid_based = models.BooleanField(default=False)
    image = models.ImageField(upload_to="image", null= True, blank=True)
    address = models.CharField(max_length=200, null= True, blank= True)
    name = models.CharField(max_length=300)
    member_limit = models.IntegerField(default=25)
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
    # ─────────────────────────────────────────────────────────────────────────

    # ── Org Type Presets ─────────────────────────────────────────────────────
    ORG_TYPE_PRESETS = {
        'school':    ['feature_leave', 'feature_results', 'feature_billing', 'feature_student_mgmt', 'feature_courses', 'feature_complaints', 'feature_events'],
        'college':   ['feature_leave', 'feature_results', 'feature_billing', 'feature_student_mgmt', 'feature_courses', 'feature_complaints', 'feature_finance'],
        'bachelor':  ['feature_leave', 'feature_results', 'feature_billing', 'feature_student_mgmt', 'feature_courses', 'feature_finance'],
        'institute': ['feature_leave', 'feature_payroll', 'feature_hrms', 'feature_finance', 'feature_student_mgmt', 'feature_courses'],
        'office':    ['feature_leave', 'feature_payroll', 'feature_hrms', 'feature_tasks', 'feature_finance', 'feature_bulk_export'],
        'others':    [],
    }

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
    
    
class Occasion(models.Model):
    name = models.CharField(max_length=200)
    org = models.ForeignKey(Organization, related_name="org_occasion", on_delete=models.CASCADE)
    date = models.DateField()
    end_date = models.DateField(null=True, blank=True)  # Optional end date for gap holidays

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
     
    def __str__(self) -> str:
        return self.fullname
    
class Pricing(models.Model):
    name = models.CharField(max_length=200)
    price = models.IntegerField()
    limit = models.IntegerField()
    device = models.CharField(max_length=200)
    image = models.ImageField(upload_to='devices/', null=True, blank=True)

    def __str__(self) -> str:
        return self.name

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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('-created_at',)

    def __str__(self):
        return self.title


@receiver(post_save, sender=CustomUser)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        if instance.user_type == "1":
            Superadmin.objects.create(admin = instance)
        if instance.user_type == "2":
            Schooladmin.objects.create(admin = instance)
        # if instance.user_type == "3":
        #     Staff.objects.create(admin = instance)
     

@receiver(post_save, sender=CustomUser)
def _post_save_receiver(sender, instance, **kwargs):
    if instance.user_type == "1" and hasattr(instance, "superadmin"):
        instance.superadmin.save()
    if instance.user_type == "2":
        instance.schooladmin.save()
    if instance.user_type == "3" and hasattr(instance, "staff"):
        instance.staff.save()

