import pytest

from sws_membership.members.models import MemberRole
from sws_membership.members.roles import UnknownMember, grant_role, revoke_role
from tests.conftest import make_member

pytestmark = pytest.mark.django_db


def test_grant_and_revoke_round_trip():
    make_member("ada@example.com", first_name="Ada", last_name="Board")
    member = grant_role("Ada@Example.com", MemberRole.ADMIN)
    assert member.has_role(MemberRole.ADMIN)
    grant_role("ada@example.com", MemberRole.ADMIN)
    assert member.roles.count() == 1
    revoke_role("ada@example.com", MemberRole.ADMIN)
    assert not member.has_role(MemberRole.ADMIN)


def test_granting_to_an_unknown_email_fails_loudly():
    with pytest.raises(UnknownMember):
        grant_role("ghost@example.com", MemberRole.STAFF)
