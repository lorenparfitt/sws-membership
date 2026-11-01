"""Who may call a route: a signed-in member, staff, or an admin.

Session based, so the CSRF token is checked on writes. Admin implies staff.
A missing session is 401; a session without the role is 403.
"""

from ninja.errors import HttpError
from ninja.security import SessionAuth

from sws_membership.members.models import MemberRole


class MemberAuth(SessionAuth):
    def authenticate(self, request, key):
        if not request.user.is_authenticated:
            return None
        return request.user


class RoleAuth(MemberAuth):
    def __init__(self, role: MemberRole) -> None:
        super().__init__()
        self.role = role

    def authenticate(self, request, key):
        member = super().authenticate(request, key)
        if member is None:
            return None
        if not (member.has_role(self.role) or member.has_role(MemberRole.ADMIN)):
            raise HttpError(403, f"{self.role.value} role required")
        return member


member_auth = MemberAuth()
staff_auth = RoleAuth(MemberRole.STAFF)
admin_auth = RoleAuth(MemberRole.ADMIN)
