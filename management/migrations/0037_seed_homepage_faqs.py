from django.db import migrations


DEFAULT_FAQS = (
    (
        "getting-started",
        "Which organizations can use Mero Attendance?",
        "Mero Attendance works for schools, colleges, training institutes, offices, hospitals, banks, factories, NGOs and multi-branch organizations. Administrators can enable only the features that each organization needs.",
    ),
    (
        "attendance",
        "Which attendance methods are supported?",
        "Organizations can use biometric devices, QR attendance, GPS and geofencing, office WiFi, face attendance, mobile attendance and authorized manual attendance. Available methods depend on the features enabled for the organization.",
    ),
    (
        "calendar",
        "Does the system support the Nepali calendar?",
        "Yes. Organizations can work with Bikram Sambat (BS) or English (AD) dates. Attendance and monthly reports follow the calendar selected in the organization settings.",
    ),
    (
        "academics",
        "What can schools and colleges manage?",
        "Academic organizations can manage courses, classifications, sections, subjects, teacher assignments, class routines, subject attendance, homework, assignments, examinations, marks, student billing and student or teacher portals.",
    ),
    (
        "hr-payroll",
        "Can Mero Attendance manage payroll and leave?",
        "Yes. The HRMS includes shifts, leave policies, approvals, attendance corrections, salary setup, payroll processing, payslips, advances and staff history. Access is controlled through organization features and role permissions.",
    ),
    (
        "security",
        "Is data separated between organizations and branches?",
        "Yes. Mero Attendance is multi-tenant: organization and branch boundaries are enforced across dashboards, forms, reports and permissions. Staff, teachers, students and administrators see only the data their role allows.",
    ),
    (
        "devices",
        "Can an existing biometric device connect to the cloud?",
        "Compatible devices can send attendance directly through ADMS, while other supported devices can synchronize through the Mero Attendance puller. Device compatibility and network settings are confirmed during setup.",
    ),
    (
        "mobile",
        "Is there a mobile app for staff, teachers and students?",
        "Yes. Role-based mobile dashboards support attendance, routines, assignments, notifications, reports and other enabled workflows. Driver and transport tracking features can also be enabled where required.",
    ),
    (
        "pricing",
        "How is subscription pricing calculated?",
        "Pricing is quotation-based. It considers the member limit, selected features, organization requirements and subscription period. Request a demo or quotation to receive the correct package for your organization.",
    ),
)


def add_default_faqs(apps, schema_editor):
    FAQ = apps.get_model("management", "FAQ")
    for order, (category, question, answer) in enumerate(DEFAULT_FAQS, start=10):
        FAQ.objects.get_or_create(
            question=question,
            defaults={
                "answer": answer,
                "category": category,
                "order": order,
                "is_active": True,
            },
        )


def remove_default_faqs(apps, schema_editor):
    FAQ = apps.get_model("management", "FAQ")
    for category, question, _answer in DEFAULT_FAQS:
        FAQ.objects.filter(category=category, question=question).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("management", "0036_packagerequest_alter_contactus_options_and_more"),
    ]

    operations = [
        migrations.RunPython(add_default_faqs, remove_default_faqs),
    ]
