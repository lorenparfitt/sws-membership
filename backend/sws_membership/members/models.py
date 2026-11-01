"""Member rows, the elevated roles a member may hold, and the sports they ride.

A Member is also the Django user: email signs in, roles decide what the
staff and admin routes allow, and the admin role opens Django's own admin.
"""

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.db import models


class MemberRole(models.TextChoices):
    """Roles beyond plain membership. Every Member row is a member already."""

    STAFF = "staff", "Staff"
    ADMIN = "admin", "Admin"


class Sport(models.TextChoices):
    """What a member rides. A closed list; printed on the card."""

    KITE_TWIN_TIP = "kite_twin_tip", "Kite, twin tip"
    KITE_FOIL = "kite_foil", "Kite, foil"
    KITE_SURFBOARD = "kite_surfboard", "Kite, surfboard"
    WING = "wing", "Wing"
    WINDSURF = "windsurf", "Windsurf"
    OTHER = "other", "Other"


SPORT_LABELS = {Sport(value): label for value, label in Sport.choices}


def normalise_email(email: str) -> str:
    return email.strip().lower()


class MemberManager(BaseUserManager):
    def get_by_natural_key(self, email):
        return self.get(email=normalise_email(email))

    def create_user(self, email, password=None, **fields):
        from sws_membership.members.member_numbers import allocate_member_number

        fields.setdefault("member_number", allocate_member_number())
        member = self.model(email=normalise_email(email), **fields)
        if password:
            member.set_password(password)
        else:
            member.set_unusable_password()
        member.save()
        return member

    def create_superuser(self, email, password=None, **fields):
        member = self.create_user(email, password, **fields)
        MemberRoleAssignment.objects.create(member=member, role=MemberRole.ADMIN)
        return member


class Member(AbstractBaseUser):
    # The number encoded in the card barcode: a positive integer, so a scan
    # that is zero padded or carries a prefix normalises to the same value.
    member_number = models.BigIntegerField(unique=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(max_length=254, unique=True)
    phone = models.CharField(max_length=40, null=True, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    photo_key = models.CharField(max_length=200, null=True, blank=True)
    address_line_1 = models.CharField(max_length=200, null=True, blank=True)
    address_line_2 = models.CharField(max_length=200, null=True, blank=True)
    city = models.CharField(max_length=100, null=True, blank=True)
    province = models.CharField(max_length=100, null=True, blank=True)
    postal_code = models.CharField(max_length=20, null=True, blank=True)
    country = models.CharField(max_length=2, default="CA")
    # Django's auth needs it; a member is never deactivated today.
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]
    objects = MemberManager()

    class Meta:
        db_table = "members"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(member_number__gt=0), name="members_member_number_positive"
            )
        ]

    def __str__(self) -> str:
        return f"{self.member_number} {self.first_name} {self.last_name}"

    # --- roles ---------------------------------------------------------------

    def role_values(self) -> list[str]:
        return sorted(assignment.role for assignment in self.roles.all())

    def has_role(self, role: MemberRole) -> bool:
        return any(assignment.role == role for assignment in self.roles.all())

    # Django's admin site is for the society's admins.
    @property
    def is_staff(self) -> bool:
        return self.has_role(MemberRole.ADMIN)

    @property
    def is_superuser(self) -> bool:
        return self.has_role(MemberRole.ADMIN)

    def has_perm(self, perm, obj=None) -> bool:
        return self.is_superuser

    def has_module_perms(self, app_label) -> bool:
        return self.is_superuser

    # --- profile -------------------------------------------------------------

    @property
    def has_password(self) -> bool:
        return bool(self.password) and self.has_usable_password()

    def sport_values(self) -> list[str]:
        return sorted(row.sport for row in self.sports.all())

    def missing_profile_fields(self) -> list[str]:
        """What the society requires before a pass is sold, in plain words."""
        missing = []
        if not self.photo_key:
            missing.append("photo")
        if self.date_of_birth is None:
            missing.append("date of birth")
        if not (self.address_line_1 and self.city and self.province and self.postal_code):
            missing.append("address")
        if not self.sports.exists():
            missing.append("sports")
        return missing

    @property
    def profile_complete(self) -> bool:
        return not self.missing_profile_fields()


class MemberRoleAssignment(models.Model):
    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="roles")
    role = models.CharField(max_length=20, choices=MemberRole.choices)

    class Meta:
        db_table = "member_roles"
        constraints = [models.UniqueConstraint(fields=["member", "role"], name="member_roles_once")]

    def __str__(self) -> str:
        return f"{self.member_id}:{self.role}"


class MemberSport(models.Model):
    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="sports")
    sport = models.CharField(max_length=20, choices=Sport.choices)

    class Meta:
        db_table = "member_sports"
        constraints = [
            models.UniqueConstraint(fields=["member", "sport"], name="member_sports_once")
        ]

    def __str__(self) -> str:
        return f"{self.member_id}:{self.sport}"
