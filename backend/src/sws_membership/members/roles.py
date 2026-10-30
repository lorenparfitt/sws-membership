"""Granting and revoking the elevated roles."""

from sqlalchemy.orm import Session

from sws_membership.members.lookup import find_member_by_email
from sws_membership.members.models import Member, MemberRole, MemberRoleAssignment


class UnknownMember(LookupError):
    pass


def grant_role(session: Session, email: str, role: MemberRole) -> Member:
    member = find_member_by_email(session, email)
    if member is None:
        raise UnknownMember(email)
    if not member.has_role(role):
        member.roles.append(MemberRoleAssignment(role=role))
        session.flush()
    return member


def revoke_role(session: Session, email: str, role: MemberRole) -> Member:
    member = find_member_by_email(session, email)
    if member is None:
        raise UnknownMember(email)
    member.roles[:] = [assignment for assignment in member.roles if assignment.role != role]
    session.flush()
    return member
