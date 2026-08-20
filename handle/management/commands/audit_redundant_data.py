"""Read-only tenant-aware duplicate audit for core master data."""

from django.core.management.base import BaseCommand
from django.db.models import Count

from handle.models import Branch, Classification, Course, Device, PaySlip, Section, member
from management.models import Occasion


class Command(BaseCommand):
    help = 'Report possible duplicate master data without changing or deleting records.'

    def handle(self, *args, **options):
        checks = (
            ('Member cards', member.objects.exclude(card__isnull=True).exclude(card=''), ('org_id', 'card')),
            ('Member device IDs', member.objects.exclude(device_id__isnull=True), ('org_id', 'device_id')),
            ('Courses', Course.objects.all(), ('org_id', 'branch_id', 'name')),
            ('Payslips', PaySlip.objects.all(), ('org_id', 'member_id', 'from_date', 'to_date')),
            ('Classifications', Classification.objects.all(), ('org_id', 'branch_id', 'name')),
            ('Branches', Branch.objects.all(), ('org_id', 'code')),
            ('Sections', Section.objects.all(), ('org_id', 'classification_id', 'name')),
            ('Device serials', Device.objects.exclude(serial_number__isnull=True), ('serial_number',)),
            ('Occasions', Occasion.objects.all(), ('org_id', 'name', 'date')),
        )
        total = 0
        for label, queryset, fields in checks:
            groups = list(queryset.values(*fields).annotate(count=Count('id')).filter(count__gt=1))
            total += len(groups)
            style = self.style.WARNING if groups else self.style.SUCCESS
            self.stdout.write(style(f'{label}: {len(groups)} duplicate group(s)'))
            for group in groups[:50]:
                self.stdout.write(f'  {group}')
        self.stdout.write(
            self.style.WARNING(f'Total groups requiring review: {total}')
            if total else self.style.SUCCESS('No duplicate groups found.')
        )
