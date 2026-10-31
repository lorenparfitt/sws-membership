"""member profile and card prints

Revision ID: aef11d149278
Revises: 861da9b3828f
Create Date: 2026-10-31 05:32:12.112254

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "aef11d149278"
down_revision: str | Sequence[str] | None = "861da9b3828f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE rule_kind ADD VALUE IF NOT EXISTS 'profile_complete'")
    op.create_table(
        "card_prints",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("member_id", sa.Integer(), nullable=False),
        sa.Column(
            "printed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("printed_by_member_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["member_id"], ["members.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["printed_by_member_id"],
            ["members.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_card_prints_member_id"), "card_prints", ["member_id"], unique=False)
    op.create_table(
        "member_sports",
        sa.Column("member_id", sa.Integer(), nullable=False),
        sa.Column(
            "sport",
            sa.Enum(
                "kite_twin_tip",
                "kite_foil",
                "kite_surfboard",
                "wing",
                "windsurf",
                "other",
                name="sport",
            ),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["member_id"], ["members.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("member_id", "sport"),
    )
    op.add_column("members", sa.Column("address_line_1", sa.String(length=200), nullable=True))
    op.add_column("members", sa.Column("address_line_2", sa.String(length=200), nullable=True))
    op.add_column("members", sa.Column("city", sa.String(length=100), nullable=True))
    op.add_column("members", sa.Column("province", sa.String(length=100), nullable=True))
    op.add_column("members", sa.Column("postal_code", sa.String(length=20), nullable=True))
    op.add_column(
        "members", sa.Column("country", sa.String(length=2), server_default="CA", nullable=False)
    )


def downgrade() -> None:
    # The profile_complete value stays in rule_kind; Postgres cannot drop an enum value.
    op.drop_column("members", "country")
    op.drop_column("members", "postal_code")
    op.drop_column("members", "province")
    op.drop_column("members", "city")
    op.drop_column("members", "address_line_2")
    op.drop_column("members", "address_line_1")
    op.drop_table("member_sports")
    sa.Enum(name="sport").drop(op.get_bind())
    op.drop_index(op.f("ix_card_prints_member_id"), table_name="card_prints")
    op.drop_table("card_prints")
