"""Tenant-safe in-app notification services.

Academic events historically targeted a ``member``.  The shared notification
centre also needs to serve school administrators, so new events may target a
``CustomUser`` directly.  All reads go through ``notifications_for_user`` and
therefore remain scoped to both the authenticated recipient and organisation.
"""

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone


def _org_for_user(user):
    if not getattr(user, 'is_authenticated', False):
        return None
    if str(getattr(user, 'user_type', '')) == '2':
        return getattr(getattr(user, 'schooladmin', None), 'org', None)
    if str(getattr(user, 'user_type', '')) == '3':
        return getattr(getattr(user, 'staff', None), 'org', None)
    return None


def _member_for_user(user):
    if str(getattr(user, 'user_type', '')) != '3':
        return None
    return getattr(getattr(user, 'staff', None), 'member', None)


def notifications_for_user(user, org=None):
    """Return only notifications owned by ``user`` in their current tenant."""
    from handle.models import InAppNotification

    org = org or _org_for_user(user)
    if org is None:
        return InAppNotification.objects.none()

    ownership = Q(recipient_user=user)
    member_obj = _member_for_user(user)
    if member_obj is not None:
        ownership |= Q(recipient=member_obj)
    return InAppNotification.objects.filter(
        ownership, org=org,
    ).select_related('recipient', 'recipient_user', 'actor').distinct()


def _create_notification(**fields):
    """Create idempotently when a dedupe key is supplied.

    The unique database key closes the race between two concurrent requests;
    the IntegrityError fallback returns the row created by the winner.
    """
    from handle.models import InAppNotification

    dedupe_key = fields.get('dedupe_key') or None
    fields['dedupe_key'] = dedupe_key
    if not dedupe_key:
        return InAppNotification.objects.create(**fields)
    try:
        with transaction.atomic():
            obj, _ = InAppNotification.objects.get_or_create(
                dedupe_key=dedupe_key,
                defaults=fields,
            )
            return obj
    except IntegrityError:
        return InAppNotification.objects.get(dedupe_key=dedupe_key)


def notify(
    member, event_type, title, body='', link_url='', *,
    priority='normal', action_label='', actor=None, dedupe_key=None,
):
    """Create one notification for a member (student/staff/teacher)."""
    if member is None or member.org_id is None:
        return None
    return _create_notification(
        org=member.org,
        recipient=member,
        event_type=event_type,
        priority=priority,
        title=title,
        body=body,
        link_url=link_url,
        action_label=action_label,
        actor=actor,
        dedupe_key=dedupe_key,
    )


def notify_user(
    user, org, event_type, title, body='', link_url='', *,
    priority='normal', action_label='', actor=None, dedupe_key=None,
):
    """Create one direct notification, primarily for school administrators."""
    if user is None or org is None or _org_for_user(user) != org:
        return None
    return _create_notification(
        org=org,
        recipient_user=user,
        event_type=event_type,
        priority=priority,
        title=title,
        body=body,
        link_url=link_url,
        action_label=action_label,
        actor=actor,
        dedupe_key=dedupe_key,
    )


def notify_many(
    members, event_type, title, body='', link_url='', *,
    priority='normal', action_label='', actor=None,
):
    """Bulk-create one academic notification per valid member."""
    from handle.models import InAppNotification

    rows = [
        InAppNotification(
            org=m.org,
            recipient=m,
            event_type=event_type,
            priority=priority,
            title=title,
            body=body,
            link_url=link_url,
            action_label=action_label,
            actor=actor,
        )
        for m in members if m.org_id
    ]
    return InAppNotification.objects.bulk_create(rows)


def unread_notification_count(recipient):
    """Backward-compatible count for either a member or authenticated user."""
    if recipient is None:
        return 0
    if hasattr(recipient, 'user_type'):
        return notifications_for_user(recipient).filter(is_read=False).count()
    from handle.models import InAppNotification
    return InAppNotification.objects.filter(
        recipient=recipient, org=recipient.org, is_read=False,
    ).count()


def mark_read(notification):
    if notification.is_read and notification.read_at:
        return notification
    notification.is_read = True
    notification.read_at = timezone.now()
    notification.save(update_fields=('is_read', 'read_at'))
    return notification


def _task_priority(task):
    return {
        'urgent': 'urgent',
        'high': 'high',
        'medium': 'normal',
        'low': 'low',
    }.get(task.priority, 'normal')


