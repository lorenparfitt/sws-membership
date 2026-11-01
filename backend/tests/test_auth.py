import re
from datetime import UTC, datetime, timedelta

import pytest

from sws_membership.accounts import service
from sws_membership.accounts.models import LoginToken
from sws_membership.members.models import MemberRole
from tests.conftest import make_member

pytestmark = pytest.mark.django_db


def _sent_token(mailer) -> str:
    match = re.search(r"token=([A-Za-z0-9_-]+)", mailer.sent[-1].text)
    assert match, mailer.sent[-1].text
    return match.group(1)


def test_requesting_a_link_emails_a_single_use_token(client, mailer):
    member = make_member()
    response = client.post_json("/api/auth/request-link", {"email": "Rider@Example.com"})
    assert response.status_code == 202
    assert len(mailer.sent) == 1
    assert mailer.sent[0].to == member.email
    assert LoginToken.objects.filter(member=member).count() == 1


def test_unknown_address_is_accepted_but_sends_nothing(client, mailer):
    response = client.post_json("/api/auth/request-link", {"email": "nobody@example.com"})
    assert response.status_code == 202
    assert mailer.sent == []
    assert LoginToken.objects.count() == 0


def test_redeeming_the_link_opens_a_session_that_me_recognises(client, mailer):
    member = make_member(roles=[MemberRole.STAFF])
    client.post_json("/api/auth/request-link", {"email": member.email})
    redeemed = client.post_json("/api/auth/redeem", {"token": _sent_token(mailer)})
    assert redeemed.status_code == 200, redeemed.content
    assert redeemed.json()["roles"] == ["staff"]
    assert "sessionid" in redeemed.cookies

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["member_number"] == member.member_number


def test_a_link_works_only_once(client, mailer):
    member = make_member()
    client.post_json("/api/auth/request-link", {"email": member.email})
    token = _sent_token(mailer)
    assert client.post_json("/api/auth/redeem", {"token": token}).status_code == 200
    assert client.post_json("/api/auth/redeem", {"token": token}).status_code == 400


def test_an_expired_link_is_rejected(mailer):
    member = make_member()
    issued = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    service.request_login_link(mailer, member.email, "http://app", now=issued)
    token = _sent_token(mailer)
    too_late = issued + service.LOGIN_LINK_LIFETIME + timedelta(seconds=1)
    with pytest.raises(service.LoginLinkRejected):
        service.redeem_login_link(token, now=too_late)


def test_a_forged_token_is_rejected(client):
    assert client.post_json("/api/auth/redeem", {"token": "not-a-real-token"}).status_code == 400


def test_me_without_a_session_is_unauthorised(client):
    assert client.get("/api/auth/me").status_code == 401


def test_sign_out_ends_the_session(client, mailer):
    member = make_member()
    client.post_json("/api/auth/request-link", {"email": member.email})
    client.post_json("/api/auth/redeem", {"token": _sent_token(mailer)})
    assert client.get("/api/auth/me").status_code == 200
    assert client.post("/api/auth/sign-out").status_code == 204
    assert client.get("/api/auth/me").status_code == 401


def test_writes_need_the_csrf_token_once_signed_in(mailer):
    """The browser must echo the CSRF cookie as a header on every write."""
    from tests.conftest import ApiClient

    strict = ApiClient(enforce_csrf_checks=True)
    member = make_member()
    strict.sign_in(member)
    assert strict.get("/api/auth/me").status_code == 200
    refused = strict.post_json("/api/auth/set-password", {"password": "longenough123"})
    assert refused.status_code == 403
    token = strict.cookies["csrftoken"].value
    accepted = strict.post_json(
        "/api/auth/set-password", {"password": "longenough123"}, HTTP_X_CSRFTOKEN=token
    )
    assert accepted.status_code == 204, accepted.content
