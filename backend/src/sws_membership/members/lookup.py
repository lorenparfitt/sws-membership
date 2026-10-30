"""Finding a member from what a scanner or a search box provides."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from sws_membership.members.member_numbers import InvalidMemberNumber, normalise_member_number
from sws_membership.members.models import Member


def find_member_by_scan(session: Session, scanned: str) -> Member | None:
    try:
        member_number = normalise_member_number(scanned)
    except InvalidMemberNumber:
        return None
    return session.scalars(select(Member).where(Member.member_number == member_number)).first()


def find_member_by_email(session: Session, email: str) -> Member | None:
    return session.scalars(select(Member).where(Member.email == email.strip().lower())).first()
