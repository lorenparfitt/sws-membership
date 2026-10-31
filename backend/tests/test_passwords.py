from sws_membership.auth import passwords, service
from sws_membership.auth.dependencies import SESSION_COOKIE
from sws_membership.members.member_numbers import allocate_member_number
from sws_membership.members.models import Member


def _member(session, email="pw@example.com") -> Member:
    member = Member(
        member_number=allocate_member_number(session),
        first_name="Pass",
        last_name="Word",
        email=email,
    )
    session.add(member)
    session.flush()
    return member


def test_set_password_needs_a_session(client):
    assert (
        client.post("/api/auth/set-password", json={"password": "longenough123"}).status_code == 401
    )


def test_short_passwords_are_refused(session, client):
    member = _member(session)
    client.cookies.set(SESSION_COOKIE, service.open_session(session, member))
    assert client.post("/api/auth/set-password", json={"password": "short"}).status_code == 400
    assert member.password_hash is None


def test_password_sign_in_after_setting_one(session, client):
    member = _member(session)
    client.cookies.set(SESSION_COOKIE, service.open_session(session, member))
    assert (
        client.post(
            "/api/auth/set-password", json={"password": "correct horse battery"}
        ).status_code
        == 204
    )
    assert client.get("/api/auth/me").json()["has_password"] is True
    assert member.password_hash is not None and "correct horse" not in member.password_hash

    client.cookies.clear()
    signed_in = client.post(
        "/api/auth/password", json={"email": "PW@example.com", "password": "correct horse battery"}
    )
    assert signed_in.status_code == 200
    assert signed_in.json()["member_number"] == member.member_number
    assert client.get("/api/auth/me").status_code == 200


def test_wrong_password_unknown_email_and_no_password_all_look_alike(session, client):
    member = _member(session, "haspw@example.com")
    passwords.set_password(session, member, "correct horse battery")
    _member(session, "nopw@example.com")
    attempts = [
        {"email": "haspw@example.com", "password": "wrong horse battery"},
        {"email": "nobody@example.com", "password": "correct horse battery"},
        {"email": "nopw@example.com", "password": "correct horse battery"},
    ]
    answers = {client.post("/api/auth/password", json=a).text for a in attempts}
    assert len(answers) == 1
    assert client.post("/api/auth/password", json=attempts[0]).status_code == 401
