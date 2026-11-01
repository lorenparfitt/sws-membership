"""Role gates on the API: a plain member, staff, and admin against staff and admin routes."""

import pytest

from sws_membership.members.models import MemberRole
from tests.conftest import make_member

pytestmark = pytest.mark.django_db

STAFF_ROUTE = "/api/staff/members/1/photo"  # 404 once past the gate: no such member
ADMIN_ROUTE = "/api/admin/catalog/options"


def _signed_in(client, roles):
    member = make_member(f"{'-'.join(r.value for r in roles) or 'plain'}@example.com", roles=roles)
    client.sign_in(member)
    return member


def test_plain_member_is_refused_staff_routes(client):
    _signed_in(client, [])
    assert client.get(STAFF_ROUTE).status_code == 403


def test_staff_reach_staff_routes_but_not_admin_ones(client):
    _signed_in(client, [MemberRole.STAFF])
    assert client.get(STAFF_ROUTE).status_code == 404
    assert client.get(ADMIN_ROUTE).status_code == 403


def test_admin_reaches_every_role_route(client):
    _signed_in(client, [MemberRole.ADMIN])
    assert client.get(STAFF_ROUTE).status_code == 404
    assert client.get(ADMIN_ROUTE).status_code == 200


def test_no_session_is_unauthorised_not_forbidden(client):
    assert client.get(STAFF_ROUTE).status_code == 401
