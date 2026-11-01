"""Import or update members from a CSV: manage.py import_members PATH"""

from pathlib import Path

from django.core.management.base import BaseCommand

from sws_membership.members.import_csv import import_members


class Command(BaseCommand):
    help = "Import or update members from a CSV with the documented columns"

    def add_arguments(self, parser):
        parser.add_argument("path")

    def handle(self, *args, **options):
        report = import_members(Path(options["path"]))
        for line_number, reason in report.rejected:
            self.stderr.write(f"line {line_number}: rejected, {reason}")
        self.stdout.write(report.summary())
