import pytest

from sws_membership.accounts import passwords
from sws_membership.members.models import Member
from tests.conftest import make_member

pytestmark = pytest.mark.django_db


def test_set_password_needs_a_session(client):
    assert (
        client.post_json("/api/auth/set-password", {"password": "longenough123"}).status_code == 401
    )


def test_short_passwords_are_refused(client):
    member = make_member("pw@example.com")
    client.sign_in(member)
    assert client.post_json("/api/auth/set-password", {"password": "short"}).status_code == 400
    assert Member.objects.get(id=member.id).has_password is False


def test_password_sign_in_after_setting_one(client):
    member = make_member("pw@example.com")
    client.sign_in(member)
    assert (
        client.post_json(
            "/api/auth/set-password", {"password": "correct horse battery"}
        ).status_code
        == 204
    )
    assert client.get("/api/auth/me").json()["has_password"] is True
    stored = Member.objects.get(id=member.id).password
    assert stored.startswith("argon2") and "correct horse" not in stored

    client.logout()
    signed_in = client.post_json(
        "/api/auth/password", {"email": "PW@example.com", "password": "correct horse battery"}
    )
    assert signed_in.status_code == 200, signed_in.content
    assert signed_in.json()["member_number"] == member.member_number
    assert client.get("/api/auth/me").status_code == 200


def test_wrong_password_unknown_email_and_no_password_all_look_alike(client):
    member = make_member("haspw@example.com")
    passwords.set_password(member, "correct horse battery")
    make_member("nopw@example.com")
    attempts = [
        {"email": "haspw@example.com", "password": "wrong horse battery"},
        {"email": "nobody@example.com", "password": "correct horse battery"},
        {"email": "nopw@example.com", "password": "correct horse battery"},
    ]
    answers = {client.post_json("/api/auth/password", a).content for a in attempts}
    assert len(answers) == 1
    assert client.post_json("/api/auth/password", attempts[0]).status_code == 401
