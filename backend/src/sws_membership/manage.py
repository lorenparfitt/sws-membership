"""Operator commands run from a shell: python -m sws_membership.manage ...

Wiring only. Each command opens one database session, calls the domain
function, and commits.
"""

import argparse
import sys
from datetime import date
from pathlib import Path

from sws_membership.database import SessionLocal
from sws_membership.members.import_csv import import_members
from sws_membership.members.lookup import find_member_by_email
from sws_membership.members.member_numbers import allocate_member_number
from sws_membership.members.models import Member, MemberRole
from sws_membership.members.roles import UnknownMember, grant_role, revoke_role
from sws_membership.members.sample_data import generate_sample_members


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


def import_members_command(arguments: argparse.Namespace) -> None:
    with SessionLocal() as session:
        report = import_members(session, Path(arguments.path))
        session.commit()
    for line_number, reason in report.rejected:
        print(f"line {line_number}: rejected, {reason}", file=sys.stderr)
    print(report.summary())


def generate_sample_command(arguments: argparse.Namespace) -> None:
    path = Path(arguments.path)
    generate_sample_members(path, arguments.count, arguments.seed)
    print(f"wrote {arguments.count} made-up members to {path}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sws-membership")
    commands = parser.add_subparsers(dest="command", required=True)

    create = commands.add_parser("create-member", help="add a member with a new number")
    create.add_argument("email")
    create.add_argument("first_name")
    create.add_argument("last_name")
    create.add_argument("--date-of-birth", dest="date_of_birth", help="YYYY-MM-DD")
    create.set_defaults(run=create_member)

    importer = commands.add_parser("import-members", help="import or update members from a CSV")
    importer.add_argument("path")
    importer.set_defaults(run=import_members_command)

    sample = commands.add_parser(
        "generate-sample-members", help="write a CSV of made-up members for development"
    )
    sample.add_argument("path")
    sample.add_argument("--count", type=int, default=200)
    sample.add_argument("--seed", type=int, default=2026)
    sample.set_defaults(run=generate_sample_command)

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
