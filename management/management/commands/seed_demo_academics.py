"""Idempotently enrich the existing School Demo with connected academic data.

This command intentionally targets only the organization named ``School Demo``.
It never resets the organization and never touches another tenant.
"""

from datetime import time, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from management.models import Organization
from handle.models import (
    AcademicYear,
    Assignment,
    AssignmentSubmission,
    AssignmentSubmissionHistory,
    Branch,
    Classification,
    ExamTerm,
    Homework,
    HomeworkStatus,
    RoutinePeriod,
    Section,
    Staff,
    Subject,
    SubjectTeacherAssignment,
    member,
)


DEMO_ORG_NAME = 'School Demo'
DEMO_PREFIX = '[Demo]'
SUBJECT_TEACHER_SLOT = {
    'Computer': 0,
    'Nepali': 0,
    'English': 1,
    'Mathematics': 2,
    'Science': 3,
    'Social Studies': 4,
}
PERIODS = {
    'A': (
        (1, time(8, 0), time(8, 45)),
        (2, time(8, 50), time(9, 35)),
        (3, time(9, 50), time(10, 35)),
        (4, time(10, 40), time(11, 25)),
    ),
    'B': (
        (5, time(11, 45), time(12, 30)),
        (6, time(12, 35), time(13, 20)),
        (7, time(13, 35), time(14, 20)),
        (8, time(14, 25), time(15, 10)),
    ),
}


