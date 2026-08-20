"""
Academic Management service layer — routine-conflict detection and the
small derived-value helpers shared by the dashboard and the reports.

Usage:
    from handle.academics import check_routine_conflict, assignment_is_late, course_material_progress
"""

import datetime


def _time_ranges_overlap(start_a, end_a, start_b, end_b):
    return start_a < end_b and start_b < end_a


def check_routine_conflict(org, *, teacher, section, room, day_of_week, start_time, end_time,
                            classification=None, exclude_pk=None):
    """Returns a list of human-readable conflict messages (empty = no conflict).

    Checks three independent things for the same org + day_of_week with an
    overlapping time range:
      - the same teacher already has another period
      - the same section (or classification, if no section) already has another period
      - the same room is already booked
    """
    from handle.models import RoutinePeriod

    conflicts = []
    qs = RoutinePeriod.objects.filter(org=org, day_of_week=day_of_week, is_active=True)
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)

    for period in qs.select_related('teacher', 'section', 'classification'):
        if not _time_ranges_overlap(start_time, end_time, period.start_time, period.end_time):
            continue

        if period.teacher_id == getattr(teacher, 'id', teacher):
            conflicts.append(
                f"{period.teacher} is already scheduled for {period.classification} "
                f"({period.start_time.strftime('%H:%M')}-{period.end_time.strftime('%H:%M')}) at this time."
            )

        same_section = section and period.section_id == getattr(section, 'id', section)
        same_classification_no_section = (
            not section and classification and period.classification_id == getattr(classification, 'id', classification)
        )
        if same_section or same_classification_no_section:
            conflicts.append(
                f"{period.section or period.classification} already has a class "
                f"({period.subject.name}) at this time."
            )

        if room and period.room and period.room.strip().lower() == room.strip().lower():
            conflicts.append(
                f"Room '{room}' is already booked for {period.classification} at this time."
            )

    return conflicts


def assignment_is_late(assignment, submitted_at):
    """Whether a submission timestamp counts as late for this assignment."""
    submitted_date = submitted_at.date() if hasattr(submitted_at, 'date') else submitted_at
    return submitted_date > assignment.due_date


def course_material_progress(subject, student):
    """Fraction (0.0-1.0) of this subject's active materials the student has
    at least one 'view' access-log row for. No separate progress model —
    derived directly from CourseMaterialAccess."""
    from handle.models import CourseMaterial

    materials = CourseMaterial.objects.filter(subject=subject, is_active=True)
    total = materials.count()
    if total == 0:
        return 0.0
    viewed = materials.filter(access_logs__student=student, access_logs__access_type='view').distinct().count()
    return round(viewed / total, 2)


# ── Subject/period-based attendance (shared by the schooladmin and staff
# "Submit Teaching Log & Attendance" views — teachers are user_type '3' and
# never reach schooladmin/ URLs, so both portals need this same logic) ─────

def roster_for_class(org, classification, section):
    from handle.models import member as MemberModel

    qs = MemberModel.objects.filter(
        org=org,
        classification=classification,
        status='active',
        member_type__in=('student', 'trainee'),
    )
    if section:
        qs = qs.filter(section=section)
    return qs.order_by('name')


def roster_for_subject(
    org, subject, classification=None, section=None, attendance_date=None,
    academic_year=None,
):
    """Return the server-validated roster for one exact subject scope.

    Dated StudentCourseEnrollment rows are authoritative once they exist for
    the scope. Existing member placement fields remain a compatibility
    fallback for organisations that have not created enrollment history yet.
    """
    from django.utils import timezone
    from django.db.models import Q
    from handle.models import StudentCourseEnrollment

    classification = classification or subject.classification
    section = section if section is not None else subject.section
    attendance_date = attendance_date or timezone.localdate()

    if subject.course_id:
        enrollments = StudentCourseEnrollment.objects.filter(
            org=org,
            course=subject.course,
            classification=classification,
            student__status='active',
            start_date__lte=attendance_date,
        ).exclude(status='cancelled').filter(
            Q(end_date__isnull=True) | Q(end_date__gte=attendance_date)
        )
        if academic_year:
            enrollments = enrollments.filter(academic_year=academic_year)
        if section:
            enrollments = enrollments.filter(section=section)
        if enrollments.exists():
            from handle.models import member as MemberModel
            return MemberModel.objects.filter(
                org=org,
                pk__in=enrollments.values('student_id'),
                status='active',
            ).distinct().order_by('name')

    qs = roster_for_class(org, classification, section)
    if subject.course_id:
        qs = qs.filter(courses=subject.course)
    return qs.distinct().order_by('name')


