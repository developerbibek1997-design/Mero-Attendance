from decimal import Decimal
from django.db import migrations


ACCOUNTING_PERMISSIONS = [
    ('can_view_accounting', 'View Accounting Dashboard', 'fa-eye'),
    ('can_create_journals', 'Create Journal Entries', 'fa-pen-to-square'),
    ('can_approve_journals', 'Approve Journal Entries', 'fa-check-double'),
    ('can_view_ledger', 'View General Ledger', 'fa-book-open'),
    ('can_view_accounting_reports', 'View Financial Reports', 'fa-chart-line'),
]


def seed_accounting_feature(apps, schema_editor):
    DynamicFeature = apps.get_model('handle', 'DynamicFeature')
    DynamicPermission = apps.get_model('handle', 'DynamicPermission')

    feature, _ = DynamicFeature.objects.get_or_create(
        key='accounting',
        defaults={
            'label': 'Sales & Accounting ERP — Accounting Core',
            'icon': 'fa-calculator',
            'category': 'accounting',
            'description': 'Double-entry accounting: chart of accounts, journal entries, general ledger, and financial reports.',
            'requires': [],
            'price': Decimal('5000.00'),
            'is_active': True,
        },
    )
    # In case the feature already existed (re-run), keep the price/label current.
    feature.label = 'Sales & Accounting ERP — Accounting Core'
    feature.icon = 'fa-calculator'
    feature.category = 'accounting'
    feature.description = 'Double-entry accounting: chart of accounts, journal entries, general ledger, and financial reports.'
    feature.price = Decimal('5000.00')
    feature.is_active = True
    feature.save()

    for flag, label, icon in ACCOUNTING_PERMISSIONS:
        DynamicPermission.objects.get_or_create(
            flag=flag, defaults={'label': label, 'icon': icon, 'feature': feature}
        )


def unseed_accounting_feature(apps, schema_editor):
    DynamicFeature = apps.get_model('handle', 'DynamicFeature')
    DynamicFeature.objects.filter(key='accounting').delete()  # cascades permissions + grants


class Migration(migrations.Migration):

    dependencies = [
        ('handle', '0059_accounting_core'),
    ]

    operations = [
        migrations.RunPython(seed_accounting_feature, unseed_accounting_feature),
    ]
