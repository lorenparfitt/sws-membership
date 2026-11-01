"""Granting and revoking the elevated roles."""

from sws_membership.members.lookup import find_member_by_email
from sws_membership.members.models import Member, MemberRole, MemberRoleAssignment


class UnknownMember(LookupError):
    pass


def grant_role(email: str, role: MemberRole) -> Member:
    member = find_member_by_email(email)
    if member is None:
        raise UnknownMember(email)
    MemberRoleAssignment.objects.get_or_create(member=member, role=role)
    return member


def revoke_role(email: str, role: MemberRole) -> Member:
    member = find_member_by_email(email)
    if member is None:
        raise UnknownMember(email)
    member.roles.filter(role=role).delete()
    return member
