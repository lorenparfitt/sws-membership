"""catalog and entitlements

Revision ID: 0b35476b1b07
Revises: a28fd3dacc6b
Create Date: 2026-10-30 15:40:19.444776

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0b35476b1b07"
down_revision: str | Sequence[str] | None = "a28fd3dacc6b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


ENTITLEMENT_KIND = postgresql.ENUM(
    "membership", "season_access", "day_visits", "shuttle_access", name="entitlement_kind"
)
RULE_KIND = postgresql.ENUM(
    "requires_active_entitlement",
    "age_at_least",
    "age_at_most",
    "one_per_member_per_season",
    name="rule_kind",
)


def upgrade() -> None:
    # The enum types are shared by several tables, so they are created once
    # here and the tables reference them without creating them again.
    ENTITLEMENT_KIND.create(op.get_bind())
    RULE_KIND.create(op.get_bind())
    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("season_year", sa.Integer(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_products_season_year"), "products", ["season_year"], unique=False)
    op.create_table(
        "eligibility_rules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("kind", postgresql.ENUM(name="rule_kind", create_type=False), nullable=False),
        sa.Column("parameters", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("failure_message", sa.String(length=200), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_eligibility_rules_product_id"), "eligibility_rules", ["product_id"], unique=False
    )
    op.create_table(
        "entitlement_grants",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column(
            "kind", postgresql.ENUM(name="entitlement_kind", create_type=False), nullable=False
        ),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=False),
        sa.Column("visit_count", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_entitlement_grants_product_id"), "entitlement_grants", ["product_id"], unique=False
    )
    op.create_table(
        "entitlements",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("member_id", sa.Integer(), nullable=False),
        sa.Column(
            "kind", postgresql.ENUM(name="entitlement_kind", create_type=False), nullable=False
        ),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=False),
        sa.Column("visits_remaining", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["member_id"], ["members.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_entitlements_member_id"), "entitlements", ["member_id"], unique=False)
    op.create_table(
        "prices",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=60), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("starts_at", sa.Date(), nullable=False),
        sa.Column("ends_at", sa.Date(), nullable=True),
        sa.Column("members_only", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_prices_product_id"), "prices", ["product_id"], unique=False)
    # ### end Alembic commands ###


def downgrade() -> None:
    op.drop_index(op.f("ix_prices_product_id"), table_name="prices")
    op.drop_table("prices")
    op.drop_index(op.f("ix_entitlements_member_id"), table_name="entitlements")
    op.drop_table("entitlements")
    op.drop_index(op.f("ix_entitlement_grants_product_id"), table_name="entitlement_grants")
    op.drop_table("entitlement_grants")
    op.drop_index(op.f("ix_eligibility_rules_product_id"), table_name="eligibility_rules")
    op.drop_table("eligibility_rules")
    op.drop_index(op.f("ix_products_season_year"), table_name="products")
    op.drop_table("products")
    RULE_KIND.drop(op.get_bind())
    ENTITLEMENT_KIND.drop(op.get_bind())
