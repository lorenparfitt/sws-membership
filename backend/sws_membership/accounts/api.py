"""HTTP surface of sign-in."""

from django.conf import settings
from django.contrib.auth import login, logout, update_session_auth_hash
from ninja import Router, Schema, Status
from ninja.errors import HttpError
from pydantic import EmailStr

from sws_membership.accounts import passwords, service
from sws_membership.accounts.auth import member_auth
from sws_membership.members.models import Member
from sws_membership.wiring import wiring

router = Router(tags=["auth"])


class LinkRequest(Schema):
    email: EmailStr


class Redemption(Schema):
    token: str


class PasswordSignIn(Schema):
    email: EmailStr
    password: str


class NewPassword(Schema):
    password: str


class MemberView(Schema):
    id: int
    member_number: int
    first_name: str
    last_name: str
    email: str
    roles: list[str]
    has_password: bool

    @classmethod
    def of(cls, member: Member) -> "MemberView":
        return cls(
            id=member.id,
            member_number=member.member_number,
            first_name=member.first_name,
            last_name=member.last_name,
            email=member.email,
            roles=member.role_values(),
            has_password=member.has_password,
        )


@router.post("/request-link", auth=None, response={202: dict})
def request_link(request, body: LinkRequest):
    service.request_login_link(wiring.mailer, body.email, settings.SWS_FRONTEND_BASE_URL)
    return Status(202, {"status": "if that address belongs to a member, a link is on its way"})


def _start_session(request, member: Member) -> MemberView:
    login(request, member, backend="django.contrib.auth.backends.ModelBackend")
    return MemberView.of(member)


@router.post("/redeem", auth=None, response=MemberView)
def redeem(request, body: Redemption):
    try:
        member = service.redeem_login_link(body.token)
    except service.LoginLinkRejected:
        raise HttpError(400, "that sign-in link is not valid")
    return _start_session(request, member)


@router.post("/password", auth=None, response=MemberView)
def sign_in_with_password(request, body: PasswordSignIn):
    member = passwords.authenticate(request, body.email, body.password)
    if member is None:
        raise HttpError(401, "email or password not recognised")
    return _start_session(request, member)


@router.post("/set-password", auth=member_auth, response={204: None})
def set_password(request, body: NewPassword):
    try:
        passwords.set_password(request.auth, body.password)
    except passwords.WeakPassword as why:
        raise HttpError(400, f"password too short: {why}")
    # A password change rotates the session hash; keep this session alive.
    update_session_auth_hash(request, request.auth)
    return Status(204, None)


@router.get("/me", auth=member_auth, response=MemberView)
def me(request):
    return MemberView.of(request.auth)


@router.post("/sign-out", auth=None, response={204: None})
def sign_out(request):
    logout(request)
    return Status(204, None)
