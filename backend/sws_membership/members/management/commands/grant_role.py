"""Give a member a role: manage.py grant_role EMAIL staff|admin"""

from django.core.management.base import BaseCommand, CommandError

from sws_membership.members.models import MemberRole
from sws_membership.members.roles import UnknownMember, grant_role


class Command(BaseCommand):
    help = "Give a member the staff or admin role"

    def add_arguments(self, parser):
        parser.add_argument("email")
        parser.add_argument("role", choices=[role.value for role in MemberRole])

    def handle(self, *args, **options):
        try:
            member = grant_role(options["email"], MemberRole(options["role"]))
        except UnknownMember:
            raise CommandError(f"no member with email {options['email']}")
        self.stdout.write(f"{member.email} roles: {', '.join(member.role_values()) or 'none'}")
