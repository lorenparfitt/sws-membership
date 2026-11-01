"""Finding a member from what a scanner or a search box provides."""

from sws_membership.members.member_numbers import InvalidMemberNumber, normalise_member_number
from sws_membership.members.models import Member, normalise_email


def find_member_by_scan(scanned: str) -> Member | None:
    try:
        member_number = normalise_member_number(scanned)
    except InvalidMemberNumber:
        return None
    return Member.objects.filter(member_number=member_number).first()


def find_member_by_email(email: str) -> Member | None:
    return Member.objects.filter(email=normalise_email(email)).first()
