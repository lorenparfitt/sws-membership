"""HTTP surface of sign-in."""

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, EmailStr

from sws_membership.auth import passwords, service
from sws_membership.auth.dependencies import (
    SESSION_COOKIE,
    CurrentMember,
    DatabaseSession,
    MailerDependency,
    SessionCookie,
)
from sws_membership.members.models import Member
from sws_membership.settings import settings

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LinkRequest(BaseModel):
    email: EmailStr


class Redemption(BaseModel):
    token: str


class PasswordSignIn(BaseModel):
    email: EmailStr
    password: str


class NewPassword(BaseModel):
    password: str


class MemberView(BaseModel):
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
            roles=sorted(assignment.role.value for assignment in member.roles),
            has_password=member.password_hash is not None,
        )


@router.post("/request-link", status_code=status.HTTP_202_ACCEPTED)
def request_link(
    body: LinkRequest, session: DatabaseSession, mailer: MailerDependency
) -> dict[str, str]:
    service.request_login_link(session, mailer, body.email, settings.frontend_base_url)
    return {"status": "if that address belongs to a member, a link is on its way"}


def _start_session(session, member: Member, response: Response) -> MemberView:
    token = service.open_session(session, member)
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=int(service.SESSION_LIFETIME.total_seconds()),
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    return MemberView.of(member)


@router.post("/redeem")
def redeem(body: Redemption, session: DatabaseSession, response: Response) -> MemberView:
    try:
        member = service.redeem_login_link(session, body.token)
    except service.LoginLinkRejected:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "that sign-in link is not valid")
    return _start_session(session, member, response)


@router.post("/password")
def sign_in_with_password(
    body: PasswordSignIn, session: DatabaseSession, response: Response
) -> MemberView:
    member = passwords.authenticate(session, body.email, body.password)
    if member is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "email or password not recognised")
    return _start_session(session, member, response)


@router.post("/set-password", status_code=status.HTTP_204_NO_CONTENT)
def set_password(body: NewPassword, session: DatabaseSession, member: CurrentMember) -> None:
    try:
        passwords.set_password(session, member, body.password)
    except passwords.WeakPassword as why:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"password too short: {why}")


@router.get("/me")
def me(member: CurrentMember) -> MemberView:
    return MemberView.of(member)


@router.post("/sign-out", status_code=status.HTTP_204_NO_CONTENT)
def sign_out(
    session: DatabaseSession, response: Response, session_token: SessionCookie = None
) -> None:
    if session_token:
        service.close_session(session, session_token)
    response.delete_cookie(SESSION_COOKIE, path="/")