class Command(BaseCommand):
    help = "Add safe, linked routines/homework/assignments to School Demo."

    @transaction.atomic
    def handle(self, *args, **options):
        org = Organization.objects.filter(name=DEMO_ORG_NAME).first()
        if not org:
            raise CommandError(
                "School Demo does not exist. Run seed_demo_orgs --only school first."
            )

        teachers = list(
            Staff.objects.filter(
                org=org,
                member__member_type='teacher',
                member__status='active',
            ).select_related('admin', 'member').order_by('member_id')
        )
        if len(teachers) < 5:
            raise CommandError("School Demo needs at least five active teacher accounts.")

        academic_year = AcademicYear.objects.filter(
            org=org, is_current=True, status='active',
        ).order_by('-start_date', '-pk').first()
        if not academic_year:
            academic_year = AcademicYear.objects.filter(
                org=org, status='active',
            ).order_by('-start_date', '-pk').first()
        if not academic_year:
            raise CommandError("School Demo needs an active academic year.")
        branch = Branch.objects.filter(org=org).order_by('pk').first()
        today = timezone.localdate()

        classifications = list(
            Classification.objects.filter(
                org=org, status='active', name__startswith='Class ',
            ).order_by('name')
        )
        if not classifications:
            raise CommandError("School Demo has no active school classifications.")

        # Earlier demo records may have broad or unmapped authority. Preserve
        # them for audit while removing them from future dashboard workflows.
        RoutinePeriod.objects.filter(
            org=org,
            is_active=True,
            teacher_assignment__isnull=True,
        ).update(is_active=False)
        SubjectTeacherAssignment.objects.filter(
            org=org,
            status='active',
            section__isnull=True,
            subject__section__isnull=True,
        ).update(status='inactive', end_date=today)

        scope_map = {}
        scope_count = 0
        for classification in classifications:
            sections = list(
                Section.objects.filter(
                    org=org,
                    classification=classification,
                    status='active',
                    name__in=PERIODS,
                ).order_by('name')
            )
            subjects = list(
                Subject.objects.filter(
                    org=org,
                    classification=classification,
                    section__isnull=True,
                    status='active',
                    name__in=SUBJECT_TEACHER_SLOT,
                ).order_by('name')
            )
            for section in sections:
                for subject in subjects:
                    teacher = teachers[SUBJECT_TEACHER_SLOT[subject.name]].admin
                    scope, _ = SubjectTeacherAssignment.objects.update_or_create(
                        org=org,
                        subject=subject,
                        teacher=teacher,
                        academic_year=academic_year,
                        section=section,
                        start_date=academic_year.start_date,
                        defaults={
                            'branch': branch,
                            'course': subject.course,
                            'classification': classification,
                            'end_date': academic_year.end_date,
                            'status': 'active',
                            'is_primary': subject.name == 'Computer',
                            'notes': (
                                f"{DEMO_PREFIX} section-specific teaching scope "
                                "for routines and student work."
                            ),
                        },
                    )
                    scope_map[(classification.pk, section.pk, subject.name)] = scope
                    scope_count += 1

        # Six working days, four periods per section. A sections run in the
        # morning and B sections in the day shift. The Latin-square teacher
        # rotation prevents teacher/class overlaps while keeping every
        # teacher dashboard populated.
        routine_count = 0
        fixed_subjects = {
            1: 'English',
            2: 'Mathematics',
            3: 'Science',
            4: 'Social Studies',
        }
        for day in range(6):
            for section_name, period_defs in PERIODS.items():
                for slot_index, (period_number, start, end) in enumerate(period_defs):
                    for class_index, classification in enumerate(classifications):
                        section = Section.objects.get(
                            org=org,
                            classification=classification,
                            name=section_name,
                        )
                        teacher_slot = (class_index + slot_index + day) % 5
                        subject_name = fixed_subjects.get(teacher_slot)
                        if teacher_slot == 0:
                            subject_name = (
                                'Computer'
                                if (class_index + slot_index + day) % 2 == 0
                                else 'Nepali'
                            )
                        scope = scope_map[(
                            classification.pk,
                            section.pk,
                            subject_name,
                        )]
                        RoutinePeriod.objects.update_or_create(
                            org=org,
                            day_of_week=day,
                            period_number=period_number,
                            classification=classification,
                            section=section,
                            defaults={
                                'branch': branch,
                                'subject': scope.subject,
                                'teacher': scope.teacher,
                                'teacher_assignment': scope,
                                'academic_year': academic_year,
                                'start_time': start,
                                'end_time': end,
                                'room': (
                                    f"{classification.name.replace('Class ', 'C')}-"
                                    f"{section.name}"
                                ),
                                'shift': 'morning' if section_name == 'A' else 'day',
                                'is_active': True,
                            },
                        )
                        routine_count += 1

        homework_count = 0
        assignment_count = 0
        submission_count = 0
        for class_index, classification in enumerate(classifications):
            for section in Section.objects.filter(
                org=org,
                classification=classification,
                status='active',
                name__in=PERIODS,
            ).order_by('name'):
                subject_name = (
                    'Computer'
                    if (class_index + (0 if section.name == 'A' else 1)) % 2 == 0
                    else 'English'
                )
                scope = scope_map[(classification.pk, section.pk, subject_name)]
                students = list(member.objects.filter(
                    org=org,
                    classification=classification,
                    section=section,
                    status='active',
                    member_type__in=('student', 'trainee'),
                ).order_by('pk'))

                description = (
                    f"{DEMO_PREFIX} {classification.name} {section.name} "
                    f"{subject_name} practice homework. Review today's lesson "
                    "and complete the exercise in your notebook."
                )
                homework, _ = Homework.objects.update_or_create(
                    org=org,
                    classification=classification,
                    section=section,
                    subject=scope.subject,
                    description=description,
                    defaults={
                        'branch': branch,
                        'teacher_assignment': scope,
                        'assigned_by': scope.teacher,
                        'due_date': today + timedelta(days=3 + class_index),
                        'priority': 'medium',
                        'estimated_time_minutes': 35,
                        'frequency': 'one_time',
                        'status': 'active',
                    },
                )
                HomeworkStatus.objects.bulk_create(
                    [
                        HomeworkStatus(homework=homework, student=student)
                        for student in students
                    ],
                    ignore_conflicts=True,
                )
                if students:
                    HomeworkStatus.objects.filter(homework=homework).update(
                        status='pending',
                        completed_at=None,
                        verified_by_teacher=False,
                        verified_at=None,
                    )
                    sample_completed_status = HomeworkStatus.objects.get(
                        homework=homework,
                        student=students[-1],
                    )
                    sample_completed_status.status = 'completed'
                    sample_completed_status.completed_at = timezone.now()
                    sample_completed_status.save(update_fields=[
                        'status', 'completed_at',
                    ])
                homework_count += 1

                title = (
                    f"{DEMO_PREFIX} {classification.name} {section.name} "
                    f"{subject_name} Practice Assignment"
                )
                assignment, _ = Assignment.objects.update_or_create(
                    org=org,
                    title=title,
                    defaults={
                        'branch': branch,
                        'classification': classification,
                        'section': section,
                        'subject': scope.subject,
                        'teacher_assignment': scope,
                        'course': scope.course,
                        'assigned_by': scope.teacher,
                        'description': (
                            "Solve the subject practice set and submit your "
                            "working before the deadline."
                        ),
                        'instructions': (
                            "Write clear steps. Attach a photo or PDF when submitting."
                        ),
                        'start_date': today,
                        'due_date': today + timedelta(days=7 + class_index),
                        'total_marks': Decimal('25.00'),
                        'passing_marks': Decimal('10.00'),
                        'visibility': 'published',
                        'status': 'open',
                    },
                )
                assignment_count += 1
                if students:
                    submission, created = AssignmentSubmission.objects.get_or_create(
                        assignment=assignment,
                        student=students[0],
                        defaults={
                            'submitted_at': timezone.now(),
                            'student_comments': (
                                f"{DEMO_PREFIX} Sample student submission for teacher review."
                            ),
                            'status': 'submitted',
                        },
                    )
                    if created:
                        AssignmentSubmissionHistory.objects.create(
                            submission=submission,
                            action='submitted',
                            status='submitted',
                            performed_by=getattr(
                                getattr(students[0], 'staff', None),
                                'admin',
                                None,
                            ),
                        )
                    submission_count += 1

        markable_exams = ExamTerm.objects.filter(
            org=org,
            classification__in=classifications,
            status='marks_entry',
            is_published=False,
        ).count()
        self.stdout.write(self.style.SUCCESS(
            "School Demo academic data ready: "
            f"teacher_scopes={scope_count}, routines={routine_count}, "
            f"homework={homework_count}, assignments={assignment_count}, "
            f"sample_submissions={submission_count}, "
            f"markable_exams={markable_exams}."
        ))