def notify_task_assigned(task, members, actor=None):
    """Notify each assignee once for a newly-created task definition."""
    link = reverse('staff:my_tasks')
    actor_name = (
        actor.get_full_name() or actor.username
        if actor is not None else 'Your administrator'
    )
    for member_obj in members:
        notify(
            member_obj,
            'task_assigned',
            f'New task: {task.title}',
            f'Assigned by {actor_name}. Due {task.due_date}.',
            link,
            priority=_task_priority(task),
            action_label='Open task',
            actor=actor,
            dedupe_key=f'task-assigned:{task.pk}:member:{member_obj.pk}',
        )


def _task_manager_users(task, exclude_user=None):
    """Creator plus organisation admins, de-duplicated and tenant checked."""
    users = {}
    if task.created_by_id and _org_for_user(task.created_by) == task.org:
        users[task.created_by_id] = task.created_by
    for profile in task.org.schooladmin_set.select_related('admin').all():
        users[profile.admin_id] = profile.admin
    if exclude_user is not None:
        users.pop(exclude_user.pk, None)
    return list(users.values())


def notify_task_managers(instance, event_type, title, body, *, actor=None, log_id=None):
    """Notify the task creator and school admins about assignee actions."""
    task = instance.task
    suffix = log_id or instance.updated_at.isoformat()
    for user in _task_manager_users(task, exclude_user=actor):
        link = (
            reverse('schooladmin:task_detail', args=(task.pk,))
            if str(user.user_type) == '2'
            else reverse('staff:task_detail', args=(task.pk,))
        )
        notify_user(
            user,
            task.org,
            event_type,
            title,
            body,
            link,
            priority=_task_priority(task),
            action_label='Review task',
            actor=actor,
            dedupe_key=f'{event_type}:{instance.pk}:user:{user.pk}:{suffix}',
        )


def notify_task_assignee(
    instance, event_type, title, body, *, actor=None, log_id=None,
    priority=None,
):
    """Notify the current assignee about a manager action."""
    suffix = log_id or instance.updated_at.isoformat()
    return notify(
        instance.assigned_member,
        event_type,
        title,
        body,
        reverse('staff:my_tasks'),
        priority=priority or _task_priority(instance.task),
        action_label='Open task',
        actor=actor,
        dedupe_key=(
            f'{event_type}:{instance.pk}:member:'
            f'{instance.assigned_member_id}:{suffix}'
        ),
    )


def ensure_task_reminders(user, org=None, on_date=None):
    """Materialise due/overdue reminders once per task instance.

    Called from the shared bell context. The unique dedupe key makes repeated
    page loads safe and avoids requiring a scheduler for dashboard reminders.
    """
    from handle.models import InAppNotification, TaskInstance

    org = org or _org_for_user(user)
    member_obj = _member_for_user(user)
    if org is None or member_obj is None:
        return
    on_date = on_date or timezone.localdate()
    instances = TaskInstance.objects.filter(
        assigned_member=member_obj,
        task__org=org,
        task__is_active=True,
        due_date__lte=on_date,
        status__in=('pending', 'in_progress', 'overdue', 'missed_absence'),
    ).select_related('task')
    candidates = []
    for instance in instances:
        overdue = instance.due_date < on_date or instance.status in (
            'overdue', 'missed_absence',
        )
        event_type = 'task_overdue' if overdue else 'task_due_today'
        title = (
            f'Overdue task: {instance.task.title}'
            if overdue else f'Due today: {instance.task.title}'
        )
        body = (
            f'This task was due {instance.due_date}. Update its status now.'
            if overdue else 'Please complete or update this task today.'
        )
        candidates.append(InAppNotification(
            org=org,
            recipient=member_obj,
            event_type=event_type,
            priority='urgent' if overdue else _task_priority(instance.task),
            title=title,
            body=body,
            link_url=reverse('staff:my_tasks'),
            action_label='Update task',
            dedupe_key=f'{event_type}:{instance.pk}:{instance.due_date}',
        ))
    if candidates:
        existing_keys = set(InAppNotification.objects.filter(
            dedupe_key__in=[row.dedupe_key for row in candidates],
        ).values_list('dedupe_key', flat=True))
        rows = [
            row for row in candidates if row.dedupe_key not in existing_keys
        ]
    else:
        rows = []
    if rows:
        InAppNotification.objects.bulk_create(rows, ignore_conflicts=True)
