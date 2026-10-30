"""Products, their prices, the entitlements they grant, and the rules that gate them.

The split follows the shape Stripe settled on: a Product is one sellable
thing, a Price is an amount with a window, and what the purchase confers is
separate from both. Rules are data rows that pick a rule kind from the
closed list in eligibility.py and carry its parameters.
"""

import enum
from datetime import date

from sqlalchemy import Boolean, Date, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from sws_membership.database import Base
from sws_membership.entitlements.models import EntitlementKind, entitlement_kind_column

CURRENCY = "CAD"


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    season_year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    prices: Mapped[list["Price"]] = relationship(
        back_populates="product", cascade="all, delete-orphan", order_by="Price.starts_at"
    )
    grants: Mapped[list["EntitlementGrant"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    rules: Mapped[list["EligibilityRule"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )

    def price_on(self, day: date, member_prices: bool) -> "Price | None":
        """The price in force on a day; the members-only one wins when allowed."""
        candidates = [
            price
            for price in self.prices
            if price.is_on_sale(day) and (member_prices or not price.members_only)
        ]
        candidates.sort(key=lambda price: (not price.members_only, price.amount_cents))
        return candidates[0] if candidates else None


class Price(Base):
    __tablename__ = "prices"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    label: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    starts_at: Mapped[date] = mapped_column(Date, nullable=False)
    ends_at: Mapped[date | None] = mapped_column(Date)
    members_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    product: Mapped[Product] = relationship(back_populates="prices")

    def is_on_sale(self, day: date) -> bool:
        return self.starts_at <= day and (self.ends_at is None or day <= self.ends_at)


class EntitlementGrant(Base):
    __tablename__ = "entitlement_grants"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[EntitlementKind] = mapped_column(entitlement_kind_column(), nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date] = mapped_column(Date, nullable=False)
    visit_count: Mapped[int | None] = mapped_column(Integer)

    product: Mapped[Product] = relationship(back_populates="grants")


class RuleKind(enum.Enum):
    """The closed list of conditions a product can be gated behind."""

    REQUIRES_ACTIVE_ENTITLEMENT = "requires_active_entitlement"
    AGE_AT_LEAST = "age_at_least"
    AGE_AT_MOST = "age_at_most"
    ONE_PER_MEMBER_PER_SEASON = "one_per_member_per_season"


class EligibilityRule(Base):
    __tablename__ = "eligibility_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[RuleKind] = mapped_column(
        Enum(RuleKind, name="rule_kind", values_callable=lambda kinds: [k.value for k in kinds]),
        nullable=False,
    )
    parameters: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    failure_message: Mapped[str] = mapped_column(String(200), nullable=False)

    product: Mapped[Product] = relationship(back_populates="rules")
