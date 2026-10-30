import pytest

from sws_membership.members.member_numbers import allocate_member_number
from sws_membership.members.models import Member, MemberRole
from sws_membership.members.roles import UnknownMember, grant_role, revoke_role


def test_grant_and_revoke_round_trip(session):
    session.add(
        Member(
            member_number=allocate_member_number(session),
            first_name="Ada",
            last_name="Board",
            email="ada@example.com",
        )
    )
    session.flush()
    member = grant_role(session, "Ada@Example.com", MemberRole.ADMIN)
    assert member.has_role(MemberRole.ADMIN)
    grant_role(session, "ada@example.com", MemberRole.ADMIN)
    assert len(member.roles) == 1
    revoke_role(session, "ada@example.com", MemberRole.ADMIN)
    assert not member.has_role(MemberRole.ADMIN)


def test_granting_to_an_unknown_email_fails_loudly(session):
    with pytest.raises(UnknownMember):
        grant_role(session, "ghost@example.com", MemberRole.STAFF)
