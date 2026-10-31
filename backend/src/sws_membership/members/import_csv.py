"""Importing members from a CSV, idempotently.

The file carries one row per member with the header below. A WellnessLiving
export is mapped onto this header by a small adapter at cut-over; until then
the generated sample data uses it directly, so the import path is the same
code either way.

Rows are keyed on member number. Running the same file twice changes
nothing the second time, and a corrected file updates the rows it changes,
so a partial or repeated import is always safe.
"""

import csv
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from sws_membership.members.member_numbers import (
    InvalidMemberNumber,
    normalise_member_number,
    reserve_member_numbers_through,
)
from sws_membership.members.models import Member, MemberSport, Sport

COLUMNS = ("member_number", "first_name", "last_name", "email", "phone", "date_of_birth")
# Present when the source has them; blank or absent leaves the field empty.
OPTIONAL_COLUMNS = ("address_line_1", "address_line_2", "city", "province", "postal_code", "sports")


@dataclass
class ImportReport:
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    rejected: list[tuple[int, str]] = field(default_factory=list)
    highest_member_number: int = 0

    def summary(self) -> str:
        return (
            f"created {self.created}, updated {self.updated}, unchanged {self.unchanged}, "
            f"rejected {len(self.rejected)}, highest member number {self.highest_member_number}"
        )


def _parse_date(value: str) -> date | None:
    value = value.strip()
    return date.fromisoformat(value) if value else None


def import_members(session: Session, path: Path) -> ImportReport:
    report = ImportReport()
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        missing = [column for column in COLUMNS if column not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"{path} lacks columns: {', '.join(missing)}")
        existing_by_number = {
            member.member_number: member for member in session.scalars(select(Member))
        }
        seen_numbers: set[int] = set()
        for line_number, row in enumerate(reader, start=2):
            try:
                member_number = normalise_member_number(row["member_number"])
                email = row["email"].strip().lower()
                if not email:
                    raise ValueError("empty email")
                values = {
                    "first_name": row["first_name"].strip(),
                    "last_name": row["last_name"].strip(),
                    "email": email,
                    "phone": row["phone"].strip() or None,
                    "date_of_birth": _parse_date(row["date_of_birth"]),
                }
                for column in OPTIONAL_COLUMNS[:-1]:
                    values[column] = (row.get(column) or "").strip() or None
                sports = tuple(
                    Sport(code.strip())
                    for code in (row.get("sports") or "").split(";")
                    if code.strip()
                )
                if member_number in seen_numbers:
                    raise ValueError(f"member number {member_number} appears twice")
            except (InvalidMemberNumber, ValueError, KeyError) as problem:
                report.rejected.append((line_number, str(problem) or "invalid member number"))
                continue
            seen_numbers.add(member_number)
            report.highest_member_number = max(report.highest_member_number, member_number)

            member = existing_by_number.get(member_number)
            if member is None:
                session.add(
                    Member(
                        member_number=member_number,
                        sports=[MemberSport(sport=s) for s in sports],
                        **values,
                    )
                )
                report.created += 1
                continue
            changed = False
            for name, value in values.items():
                if getattr(member, name) != value:
                    setattr(member, name, value)
                    changed = True
            if {row.sport for row in member.sports} != set(sports):
                member.sports[:] = [MemberSport(sport=s) for s in sports]
                changed = True
            if changed:
                report.updated += 1
            else:
                report.unchanged += 1
        session.flush()
    if report.highest_member_number:
        reserve_member_numbers_through(session, report.highest_member_number)
    return report
