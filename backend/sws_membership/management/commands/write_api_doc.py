"""Write docs/api.md from the routes, or check that it is current."""

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from sws_membership.api_doc import render_api_doc

API_DOC = Path(settings.BASE_DIR).parent / "docs" / "api.md"


class Command(BaseCommand):
    help = "Write docs/api.md from the API routes (--check: fail if it is out of date)."

    def add_arguments(self, parser):
        parser.add_argument("--check", action="store_true")

    def handle(self, *args, check: bool, **options):
        text = render_api_doc()
        current = API_DOC.read_text() if API_DOC.exists() else ""
        if check:
            if current != text:
                raise CommandError(f"{API_DOC} is out of date; run: uv run doit api_doc")
            self.stdout.write(f"{API_DOC} is current")
            return
        API_DOC.write_text(text)
        self.stdout.write(f"wrote {API_DOC}")
