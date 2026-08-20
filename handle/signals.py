"""Automatic member lifecycle auditing.

The signal deliberately records human-readable snapshots rather than foreign
keys alone, so history remains understandable after a related record is renamed.
"""

import datetime
from decimal import Decimal

from django.db.models.signals import m2m_changed, post_save, pre_save
from django.dispatch import receiver

from .audit import get_audit_user
from .models import MemberHistory, ResignationRecord, StudentCourseEnrollment, member


TRACKED_FIELDS = (
    'name', 'member_type', 'status', 'branch', 'classification', 'section',
    'device_id', 'card', 'roll_number', 'designation', 'email', 'phone',
    'address', 'date_of_birth', 'admission_date', 'salary_type', 'salary_amount',
    'staff_type', 'probation_start_date', 'probation_end_date',
    'make_staff', 'live_tracking_enabled', 'billing_type', 'monthly_fee',
    'discount_type', 'discount_amount', 'scholarship_amount',
    'final_monthly_fee', 'billing_start_date', 'shift_start_time',
    'shift_end_time', 'black_list',
)

FIELD_LABELS = {
    'status': 'Employment/member status',
    'classification': 'Classification',
    'section': 'Section',
    'branch': 'Branch',
    'salary_amount': 'Salary',
    'roll_number': 'Roll number',
    'admission_date': 'Join/admission date',
    'make_staff': 'Portal access',
}


def _display(value):
    if value is None or value == '':
        return '—'
    if isinstance(value, (datetime.date, datetime.time, datetime.datetime, Decimal)):
        return str(value)
    return str(value)


@receiver(pre_save, sender=member)
def remember_member_changes(sender, instance, **kwargs):
    if not instance.pk:
        instance._history_changes = []
        return
    previous = sender.objects.filter(pk=instance.pk).select_related(
        'branch', 'classification', 'section',
    ).first()
    if not previous:
        instance._history_changes = []
        return
    changes = []
    update_fields = kwargs.get('update_fields')
    for field_name in TRACKED_FIELDS:
        if update_fields is not None and field_name not in update_fields:
            continue
        field = sender._meta.get_field(field_name)
        old_raw = getattr(previous, field.attname)
        new_raw = getattr(instance, field.attname)
        if old_raw == new_raw:
            continue
        if field.is_relation:
            old_obj = getattr(previous, field_name, None)
            new_obj = getattr(instance, field_name, None)
            old_value, new_value = _display(old_obj), _display(new_obj)
        else:
            old_value, new_value = _display(old_raw), _display(new_raw)
        changes.append((field_name, old_value, new_value))
    instance._history_changes = changes


@receiver(post_save, sender=member)
def write_member_history(sender, instance, created, **kwargs):
    if not instance.org_id:
        return
    actor = get_audit_user()
    if created:
        MemberHistory.objects.create(
            member=instance, org=instance.org, action='member_created',
            description='Member profile created', changed_by=actor,
        )
        return
    rows = []
    for field_name, old_value, new_value in getattr(instance, '_history_changes', []):
        label = FIELD_LABELS.get(field_name, field_name.replace('_', ' ').title())
        rows.append(MemberHistory(
            member=instance, org=instance.org, action='field_changed',
            field_name=field_name, old_value=old_value, new_value=new_value,
            description=f'{label} changed from {old_value} to {new_value}',
            changed_by=actor,
        ))
    if rows:
        MemberHistory.objects.bulk_create(rows)


@receiver(m2m_changed, sender=member.courses.through)
@receiver(m2m_changed, sender=member.shifts.through)
def write_member_relation_history(sender, instance, action, reverse, model, pk_set, **kwargs):
    if reverse or not instance.org_id or action not in ('post_add', 'post_remove', 'post_clear'):
        return
    relation = 'Courses' if sender is member.courses.through else 'Legacy daily shifts'
    names = list(model.objects.filter(pk__in=pk_set or []).values_list('name', flat=True))
    verb = {'post_add': 'assigned', 'post_remove': 'removed', 'post_clear': 'cleared'}[action]
    MemberHistory.objects.create(
        member=instance, org=instance.org, action='relation_changed',
        field_name=relation.lower().replace(' ', '_'),
        description=f"{relation} {verb}: {', '.join(names) if names else 'all'}",
        metadata={'action': action, 'ids': sorted(pk_set or [])},
        changed_by=get_audit_user(),
    )


@receiver(post_save, sender=ResignationRecord)
def write_resignation_history(sender, instance, created, **kwargs):
    MemberHistory.objects.create(
        member=instance.member, org=instance.org,
        action='resignation_created' if created else 'resignation_updated',
        field_name='resignation', changed_by=get_audit_user(),
        description=(
            f"Resignation {'recorded' if created else 'updated'}: "
            f"{instance.get_status_display()} effective {instance.resignation_date}"
        ),
        metadata={
            'resignation_id': instance.pk, 'status': instance.status,
            'last_working_day': str(instance.last_working_day or ''),
        },
    )


@receiver(post_save, sender=StudentCourseEnrollment)
def write_enrollment_history(sender, instance, created, **kwargs):
    MemberHistory.objects.create(
        member=instance.student, org=instance.org,
        action='academic_enrollment_created' if created else 'academic_enrollment_updated',
        field_name='academic_enrollment', changed_by=get_audit_user(),
        description=(
            f"Academic enrollment {'created' if created else 'updated'}: "
            f"{instance.course.name} / {instance.classification.name} / "
            f"{instance.section.name if instance.section_id else 'All sections'} "
            f"({instance.get_status_display()})"
        ),
        metadata={'enrollment_id': instance.pk, 'status': instance.status},
    )
