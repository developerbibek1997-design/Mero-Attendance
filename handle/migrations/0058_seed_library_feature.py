from decimal import Decimal
from django.db import migrations


LIBRARY_PERMISSIONS = [
    ('can_view_library', 'View Library', 'fa-eye'),
    ('can_manage_library', 'Manage Books & Catalog', 'fa-sliders'),
    ('can_issue_books', 'Issue Books', 'fa-right-from-bracket'),
    ('can_return_books', 'Return Books', 'fa-right-to-bracket'),
]


def seed_library_feature(apps, schema_editor):
    DynamicFeature = apps.get_model('handle', 'DynamicFeature')
    DynamicPermission = apps.get_model('handle', 'DynamicPermission')

    feature, _ = DynamicFeature.objects.get_or_create(
        key='library',
        defaults={
            'label': 'Library Management',
            'icon': 'fa-book',
            'category': 'library',
            'description': 'Books, borrowing, and library reports for schools, colleges and institutes.',
            'requires': [],
            'price': Decimal('5000.00'),
            'is_active': True,
        },
    )
    # In case the feature already existed (re-run), keep the price/label current.
    feature.label = 'Library Management'
    feature.icon = 'fa-book'
    feature.category = 'library'
    feature.description = 'Books, borrowing, and library reports for schools, colleges and institutes.'
    feature.price = Decimal('5000.00')
    feature.is_active = True
    feature.save()

    for flag, label, icon in LIBRARY_PERMISSIONS:
        DynamicPermission.objects.get_or_create(
            flag=flag, defaults={'label': label, 'icon': icon, 'feature': feature}
        )


def unseed_library_feature(apps, schema_editor):
    DynamicFeature = apps.get_model('handle', 'DynamicFeature')
    DynamicFeature.objects.filter(key='library').delete()  # cascades permissions + grants


class Migration(migrations.Migration):

    dependencies = [
        ('handle', '0057_library_management'),
    ]

    operations = [
        migrations.RunPython(seed_library_feature, unseed_library_feature),
    ]
