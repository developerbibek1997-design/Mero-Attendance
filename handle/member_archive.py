import json
import os

from django.conf import settings
from django.core import serializers
from django.db import transaction
from django.utils import timezone

from management.models import LeaveReport, AutoCheckin

from .models import (
    MemberHistory,
    PaySlip, AdvanceSalary, AdvanceInstallmentPayment,
    Timesheet, TimesheetEntry,
    AttendanceRecord, AttendanceGap, ADMSAttendanceEvent, QRAttendanceScanLog, SubjectAttendanceRecord,
    LiveTrackingSession, LocationPing,
    PayrollAdjustment, ProvidentFundRecord, SocialSecurityFundRecord, ProbationReview,
    ResignationRecord, StaffDocument, AbsenceCorrection, MemberWeekdayShift, MemberShiftOverride, MemberFace,
    StudentCourseEnrollment, ResultRecord, ResultSendLog,
    AssignmentSubmission, AssignmentSubmissionAttachment, AssignmentSubmissionHistory,
    HomeworkStatus, CourseMaterialAccess,
    TaskInstance, TaskUpdateLog, TaskAttachment, Task,
    FieldVisit, FieldVisitReport, ClientFollowUp, Complaint,
    Bill, BillItem, BillSendLog,
    BookIssue, Notice, NoticeRead, InAppNotification,
    StudentBusAssignment, BusTrackingSession, BusLocationPing, BusStudentTripStatus,
    StaffPermissionGrant,
)

# (model, lookup) — `lookup` is the queryset filter kwarg resolving to the
# member being archived. Order is parent-before-child: restore walks this
# same order so FK targets already exist by the time a child row is
# recreated; archive walks it to serialize everything before any deletes
# happen (so a CASCADE triggered by deleting a parent never destroys data
# we haven't captured yet).
ARCHIVE_REGISTRY = [
    (PaySlip, 'member'),
    (AdvanceSalary, 'member'),
    (AdvanceInstallmentPayment, 'advance__member'),
    (Timesheet, 'member'),
    (TimesheetEntry, 'timesheet__member'),
    (AttendanceRecord, 'mem'),
    (AttendanceGap, 'member'),
    (ADMSAttendanceEvent, 'member'),
    (QRAttendanceScanLog, 'member'),
    (SubjectAttendanceRecord, 'member'),
    (LiveTrackingSession, 'member'),
    (LocationPing, 'member'),
    (PayrollAdjustment, 'member'),
    (ProvidentFundRecord, 'member'),
    (SocialSecurityFundRecord, 'member'),
    (ProbationReview, 'member'),
    (ResignationRecord, 'member'),
    (StaffDocument, 'member'),
    (AbsenceCorrection, 'member'),
    (MemberWeekdayShift, 'member'),
    (MemberShiftOverride, 'member'),
    (MemberFace, 'member'),
    (LeaveReport, 'member'),
    (AutoCheckin, 'member'),
    (StudentCourseEnrollment, 'student'),
    (ResultRecord, 'student'),
    (ResultSendLog, 'member'),
    (AssignmentSubmission, 'student'),
    (AssignmentSubmissionAttachment, 'submission__student'),
    (AssignmentSubmissionHistory, 'submission__student'),
    (HomeworkStatus, 'student'),
    (CourseMaterialAccess, 'student'),
    (TaskInstance, 'assigned_member'),
    (TaskUpdateLog, 'instance__assigned_member'),
    (TaskAttachment, 'instance__assigned_member'),
    (FieldVisit, 'member'),
    (FieldVisitReport, 'visit__member'),
    (ClientFollowUp, 'visited_by'),
    (Complaint, 'filed_by'),
    (Bill, 'member'),
    (BillItem, 'bill__member'),
    (BillSendLog, 'bill__member'),
    (BookIssue, 'member'),
    (Notice, 'target_member'),
    (NoticeRead, 'member'),
    (InAppNotification, 'recipient'),
    (StudentBusAssignment, 'student'),
    (BusTrackingSession, 'driver'),
    (BusStudentTripStatus, 'student'),
    (BusLocationPing, 'driver'),
    (StaffPermissionGrant, 'member'),
]

# Fields Django's Model.save() always overwrites to "now" regardless of the
# value assigned (auto_now / auto_now_add) — restored via a raw queryset
# .update() afterwards, which bypasses that special-casing.
AUTO_TIMESTAMP_FIELDS = {
    PaySlip: ('generated_on', 'updated_at'),
}