def active_subject_assignments_for_teacher(org, teacher, on_date=None):
    """Exact active teaching scopes for a teacher in one organization."""
    from django.db.models import Q
    from django.utils import timezone
    from handle.models import SubjectTeacherAssignment

    on_date = on_date or timezone.localdate()
    return SubjectTeacherAssignment.objects.filter(
        org=org,
        teacher=teacher,
        subject__status='active',
        status='active',
        start_date__lte=on_date,
    ).filter(
        Q(end_date__isnull=True) | Q(end_date__gte=on_date)
    ).select_related(
        'academic_year', 'branch', 'course', 'classification', 'section',
        'subject',
    )


def subject_assignment_for_teacher(
    subject, teacher, on_date=None, academic_year=None, section=None,
):
    """Return the active, dated assignment granting attendance authority.

    Legacy Subject.teacher is accepted only when no assignment rows exist for
    the subject. Once assignments are managed, deactivating one must actually
    revoke future access.
    """
    from django.db.models import Q
    from django.utils import timezone

    teacher_id = getattr(teacher, 'pk', teacher)
    on_date = on_date or timezone.localdate()
    assignments = subject.teacher_assignments.filter(teacher_id=teacher_id)
    active = assignments.filter(
        status='active',
        start_date__lte=on_date,
    ).filter(Q(end_date__isnull=True) | Q(end_date__gte=on_date))
    if academic_year:
        active = active.filter(Q(academic_year=academic_year) | Q(academic_year__isnull=True))
    if section is not None:
        section_id = getattr(section, 'pk', section)
        active = active.filter(Q(section_id=section_id) | Q(section__isnull=True))
    assignment = active.select_related(
        'academic_year', 'course', 'classification', 'section'
    ).order_by(
        '-section_id', '-is_primary', '-start_date', '-pk',
    ).first()
    if assignment:
        return assignment
    if not subject.teacher_assignments.exists() and subject.teacher_id == teacher_id:
        return None
    return False


def teacher_is_assigned_to_subject(
    subject, teacher, on_date=None, academic_year=None, section=None,
):
    assignment = subject_assignment_for_teacher(
        subject, teacher, on_date=on_date, academic_year=academic_year,
        section=section,
    )
    return assignment is not False


def todays_routine_period_options(org, user, is_admin):
    """RoutinePeriod rows for today, each paired with its roster — teachers
    only see their own periods, admins see everyone's (for oversight/backfill)."""
    from django.utils import timezone
    from handle.models import RoutinePeriod

    today = timezone.localdate()
    # Python uses Monday=0; RoutinePeriod intentionally uses Sunday=0.
    routine_weekday = (today.weekday() + 1) % 7
    periods_qs = RoutinePeriod.objects.filter(
        org=org, day_of_week=routine_weekday, is_active=True,
    ).select_related(
        'academic_year', 'subject__course', 'classification', 'section', 'teacher'
    ).order_by('period_number')
    if not is_admin:
        periods_qs = periods_qs.filter(teacher=user)
    options = []
    for period in periods_qs:
        if not is_admin and not teacher_is_assigned_to_subject(
            period.subject, user, on_date=today, academic_year=period.academic_year,
            section=period.section,
        ):
            continue
        options.append({
            'period': period,
            'roster': roster_for_subject(
                org, period.subject, period.classification, period.section,
                attendance_date=today, academic_year=period.academic_year,
            ),
        })
    return options


