"""Load the development catalog and placeholder waiver: manage.py seed_catalog"""

from django.core.management.base import BaseCommand

from sws_membership.catalog.sample_data import load_sample_catalog
from sws_membership.waivers.sample_data import load_sample_waiver


class Command(BaseCommand):
    help = "Load the sample catalog and a placeholder waiver (idempotent)"

    def handle(self, *args, **options):
        created = load_sample_catalog()
        waiver = load_sample_waiver()
        self.stdout.write(
            f"sample catalog: created {created} products; placeholder waiver "
            f"{'published' if waiver else 'already present'}"
        )