# Plain M2M fields declared directly on `member` itself (not a child row).
MEMBER_M2M_FIELDS = ['courses', 'shifts']


def _model_key(model):
    return f"{model._meta.app_label}.{model._meta.model_name}"


def archive_member(mem, performed_by=None, reason=''):
    """Serialize every record linked to `mem` to a JSON file, then delete
    the live rows and flip the member to 'dumped'. Returns the relative
    media path of the archive file."""
    with transaction.atomic():
        archive = {
            'member_id': mem.id,
            'archived_at': timezone.now().isoformat(),
            'models': {},
            'm2m': {},
        }
        counts = {}

        querysets = []
        for model, lookup in ARCHIVE_REGISTRY:
            qs = model.objects.filter(**{lookup: mem})
            querysets.append(qs)
            rows = json.loads(serializers.serialize('json', qs))
            if rows:
                archive['models'][_model_key(model)] = rows
                counts[_model_key(model)] = len(rows)

        for field_name in MEMBER_M2M_FIELDS:
            archive['m2m'][field_name] = list(getattr(mem, field_name).values_list('id', flat=True))
        archive['m2m']['assigned_tasks'] = list(mem.assigned_tasks.values_list('id', flat=True))

        org_dir = os.path.join(settings.MEDIA_ROOT, 'member_archives', str(mem.org_id or 0))
        os.makedirs(org_dir, exist_ok=True)
        filename = f"member_{mem.id}_{timezone.now().strftime('%Y%m%d%H%M%S')}.json"
        with open(os.path.join(org_dir, filename), 'w') as f:
            json.dump(archive, f, indent=2, default=str)
        relative_path = os.path.join('member_archives', str(mem.org_id or 0), filename)

        # Nothing is lost even though some of these querysets may already be
        # empty by the time we get here (e.g. AdvanceInstallmentPayment rows
        # auto-deleted by AdvanceSalary's CASCADE) — everything was captured
        # above before any delete happened.
        for qs in querysets:
            qs.delete()

        for field_name in MEMBER_M2M_FIELDS:
            getattr(mem, field_name).clear()
        mem.assigned_tasks.clear()

        mem.previous_status = mem.status
        mem.status = 'dumped'
        mem.archive_file = relative_path
        mem.save()

        MemberHistory.objects.create(
            member=mem, org=mem.org, action='dumped',
            description=reason,
            metadata={'archive_file': relative_path, 'counts': counts},
            changed_by=performed_by,
        )

    return relative_path


def restore_member(mem, performed_by=None):
    """Recreate every archived record for `mem` from its JSON archive file
    and restore the member to its pre-dump status."""
    if not mem.archive_file:
        raise ValueError("This member has no archive to restore from.")

    full_path = os.path.join(settings.MEDIA_ROOT, mem.archive_file)
    with open(full_path) as f:
        archive = json.load(f)

    with transaction.atomic():
        restored_counts = {}
        for model, lookup in ARCHIVE_REGISTRY:
            rows = archive['models'].get(_model_key(model))
            if not rows:
                continue
            objs = list(serializers.deserialize('json', json.dumps(rows)))
            for obj in objs:
                obj.save()
            restored_counts[_model_key(model)] = len(objs)

            auto_fields = AUTO_TIMESTAMP_FIELDS.get(model)
            if auto_fields:
                for row, obj in zip(rows, objs):
                    field_values = row['fields']
                    update_kwargs = {name: field_values[name] for name in auto_fields if name in field_values}
                    if update_kwargs:
                        model.objects.filter(pk=obj.object.pk).update(**update_kwargs)

        for field_name in MEMBER_M2M_FIELDS:
            getattr(mem, field_name).set(archive['m2m'].get(field_name, []))

        task_ids = archive['m2m'].get('assigned_tasks', [])
        if task_ids:
            existing_ids = list(Task.objects.filter(id__in=task_ids).values_list('id', flat=True))
            mem.assigned_tasks.set(existing_ids)

        mem.status = mem.previous_status or 'active'
        mem.previous_status = None
        mem.archive_file = None
        mem.save()

        MemberHistory.objects.create(
            member=mem, org=mem.org, action='rejoined',
            metadata={'restored_counts': restored_counts},
            changed_by=performed_by,
        )
