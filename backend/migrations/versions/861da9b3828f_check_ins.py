"""check-ins

Revision ID: 861da9b3828f
Revises: 6c45c02813af
Create Date: 2026-10-31 05:08:07.521380

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "861da9b3828f"
down_revision: str | Sequence[str] | None = "6c45c02813af"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "check_ins",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("member_id", sa.Integer(), nullable=False),
        sa.Column("entitlement_id", sa.Integer(), nullable=False),
        sa.Column("station", sa.Enum("spit", "shuttle", name="station"), nullable=False),
        sa.Column("on_day", sa.Date(), nullable=False),
        sa.Column(
            "checked_in_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("checked_in_by_member_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["checked_in_by_member_id"],
            ["members.id"],
        ),
        sa.ForeignKeyConstraint(
            ["entitlement_id"],
            ["entitlements.id"],
        ),
        sa.ForeignKeyConstraint(["member_id"], ["members.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_check_ins_member_id"), "check_ins", ["member_id"], unique=False)
    op.create_index(op.f("ix_check_ins_on_day"), "check_ins", ["on_day"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_check_ins_on_day"), table_name="check_ins")
    op.drop_index(op.f("ix_check_ins_member_id"), table_name="check_ins")
    op.drop_table("check_ins")
    sa.Enum(name="station").drop(op.get_bind())
