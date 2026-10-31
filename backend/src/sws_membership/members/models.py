"""Member rows and the elevated roles a member may hold."""

import enum
from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, Enum, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from sws_membership.database import Base


class MemberRole(enum.Enum):
    """Roles beyond plain membership. Every Member row is a member already."""

    STAFF = "staff"
    ADMIN = "admin"


class Sport(enum.Enum):
    """What a member rides. A closed list; printed on the card."""

    KITE_TWIN_TIP = "kite_twin_tip"
    KITE_FOIL = "kite_foil"
    KITE_SURFBOARD = "kite_surfboard"
    WING = "wing"
    WINDSURF = "windsurf"
    OTHER = "other"


SPORT_LABELS = {
    Sport.KITE_TWIN_TIP: "Kite, twin tip",
    Sport.KITE_FOIL: "Kite, foil",
    Sport.KITE_SURFBOARD: "Kite, surfboard",
    Sport.WING: "Wing",
    Sport.WINDSURF: "Windsurf",
    Sport.OTHER: "Other",
}


class Member(Base):
    __tablename__ = "members"

    id: Mapped[int] = mapped_column(primary_key=True)
    # The number encoded in the card barcode: a positive integer, so a scan
    # that is zero padded or carries a prefix normalises to the same value.
    member_number: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False)
    phone: Mapped[str | None] = mapped_column(String(40))
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    photo_key: Mapped[str | None] = mapped_column(String(200))
    address_line_1: Mapped[str | None] = mapped_column(String(200))
    address_line_2: Mapped[str | None] = mapped_column(String(200))
    city: Mapped[str | None] = mapped_column(String(100))
    province: Mapped[str | None] = mapped_column(String(100))
    postal_code: Mapped[str | None] = mapped_column(String(20))
    country: Mapped[str] = mapped_column(
        String(2), nullable=False, default="CA", server_default="CA"
    )
    # Null until the member sets one; the emailed link signs in regardless.
    password_hash: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    roles: Mapped[list["MemberRoleAssignment"]] = relationship(
        back_populates="member", cascade="all, delete-orphan"
    )
    sports: Mapped[list["MemberSport"]] = relationship(
        back_populates="member", cascade="all, delete-orphan"
    )

    def has_role(self, role: MemberRole) -> bool:
        return any(assignment.role == role for assignment in self.roles)

    def missing_profile_fields(self) -> list[str]:
        """What the society requires before a pass is sold, in plain words."""
        missing = []
        if not self.photo_key:
            missing.append("photo")
        if self.date_of_birth is None:
            missing.append("date of birth")
        if not (self.address_line_1 and self.city and self.province and self.postal_code):
            missing.append("address")
        if not self.sports:
            missing.append("sports")
        return missing

    @property
    def profile_complete(self) -> bool:
        return not self.missing_profile_fields()


class MemberRoleAssignment(Base):
    __tablename__ = "member_roles"

    member_id: Mapped[int] = mapped_column(
        ForeignKey("members.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[MemberRole] = mapped_column(
        Enum(MemberRole, name="member_role", values_callable=lambda e: [m.value for m in e]),
        primary_key=True,
    )

    member: Mapped[Member] = relationship(back_populates="roles")


class MemberSport(Base):
    __tablename__ = "member_sports"

    member_id: Mapped[int] = mapped_column(
        ForeignKey("members.id", ondelete="CASCADE"), primary_key=True
    )
    sport: Mapped[Sport] = mapped_column(
        Enum(Sport, name="sport", values_callable=lambda e: [m.value for m in e]), primary_key=True
    )

    member: Mapped[Member] = relationship(back_populates="sports")