def teacher_routine_reminders(
    org, user, subject_ids, *, assignment_ids=None, on_date=None, now=None,
    academic_year=None,
):
    """Build teacher-safe weekly routine data and today's reminder states."""
    from django.db.models import Q
    from django.utils import timezone
    from handle.models import RoutinePeriod, TeachingLog

    on_date = on_date or timezone.localdate()
    now = now or timezone.localtime()
    current_time = now.time().replace(tzinfo=None)
    weekday = (on_date.weekday() + 1) % 7

    periods_qs = RoutinePeriod.objects.filter(
        org=org,
        teacher=user,
        subject_id__in=subject_ids,
        is_active=True,
    )
    if assignment_ids is not None:
        periods_qs = periods_qs.filter(
            Q(teacher_assignment_id__in=assignment_ids)
            | Q(teacher_assignment__isnull=True, subject__teacher=user)
        )
    if academic_year:
        periods_qs = periods_qs.filter(
            Q(academic_year=academic_year) | Q(academic_year__isnull=True)
        )
    periods = list(periods_qs.select_related(
        'academic_year',
        'teacher_assignment',
        'subject__course',
        'classification',
        'section',
    ).order_by('day_of_week', 'period_number', 'start_time'))

    today_periods = [period for period in periods if period.day_of_week == weekday]
    logs = TeachingLog.objects.filter(
        org=org,
        teacher=user,
        date=on_date,
        routine_period__in=today_periods,
    ).order_by('routine_period_id', '-pk')
    log_by_period = {}
    for log in logs:
        log_by_period.setdefault(log.routine_period_id, log)

    priority = {
        'live': 0,
        'rejected': 1,
        'overdue': 2,
        'draft': 3,
        'upcoming': 4,
        'completed': 5,
    }
    for period in today_periods:
        log = log_by_period.get(period.pk)
        period.attendance_log = log
        period.attendance_action_required = True
        if log and log.status in ('submitted', 'approved'):
            period.reminder_state = 'completed'
            period.reminder_label = 'Attendance submitted'
            period.reminder_badge_class = 'bg-success'
            period.attendance_action_required = False
        elif log and log.status == 'rejected':
            period.reminder_state = 'rejected'
            period.reminder_label = 'Correct rejected attendance'
            period.reminder_badge_class = 'bg-danger'
        elif log and log.status == 'draft':
            period.reminder_state = 'draft'
            period.reminder_label = 'Draft attendance — submit it'
            period.reminder_badge_class = 'bg-info'
        elif period.start_time <= current_time <= period.end_time:
            period.reminder_state = 'live'
            period.reminder_label = 'Class is running — take attendance'
            period.reminder_badge_class = 'bg-danger'
        elif current_time < period.start_time:
            minutes = max(
                0,
                int((
                    datetime.datetime.combine(on_date, period.start_time)
                    - datetime.datetime.combine(on_date, current_time)
                ).total_seconds() // 60),
            )
            period.reminder_state = 'upcoming'
            period.reminder_label = (
                f'Starts in {minutes} min'
                if minutes <= 120
                else f'Today at {period.start_time.strftime("%H:%M")}'
            )
            period.reminder_badge_class = 'bg-primary'
        else:
            period.reminder_state = 'overdue'
            period.reminder_label = 'Attendance not submitted'
            period.reminder_badge_class = 'bg-warning text-dark'

    attention = None
    if today_periods:
        attention = sorted(
            today_periods,
            key=lambda period: (
                priority.get(period.reminder_state, 99),
                period.start_time,
                period.period_number,
            ),
        )[0]

    future_candidates = []
    for period in periods:
        days_until = (period.day_of_week - weekday) % 7
        if days_until == 0 and period.end_time <= current_time:
            days_until = 7
        if days_until == 0 and period in today_periods:
            if period.reminder_state == 'completed':
                continue
        period.next_occurrence_date = on_date + datetime.timedelta(days=days_until)
        period.next_occurrence_day = dict(RoutinePeriod.DAY_CHOICES)[period.day_of_week]
        future_candidates.append((days_until, period.start_time, period.period_number, period))
    next_period = min(future_candidates, default=(None, None, None, None))[3]

    return {
        'periods': periods,
        'today_periods': today_periods,
        'attention': attention,
        'next_period': next_period,
    }


def student_routine_reminders(periods, *, on_date=None, now=None):
    """Decorate a server-scoped student timetable with live/upcoming states."""
    from django.utils import timezone
    from handle.models import RoutinePeriod

    on_date = on_date or timezone.localdate()
    now = now or timezone.localtime()
    current_time = now.time().replace(tzinfo=None)
    weekday = (on_date.weekday() + 1) % 7
    periods = sorted(
        list(periods),
        key=lambda period: (
            period.day_of_week, period.period_number, period.start_time,
        ),
    )
    today_periods = [
        period for period in periods if period.day_of_week == weekday
    ]
    for period in today_periods:
        if period.start_time <= current_time <= period.end_time:
            period.reminder_state = 'live'
            period.reminder_label = 'Class is running now'
            period.reminder_badge_class = 'bg-danger'
        elif current_time < period.start_time:
            minutes = max(
                0,
                int((
                    datetime.datetime.combine(on_date, period.start_time)
                    - datetime.datetime.combine(on_date, current_time)
                ).total_seconds() // 60),
            )
            period.reminder_state = 'upcoming'
            period.reminder_label = (
                f'Starts in {minutes} min'
                if minutes <= 120
                else f'Today at {period.start_time.strftime("%H:%M")}'
            )
            period.reminder_badge_class = 'bg-primary'
        else:
            period.reminder_state = 'finished'
            period.reminder_label = 'Finished'
            period.reminder_badge_class = 'bg-secondary'

    live = next(
        (period for period in today_periods if period.reminder_state == 'live'),
        None,
    )
    upcoming = next(
        (
            period for period in today_periods
            if period.reminder_state == 'upcoming'
        ),
        None,
    )
    attention = live or upcoming

    future_candidates = []
    for period in periods:
        days_until = (period.day_of_week - weekday) % 7
        if days_until == 0 and period.end_time <= current_time:
            days_until = 7
        period.next_occurrence_date = on_date + datetime.timedelta(days=days_until)
        period.next_occurrence_day = dict(RoutinePeriod.DAY_CHOICES)[period.day_of_week]
        future_candidates.append((
            days_until, period.start_time, period.period_number, period,
        ))
    next_period = min(
        future_candidates, default=(None, None, None, None)
    )[3]

    return {
        'periods': periods,
        'today_periods': today_periods,
        'active': live,
        'attention': attention,
        'next_period': next_period,
        'current_day': weekday,
    }


def submit_teaching_log_and_attendance(org, user, is_admin, post):
    """Create/update the day's TeachingLog for a subject-period (auto-filled
    from a RoutinePeriod, or manually specified) and mark per-student
    SubjectAttendanceRecord rows from the posted roster checkboxes.

    Returns (log, error_message) — log is None if error_message is set.
    """
    import datetime as _dt
    from django.db import transaction
    from django.utils import timezone
    from handle.models import (
        AcademicYear, RoutinePeriod, Subject, Classification, Section,
        TeachingLog, SubjectAttendanceRecord, Staff,
    )

    topic_covered = post.get('topic_covered', '').strip()
    if not topic_covered:
        return None, "Topic covered is required."

    today = timezone.localdate()
    date_str = post.get('date', '')
    try:
        log_date = _dt.datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else today
    except ValueError:
        log_date = today

    routine_period_id = post.get('routine_period')
    routine_period = None
    academic_year = None
    teacher_assignment = None
    if routine_period_id:
        try:
            period = RoutinePeriod.objects.select_related(
                'academic_year', 'subject__course', 'classification', 'section', 'teacher'
            ).get(pk=routine_period_id, org=org, is_active=True)
        except RoutinePeriod.DoesNotExist:
            return None, "Invalid period selected."
        if not is_admin and period.teacher_id != user.id:
            return None, "You can only take attendance for your own periods."
        subject = period.subject
        if subject.status != 'active':
            return None, "This subject is inactive and cannot accept attendance."
        classification = period.classification
        section = period.section
        teacher = period.teacher
        period_number = period.period_number
        routine_period = period
        academic_year = period.academic_year
        teacher_assignment = subject_assignment_for_teacher(
            subject, teacher, on_date=log_date, academic_year=academic_year,
            section=section,
        )
        if teacher_assignment is False:
            return None, "The routine teacher is not actively assigned to this subject."
    else:
        subject_id = post.get('subject')
        classification_id = post.get('classification')
        section_id = post.get('section')
        if not subject_id or not classification_id:
            return None, "Subject and Class are required."
        try:
            subject = Subject.objects.get(pk=subject_id, org=org, status='active')
            classification = Classification.objects.get(pk=classification_id, org=org)
        except (Subject.DoesNotExist, Classification.DoesNotExist):
            return None, "Invalid subject or class."
        section = Section.objects.filter(pk=section_id, org=org).first() if section_id else None
        period_number = post.get('period') or None
        teacher_id = post.get('teacher') if is_admin else None
        if is_admin and not teacher_id:
            return None, "Select the assigned teacher for manual subject attendance."
        teacher_staff = Staff.objects.filter(
            org=org, admin_id=teacher_id
        ).select_related('admin').first() if teacher_id else None
        if teacher_id and not teacher_staff:
            return None, "Please select a teacher from this organization."
        teacher = teacher_staff.admin if teacher_staff else user

        if subject.classification_id != classification.pk:
            return None, "The selected subject does not belong to this classification."
        if subject.section_id and subject.section_id != getattr(section, 'pk', None):
            return None, "The selected subject is assigned to a different section."
        if section and section.classification_id != classification.pk:
            return None, "The selected section does not belong to this classification."
        academic_year_id = post.get('academic_year')
        if academic_year_id:
            academic_year = AcademicYear.objects.filter(
                pk=academic_year_id, org=org, status='active'
            ).first()
            if not academic_year:
                return None, "Please select a valid academic year."
        else:
            academic_year = AcademicYear.objects.filter(
                org=org, is_current=True, status='active'
            ).order_by('-start_date', '-pk').first()
        teacher_assignment = subject_assignment_for_teacher(
            subject, teacher, on_date=log_date, academic_year=academic_year,
            section=section,
        )
        if teacher_assignment is False:
            return None, "The selected teacher is not actively assigned to this subject."

    if subject.course_id:
        if not subject.course.classifications.filter(pk=classification.pk).exists():
            return None, "This classification is not linked to the subject's course."
        if section and subject.course.sections.exists() and not subject.course.sections.filter(pk=section.pk).exists():
            return None, "This section is not linked to the subject's course."

    allowed_statuses = {choice[0] for choice in SubjectAttendanceRecord.STATUS_CHOICES}
    draft_value = post.get('save_as_draft')
    save_as_draft = (
        draft_value is True
        or str(draft_value).strip().lower() in {'1', 'true', 'yes', 'draft'}
    )
    target_status = 'draft' if save_as_draft else 'submitted'
    now = timezone.now()

    with transaction.atomic():
        # Lock and re-use the exact logical session, making repeated form/API
        # submissions idempotent.
        log = TeachingLog.objects.select_for_update().filter(
            org=org, teacher=teacher, subject=subject, classification=classification,
            section=section, date=log_date, period=period_number,
        ).order_by('pk').first()
        if log is None:
            log = TeachingLog(
                org=org, teacher=teacher, subject=subject, classification=classification,
                section=section, date=log_date, period=period_number,
                created_by=user,
            )
        elif log.status == 'approved' and not is_admin:
            return None, "Approved attendance cannot be changed by the teacher."

        log.branch = (
            getattr(routine_period, 'branch', None)
            or getattr(subject.course, 'branch', None)
            or classification.primary_branch
        )
        log.academic_year = academic_year
        log.course = subject.course
        log.teacher_assignment = teacher_assignment if teacher_assignment else None
        log.routine_period = routine_period
        log.start_time = getattr(routine_period, 'start_time', None)
        log.end_time = getattr(routine_period, 'end_time', None)
        log.room = getattr(routine_period, 'room', None) or post.get('room', '').strip() or None
        log.topic_covered = topic_covered
        log.chapter = post.get('chapter', '').strip() or None
        log.learning_objectives = post.get('learning_objectives', '').strip() or None
        log.remarks = post.get('remarks', '').strip() or None
        log.status = target_status
        if target_status == 'submitted':
            log.submitted_by = user
            log.submitted_at = now
            log.rejection_reason = None
        log.save()

        roster = roster_for_subject(
            org, subject, classification, section,
            attendance_date=log_date, academic_year=academic_year,
        )
        marked_any = False
        for m in roster:
            status = post.get(f'status_{m.pk}')
            if status not in allowed_statuses:
                status = 'present' if post.get(f'present_{m.pk}') else 'absent'
            SubjectAttendanceRecord.objects.update_or_create(
                teaching_log=log, member=m,
                defaults={
                    'status': status,
                    'remarks': post.get(f'remarks_{m.pk}', '').strip() or None,
                    'marked_by': user,
                    'org': org,
                },
            )
            marked_any = True
        if marked_any:
            log.recompute_attendance_counts()

    return log, None
