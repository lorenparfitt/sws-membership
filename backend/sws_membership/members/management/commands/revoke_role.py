"""Remove a role from a member: manage.py revoke_role EMAIL staff|admin"""

from django.core.management.base import BaseCommand, CommandError

from sws_membership.members.models import MemberRole
from sws_membership.members.roles import UnknownMember, revoke_role


class Command(BaseCommand):
    help = "Remove the staff or admin role from a member"

    def add_arguments(self, parser):
        parser.add_argument("email")
        parser.add_argument("role", choices=[role.value for role in MemberRole])

    def handle(self, *args, **options):
        try:
            member = revoke_role(options["email"], MemberRole(options["role"]))
        except UnknownMember:
            raise CommandError(f"no member with email {options['email']}")
        self.stdout.write(f"{member.email} roles: {', '.join(member.role_values()) or 'none'}")
