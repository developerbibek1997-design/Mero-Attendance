import datetime

from django.db import transaction
from django.utils import timezone

from .models import AttendanceRecord, member


class DuplicateAttendancePunch(Exception):
    """Raised when the same member submits another punch inside the cooldown."""

    def __init__(self, record, retry_after):
        self.record = record
        self.retry_after = max(1, int(retry_after))
        super().__init__('Attendance was already recorded. Please wait one minute.')


@transaction.atomic
def create_attendance_punch(*, memb, org, attendance_method, scanned_time=None):
    """Create one self-service punch with a cross-method, concurrency-safe guard.

    Locking the member row makes simultaneous QR/GPS/WiFi requests serialize, so
    two phone taps cannot create an accidental check-in/check-out pair.
    """
    locked_member = member.objects.select_for_update().get(pk=memb.pk, org=org)
    now = scanned_time or timezone.now()
    cooldown_start = now - datetime.timedelta(minutes=1)
    recent = (
        AttendanceRecord.objects.filter(
            mem=locked_member,
            org=org,
            scanned_time__gte=cooldown_start,
            scanned_time__lte=now,
        )
        .order_by('-scanned_time', '-pk')
        .first()
    )
    if recent is not None:
        elapsed = max(0, (now - recent.scanned_time).total_seconds())
        raise DuplicateAttendancePunch(recent, 60 - elapsed)

    already_marked = AttendanceRecord.objects.filter(
        mem=locked_member,
        org=org,
        scanned_time__date=timezone.localdate(now),
    ).exists()
    record = AttendanceRecord.objects.create(
        mem=locked_member,
        org=org,
        scanned_time=now,
        attendance_method=attendance_method,
    )
    return record, already_marked
