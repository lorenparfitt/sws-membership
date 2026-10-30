"""Operator commands run from a shell: python -m sws_membership.manage ...

Wiring only. Each command opens one database session, calls the domain
function, and commits.
"""

import argparse
import sys
from datetime import date

from sws_membership.database import SessionLocal
from sws_membership.members.lookup import find_member_by_email
from sws_membership.members.member_numbers import allocate_member_number
from sws_membership.members.models import Member, MemberRole
from sws_membership.members.roles import UnknownMember, grant_role, revoke_role


def create_member(arguments: argparse.Namespace) -> None:
    with SessionLocal() as session:
        if find_member_by_email(session, arguments.email) is not None:
            sys.exit(f"a member with email {arguments.email} already exists")
        member = Member(
            member_number=allocate_member_number(session),
            first_name=arguments.first_name,
            last_name=arguments.last_name,
            email=arguments.email.strip().lower(),
            date_of_birth=date.fromisoformat(arguments.date_of_birth)
            if arguments.date_of_birth
            else None,
        )
        session.add(member)
        session.commit()
        print(f"created member {member.member_number} {member.first_name} {member.last_name}")


def change_role(arguments: argparse.Namespace) -> None:
    action = grant_role if arguments.command == "grant-role" else revoke_role
    with SessionLocal() as session:
        try:
            member = action(session, arguments.email, MemberRole(arguments.role))
        except UnknownMember:
            sys.exit(f"no member with email {arguments.email}")
        session.commit()
        roles = sorted(assignment.role.value for assignment in member.roles) or ["none"]
        print(f"{member.email} roles: {', '.join(roles)}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sws-membership")
    commands = parser.add_subparsers(dest="command", required=True)

    create = commands.add_parser("create-member", help="add a member with a new number")
    create.add_argument("email")
    create.add_argument("first_name")
    create.add_argument("last_name")
    create.add_argument("--date-of-birth", dest="date_of_birth", help="YYYY-MM-DD")
    create.set_defaults(run=create_member)

    role_values = [role.value for role in MemberRole]
    for name, help_text in (("grant-role", "give a member a role"), ("revoke-role", "remove one")):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("email")
        command.add_argument("role", choices=role_values)
        command.set_defaults(run=change_role)
    return parser


def main(argv: list[str] | None = None) -> None:
    arguments = build_parser().parse_args(argv)
    arguments.run(arguments)


if __name__ == "__main__":
    main()
