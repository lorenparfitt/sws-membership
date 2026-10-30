"""members and member numbers

Revision ID: 3160a74b0218
Revises:
Create Date: 2026-10-30 14:56:44.007443

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "3160a74b0218"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Numbers for new members. The WellnessLiving import moves it past the
    # highest imported number before any new member is created.
    op.execute(sa.schema.CreateSequence(sa.Sequence("member_number_seq")))
    op.create_table(
        "members",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("member_number", sa.BigInteger(), nullable=False),
        sa.Column("first_name", sa.String(length=100), nullable=False),
        sa.Column("last_name", sa.String(length=100), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("phone", sa.String(length=40), nullable=True),
        sa.Column("date_of_birth", sa.Date(), nullable=True),
        sa.Column("photo_key", sa.String(length=200), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("member_number"),
        sa.CheckConstraint("member_number > 0", name="members_member_number_positive"),
    )
    op.create_table(
        "member_roles",
        sa.Column("member_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.Enum("staff", "admin", name="member_role"), nullable=False),
        sa.ForeignKeyConstraint(["member_id"], ["members.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("member_id", "role"),
    )


def downgrade() -> None:
    op.drop_table("member_roles")
    sa.Enum(name="member_role").drop(op.get_bind())
    op.drop_table("members")
    op.execute(sa.schema.DropSequence(sa.Sequence("member_number_seq")))
