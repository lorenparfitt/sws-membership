"""waivers

Revision ID: 6c45c02813af
Revises: 13ace2a56e50
Create Date: 2026-10-31 04:41:30.506738

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6c45c02813af"
down_revision: str | Sequence[str] | None = "13ace2a56e50"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Autogenerate does not see enum members. ADD VALUE cannot run inside the
    # migration transaction on every Postgres version, hence the autocommit block.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE rule_kind ADD VALUE IF NOT EXISTS 'requires_current_waiver'")
    op.create_table(
        "waiver_resets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("reset_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reset_by_member_id", sa.Integer(), nullable=True),
        sa.Column("reason", sa.String(length=300), nullable=False),
        sa.ForeignKeyConstraint(
            ["reset_by_member_id"],
            ["members.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "waiver_templates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body_text", sa.Text(), nullable=False),
        sa.Column("document_hash", sa.String(length=64), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_by_member_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["published_by_member_id"],
            ["members.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("version"),
    )
    op.create_table(
        "waiver_signatures",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("member_id", sa.Integer(), nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=False),
        sa.Column("signed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ip_address", sa.String(length=45), nullable=False),
        sa.Column("signer_name", sa.String(length=200), nullable=False),
        sa.Column("signature_key", sa.String(length=200), nullable=False),
        sa.Column("document_hash", sa.String(length=64), nullable=False),
        sa.Column("guardian_name", sa.String(length=200), nullable=True),
        sa.Column("guardian_signature_key", sa.String(length=200), nullable=True),
        sa.ForeignKeyConstraint(["member_id"], ["members.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["template_id"],
            ["waiver_templates.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_waiver_signatures_member_id"), "waiver_signatures", ["member_id"], unique=False
    )


def downgrade() -> None:
    # Postgres cannot remove a value from an enum type; requires_current_waiver
    # stays in rule_kind until the catalog migration drops the type.
    op.drop_index(op.f("ix_waiver_signatures_member_id"), table_name="waiver_signatures")
    op.drop_table("waiver_signatures")
    op.drop_table("waiver_templates")
    op.drop_table("waiver_resets")
