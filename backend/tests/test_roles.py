from fastapi import APIRouter, Depends

from sws_membership.auth import service
from sws_membership.auth.dependencies import SESSION_COOKIE, require_role
from sws_membership.members.member_numbers import allocate_member_number
from sws_membership.members.models import Member, MemberRole, MemberRoleAssignment

probe = APIRouter()


@probe.get("/probe/staff", dependencies=[Depends(require_role(MemberRole.STAFF))])
def staff_only() -> dict[str, bool]:
    return {"ok": True}


@probe.get("/probe/admin", dependencies=[Depends(require_role(MemberRole.ADMIN))])
def admin_only() -> dict[str, bool]:
    return {"ok": True}


def _signed_in(session, client, roles):
    member = Member(
        member_number=allocate_member_number(session),
        first_name="Pat",
        last_name="Gate",
        email=f"{'-'.join(r.value for r in roles) or 'plain'}@example.com",
        roles=[MemberRoleAssignment(role=role) for role in roles],
    )
    session.add(member)
    session.flush()
    client.cookies.set(SESSION_COOKIE, service.open_session(session, member))
    client.app.include_router(probe)
    return member


def test_plain_member_is_refused_staff_routes(session, client):
    _signed_in(session, client, [])
    assert client.get("/probe/staff").status_code == 403


def test_staff_reach_staff_routes_but_not_admin_ones(session, client):
    _signed_in(session, client, [MemberRole.STAFF])
    assert client.get("/probe/staff").status_code == 200
    assert client.get("/probe/admin").status_code == 403


def test_admin_reaches_every_role_route(session, client):
    _signed_in(session, client, [MemberRole.ADMIN])
    assert client.get("/probe/staff").status_code == 200
    assert client.get("/probe/admin").status_code == 200
