"""Add a member with a new number: manage.py create_member EMAIL FIRST LAST [--date-of-birth]"""

from datetime import date

from django.core.management.base import BaseCommand, CommandError

from sws_membership.members.lookup import find_member_by_email
from sws_membership.members.models import Member


class Command(BaseCommand):
    help = "Add a member with a newly allocated member number"

    def add_arguments(self, parser):
        parser.add_argument("email")
        parser.add_argument("first_name")
        parser.add_argument("last_name")
        parser.add_argument("--date-of-birth", dest="date_of_birth", help="YYYY-MM-DD")
        parser.add_argument("--password", help="set a password at once (development only)")

    def handle(self, *args, **options):
        if find_member_by_email(options["email"]) is not None:
            raise CommandError(f"a member with email {options['email']} already exists")
        member = Member.objects.create_user(
            options["email"],
            options["password"],
            first_name=options["first_name"],
            last_name=options["last_name"],
            date_of_birth=date.fromisoformat(options["date_of_birth"])
            if options["date_of_birth"]
            else None,
        )
        self.stdout.write(
            f"created member {member.member_number} {member.first_name} {member.last_name}"
        )
