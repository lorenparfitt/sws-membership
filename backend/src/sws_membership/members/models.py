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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    roles: Mapped[list["MemberRoleAssignment"]] = relationship(
        back_populates="member", cascade="all, delete-orphan"
    )

    def has_role(self, role: MemberRole) -> bool:
        return any(assignment.role == role for assignment in self.roles)


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
