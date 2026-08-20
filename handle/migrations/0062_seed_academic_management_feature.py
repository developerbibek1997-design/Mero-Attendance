from django.db import migrations


ACADEMIC_PERMISSIONS = [
    ('can_manage_assignments', 'Manage Assignments', 'fa-file-pen'),
    ('can_grade_assignments', 'Grade Assignments', 'fa-check-double'),
    ('can_manage_homework', 'Manage Homework', 'fa-book-open-reader'),
    ('can_manage_course_materials', 'Manage Course Materials', 'fa-folder-open'),
    ('can_manage_teaching_logs', 'Submit Teaching Logs', 'fa-clipboard-list'),
    ('can_approve_teaching_logs', 'Approve Teaching Logs', 'fa-stamp'),
    ('can_manage_routine', 'Manage Class Routine', 'fa-calendar-days'),
]


def seed_academic_feature(apps, schema_editor):
    DynamicFeature = apps.get_model('handle', 'DynamicFeature')
    DynamicPermission = apps.get_model('handle', 'DynamicPermission')

    feature, _ = DynamicFeature.objects.get_or_create(
        key='academic_management',
        defaults={
            'label': 'Academic Management',
            'icon': 'fa-graduation-cap',
            'category': 'academic',
            'description': 'Assignments, homework, course materials, daily teaching logs and class routine for schools, colleges and institutes.',
            'requires': [],
            'price': None,
            'is_active': True,
        },
    )
    # In case the feature already existed (re-run), keep the label/description current.
    feature.label = 'Academic Management'
    feature.icon = 'fa-graduation-cap'
    feature.category = 'academic'
    feature.description = 'Assignments, homework, course materials, daily teaching logs and class routine for schools, colleges and institutes.'
    feature.is_active = True
    feature.save()

    for flag, label, icon in ACADEMIC_PERMISSIONS:
        DynamicPermission.objects.get_or_create(
            flag=flag, defaults={'label': label, 'icon': icon, 'feature': feature}
        )


def unseed_academic_feature(apps, schema_editor):
    DynamicFeature = apps.get_model('handle', 'DynamicFeature')
    DynamicFeature.objects.filter(key='academic_management').delete()  # cascades permissions + grants


class Migration(migrations.Migration):

    dependencies = [
        ('handle', '0061_academic_management'),
    ]

    operations = [
        migrations.RunPython(seed_academic_feature, unseed_academic_feature),
    ]
