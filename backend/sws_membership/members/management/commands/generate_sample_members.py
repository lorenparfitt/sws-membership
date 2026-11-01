"""Write a CSV of made-up members: manage.py generate_sample_members PATH [--count] [--seed]"""

from pathlib import Path

from django.core.management.base import BaseCommand

from sws_membership.members.sample_data import generate_sample_members


class Command(BaseCommand):
    help = "Write a CSV of fictional members for development; never real data"

    def add_arguments(self, parser):
        parser.add_argument("path")
        parser.add_argument("--count", type=int, default=200)
        parser.add_argument("--seed", type=int, default=2026)

    def handle(self, *args, **options):
        path = Path(options["path"])
        generate_sample_members(path, options["count"], options["seed"])
        self.stdout.write(f"wrote {options['count']} made-up members to {path}")
