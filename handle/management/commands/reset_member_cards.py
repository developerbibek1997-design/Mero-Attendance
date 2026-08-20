"""Bulk-reset the card/RFID number for every member of one organization."""

from django.core.management.base import BaseCommand, CommandError

from handle.models import member


class Command(BaseCommand):
    help = "Set card='0' for every member of the given organization (dumped members are skipped)."

    def add_arguments(self, parser):
        parser.add_argument('org_id', type=int, help='Organization id whose members should be reset.')

    def handle(self, *args, **options):
        org_id = options['org_id']
        qs = member.objects.filter(org_id=org_id).exclude(status='dumped')
        count = qs.count()
        if count == 0:
            raise CommandError(f'No members found for org_id={org_id}.')

        updated = qs.update(card='0')
        self.stdout.write(self.style.SUCCESS(
            f"Set card='0' for {updated} member(s) in org_id={org_id}."
        ))
