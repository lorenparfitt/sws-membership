import re
from datetime import UTC, datetime, timedelta

import pytest

from sws_membership.auth import service
from sws_membership.auth.models import LoginToken
from sws_membership.members.member_numbers import allocate_member_number
from sws_membership.members.models import Member, MemberRole, MemberRoleAssignment


def _member(session, email="rider@example.com", roles=()) -> Member:
    member = Member(
        member_number=allocate_member_number(session),
        first_name="Sam",
        last_name="Rider",
        email=email,
        roles=[MemberRoleAssignment(role=role) for role in roles],
    )
    session.add(member)
    session.flush()
    return member


def _sent_token(mailer) -> str:
    match = re.search(r"token=([A-Za-z0-9_-]+)", mailer.sent[-1].text)
    assert match, mailer.sent[-1].text
    return match.group(1)


def test_requesting_a_link_emails_a_single_use_token(session, client, mailer):
    member = _member(session)
    response = client.post("/api/auth/request-link", json={"email": "Rider@Example.com"})
    assert response.status_code == 202
    assert len(mailer.sent) == 1
    assert mailer.sent[0].to == member.email
    assert session.query(LoginToken).filter_by(member_id=member.id).count() == 1


def test_unknown_address_is_accepted_but_sends_nothing(session, client, mailer):
    response = client.post("/api/auth/request-link", json={"email": "nobody@example.com"})
    assert response.status_code == 202
    assert mailer.sent == []
    assert session.query(LoginToken).count() == 0


def test_redeeming_the_link_opens_a_session_that_me_recognises(session, client, mailer):
    member = _member(session, roles=[MemberRole.STAFF])
    client.post("/api/auth/request-link", json={"email": member.email})
    redeemed = client.post("/api/auth/redeem", json={"token": _sent_token(mailer)})
    assert redeemed.status_code == 200
    assert redeemed.json()["roles"] == ["staff"]
    assert "sws_session" in redeemed.cookies

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["member_number"] == member.member_number


def test_a_link_works_only_once(session, client, mailer):
    member = _member(session)
    client.post("/api/auth/request-link", json={"email": member.email})
    token = _sent_token(mailer)
    assert client.post("/api/auth/redeem", json={"token": token}).status_code == 200
    assert client.post("/api/auth/redeem", json={"token": token}).status_code == 400


def test_an_expired_link_is_rejected(session, mailer):
    member = _member(session)
    issued = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    service.request_login_link(session, mailer, member.email, "http://app", now=issued)
    token = _sent_token(mailer)
    too_late = issued + service.LOGIN_LINK_LIFETIME + timedelta(seconds=1)
    with pytest.raises(service.LoginLinkRejected):
        service.redeem_login_link(session, token, now=too_late)


def test_a_forged_token_is_rejected(client):
    assert client.post("/api/auth/redeem", json={"token": "not-a-real-token"}).status_code == 400


def test_me_without_a_session_is_unauthorised(client):
    assert client.get("/api/auth/me").status_code == 401


def test_sign_out_ends_the_session(session, client, mailer):
    member = _member(session)
    client.post("/api/auth/request-link", json={"email": member.email})
    client.post("/api/auth/redeem", json={"token": _sent_token(mailer)})
    assert client.get("/api/auth/me").status_code == 200
    assert client.post("/api/auth/sign-out").status_code == 204
    assert client.get("/api/auth/me").status_code == 401


def test_an_expired_session_no_longer_resolves(session):
    member = _member(session)
    opened = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    token = service.open_session(session, member, now=opened)
    assert service.resolve_session(session, token, now=opened + timedelta(days=1)) is member
    too_late = opened + service.SESSION_LIFETIME + timedelta(seconds=1)
    assert service.resolve_session(session, token, now=too_late) is None
