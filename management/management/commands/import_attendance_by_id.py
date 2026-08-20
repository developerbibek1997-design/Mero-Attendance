"""
Management command: import_attendance_by_id

Bulk-imports historical AttendanceRecord rows for one organization from a
CSV where each row already carries the CURRENT member id (already resolved
by name against the target org, e.g. via import_attendance_by_name.py or a
manual mapping) so no name lookup happens at import time.

CSV format (no header row expected):
    member_id,member_name,record_time
    1203,Dambar Kumar Rai,2026-07-17 07:20:33

- member_name is kept only for the log output and error messages.
- record_time must be "YYYY-MM-DD HH:MM:SS".
- Every member_id is verified to belong to --org-id before anything is
  written; a row whose id doesn't belong to this org is skipped and
  reported, never silently attached to someone else's org.

Usage:
    python manage.py import_attendance_by_id --org-id 24 --file attendance.csv --dry-run
    python manage.py import_attendance_by_id --org-id 24 --file attendance.csv

Safety:
  - Each row is inserted in its own transaction.
  - A (member_id, scanned_time) pair that already exists is skipped, so
    re-running the same file twice never creates duplicate scans.
  - --dry-run validates every row and reports what would be created,
    without writing anything to the DB.
"""

import csv
import datetime

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from handle.models import AttendanceRecord, member
from management.models import Organization


class Command(BaseCommand):
    help = "Import historical AttendanceRecord rows for one org from a CSV keyed by current member id."

    def add_arguments(self, parser):
        parser.add_argument('--org-id', type=int, required=True, help='Organization ID to import into.')
        parser.add_argument('--file', type=str, required=True, help='Path to the CSV file (member_id,member_name,record_time).')
        parser.add_argument('--method', type=str, default='biometric',
                             help="attendance_method to record (default: 'biometric').")
        parser.add_argument('--dry-run', action='store_true', help='Validate only; make no DB changes.')

    def handle(self, *args, **options):
        org_id = options['org_id']
        path = options['file']
        dry_run = options['dry_run']
        method = options['method']

        try:
            org = Organization.objects.get(pk=org_id)
        except Organization.DoesNotExist:
            raise CommandError(f"Organization id={org_id} does not exist.")

        try:
            f = open(path, newline='', encoding='utf-8-sig')
        except FileNotFoundError:
            raise CommandError(f"File not found: {path}")
        reader = csv.reader(f)
        rows = [r for r in reader if r and any(c.strip() for c in r)]
        f.close()

        self.stdout.write(self.style.NOTICE(
            f"Importing attendance into org #{org.id} ({org.name}) from '{path}' "
            f"{'(DRY RUN - no changes will be saved)' if dry_run else ''}"
        ))

        valid_member_ids = set(member.objects.filter(org=org).values_list('id', flat=True))
        existing_scans = set(
            AttendanceRecord.objects.filter(org=org).values_list('mem_id', 'scanned_time')
        )

        verb = 'would create' if dry_run else 'created'
        created = 0
        duplicate = 0
        skipped = []

        for row_num, row in enumerate(rows, start=1):
            if len(row) < 3:
                skipped.append((row_num, '(unparsable row)', f"expected 3 columns, got {len(row)}"))
                continue
            id_str, name, time_str = row[0].strip(), row[1].strip(), row[2].strip()

            try:
                mem_id = int(id_str)
            except ValueError:
                skipped.append((row_num, name, f"invalid member_id: '{id_str}'"))
                continue

            if mem_id not in valid_member_ids:
                skipped.append((row_num, name, f"member #{mem_id} does not belong to org #{org.id}"))
                continue

            try:
                scanned_time = datetime.datetime.strptime(time_str, '%Y-%m-%d %H:%M:%S')
            except ValueError:
                skipped.append((row_num, name, f"bad time format: '{time_str}' (expected YYYY-MM-DD HH:MM:SS)"))
                continue

            if timezone.is_naive(scanned_time):
                try:
                    scanned_time = timezone.make_aware(scanned_time)
                except Exception:
                    pass

            if (mem_id, scanned_time) in existing_scans:
                duplicate += 1
                continue

            if dry_run:
                created += 1
                self.stdout.write(f"  + Attendance {verb}: {name} (member #{mem_id}) at {scanned_time}")
                existing_scans.add((mem_id, scanned_time))
                continue

            try:
                with transaction.atomic():
                    AttendanceRecord.objects.create(
                        mem_id=mem_id, org=org, scanned_time=scanned_time, attendance_method=method,
                    )
                existing_scans.add((mem_id, scanned_time))
                created += 1
                self.stdout.write(self.style.SUCCESS(f"  + Attendance {verb}: {name} (member #{mem_id}) at {scanned_time}"))
            except Exception as e:
                skipped.append((row_num, name, f"error: {e}"))
                continue

        self.stdout.write('')
        self.stdout.write(self.style.NOTICE("-- Summary --------------------------"))
        self.stdout.write(f"  Attendance records {verb}: {created}")
        self.stdout.write(f"  Already existed (skipped as duplicate): {duplicate}")
        self.stdout.write(f"  Rows skipped (invalid):        {len(skipped)}")
        for row_num, name, reason in skipped:
            self.stdout.write(self.style.WARNING(f"    row {row_num} ({name}): {reason}"))
        if dry_run:
            self.stdout.write(self.style.NOTICE("Dry run complete - no changes were saved. Re-run without --dry-run to commit."))
