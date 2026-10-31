"""Request-scoped dependencies: the database session, the signed-in member, roles."""

from collections.abc import Callable, Iterator
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from sws_membership.auth.service import resolve_session
from sws_membership.database import SessionLocal
from sws_membership.mail.mailer import Mailer
from sws_membership.members.models import Member, MemberRole
from sws_membership.storage.objects import ObjectStorage

SESSION_COOKIE = "sws_session"


def get_database_session() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session
        session.commit()


def get_mailer(request: Request) -> Mailer:
    return request.app.state.mailer


def get_storage(request: Request) -> ObjectStorage:
    return request.app.state.storage


DatabaseSession = Annotated[Session, Depends(get_database_session)]
MailerDependency = Annotated[Mailer, Depends(get_mailer)]
StorageDependency = Annotated[ObjectStorage, Depends(get_storage)]
SessionCookie = Annotated[str | None, Cookie(alias=SESSION_COOKIE)]


def current_member(session: DatabaseSession, session_token: SessionCookie = None) -> Member:
    member = resolve_session(session, session_token) if session_token else None
    if member is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "sign in required")
    return member


CurrentMember = Annotated[Member, Depends(current_member)]


def require_role(role: MemberRole) -> Callable[[Member], Member]:
    def check(member: CurrentMember) -> Member:
        if not member.has_role(role) and not member.has_role(MemberRole.ADMIN):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"{role.value} role required")
        return member

    return check
