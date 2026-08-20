from datetime import datetime, time
from decimal import Decimal

from django.conf import settings
from django.db import migrations, models
import django.core.validators
import django.db.models.deletion
from django.utils import timezone


FEATURE_LABELS = {
    "finance": "Finance — Income & Expense",
    "billing": "Billing & Invoices",
    "stock": "Stock / Inventory",
    "tasks": "Task Management",
    "results": "Results & Exams",
    "hrms": "HR Module",
    "payroll": "Payroll & Payslips",
    "complaints": "Complaints & Requests",
    "events": "Events",
    "branches": "Branch Management",
    "leave": "Leave Management",
    "study_gap": "Study Gap / Teaching Log",
    "bulk_export": "Bulk Data Export",
    "notifications": "Notifications / SMS",
    "courses": "Course Management",
    "student_mgmt": "Student Management",
    "member_mgmt": "Member / Staff Management",
    "qr_attendance": "Dynamic QR Attendance",
    "timesheet": "Timesheet Management",
    "id_cards": "ID Card Generation",
    "field_visits": "Field Visit / Location Sharing",
    "clients": "Client Follow-Up (CRM)",
    "face_attendance": "Face Attendance",
    "notices": "Notice Board / Announcements",
    "biometric": "Biometric / RFID Attendance",
    "qr": "QR Code Attendance",
    "gps": "GPS Location Attendance",
    "manual": "Manual Attendance",
    "nepali_cal": "Nepali Calendar (BS)",
    "wifi": "WiFi / Multi-Feature Attendance",
}

FREE_KEYS = {
    "payroll",
    "leave",
    "member_mgmt",
    "biometric",
    "qr",
    "gps",
    "manual",
    "wifi",
    "nepali_cal",
    "qr_attendance",
}


def seed_feature_prices_and_creation_dates(apps, schema_editor):
    Organization = apps.get_model("management", "Organization")
    FeaturePrice = apps.get_model("management", "FeaturePrice")
    DynamicFeature = apps.get_model("handle", "DynamicFeature")

    for organization in Organization.objects.all().iterator():
        if organization.created_at is None and organization.subscription_start:
            created = datetime.combine(organization.subscription_start, time.min)
            if timezone.is_naive(created):
                created = timezone.make_aware(created)
            Organization.objects.filter(pk=organization.pk).update(created_at=created)

    order = 10
    for key, label in FEATURE_LABELS.items():
        FeaturePrice.objects.get_or_create(
            feature_key=key,
            defaults={
                "label": label,
                "annual_price": Decimal("0") if key in FREE_KEYS else Decimal("3000"),
                "display_order": order,
            },
        )
        order += 10

    for dynamic in DynamicFeature.objects.all().iterator():
        FeaturePrice.objects.get_or_create(
            feature_key=dynamic.key,
            defaults={
                "label": dynamic.label,
                "annual_price": dynamic.price if dynamic.price is not None else Decimal("3000"),
                "is_active": dynamic.is_active,
                "display_order": order,
            },
        )
        order += 10


class Migration(migrations.Migration):

    dependencies = [
        ("handle", "0072_notification_recipient_constraint"),
        ("management", "0032_alter_organization_category"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="organization",
            name="created_at",
            field=models.DateTimeField(
                blank=True,
                editable=False,
                help_text="Immutable organization creation timestamp used as the subscription start date.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="organization",
            name="custom_amount_note",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Internal note explaining an agreed custom subscription amount.",
                max_length=255,
            ),
        ),
        migrations.AddField(
            model_name="organization",
            name="custom_subscription_amount",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Optional superadmin-defined annual amount. Overrides the calculated package and feature total.",
                max_digits=12,
                null=True,
                validators=[django.core.validators.MinValueValidator(Decimal("0"))],
            ),
        ),
        migrations.CreateModel(
            name="FeaturePrice",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("feature_key", models.SlugField(max_length=100, unique=True)),
                ("label", models.CharField(max_length=150)),
                (
                    "annual_price",
                    models.DecimalField(
                        decimal_places=2,
                        default=0,
                        max_digits=12,
                        validators=[django.core.validators.MinValueValidator(Decimal("0"))],
                    ),
                ),
                ("is_active", models.BooleanField(default=True)),
                (
                    "is_public",
                    models.BooleanField(
                        default=True,
                        help_text="Show this feature in the public quotation calculator.",
                    ),
                ),
                ("display_order", models.PositiveIntegerField(default=100)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="feature_prices_updated",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ("display_order", "label", "feature_key")},
        ),
        migrations.RunPython(seed_feature_prices_and_creation_dates, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="organization",
            name="created_at",
            field=models.DateTimeField(
                blank=True,
                default=timezone.now,
                editable=False,
                help_text="Immutable organization creation timestamp used as the subscription start date.",
                null=True,
            ),
        ),
    ]
