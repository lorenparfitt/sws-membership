"""The catalog as a member sees it: every active product, priced and judged."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from sws_membership.auth.dependencies import CurrentMember, DatabaseSession
from sws_membership.catalog.eligibility import evaluate, evaluate_basket, would_grant
from sws_membership.catalog.facts import facts_for
from sws_membership.catalog.models import CURRENCY, Product

router = APIRouter(prefix="/api/catalog", tags=["catalog"])


def current_day() -> date:
    """Today, as a dependency so tests can pin the calendar."""
    return date.today()


CurrentDay = Annotated[date, Depends(current_day)]


class PriceView(BaseModel):
    id: int
    label: str
    amount_cents: int
    currency: str = CURRENCY
    members_only: bool
    ends_at: date | None


class ProductView(BaseModel):
    id: int
    name: str
    description: str
    season_year: int
    grants: list[str]
    price: PriceView | None
    purchasable: bool
    locked_because: list[str]


def catalog_for(session, member, today: date, basket: tuple[int, ...] = ()) -> list[ProductView]:
    """Every active product as one member sees it: price today, purchasable, why not.

    With a basket, what its purchasable products would grant counts as held,
    so adding the membership unlocks the pass next to it before any payment.
    """
    facts = facts_for(session, member)
    products = session.scalars(
        select(Product)
        .where(Product.active.is_(True))
        .order_by(Product.sort_order, Product.name)
        .options(
            selectinload(Product.prices), selectinload(Product.grants), selectinload(Product.rules)
        )
    ).all()
    chosen = [p for p in products if p.id in basket]
    basket_results = evaluate_basket(chosen, facts, today)
    held = {p.id: would_grant(p) for p in chosen if basket_results[p.id].purchasable}
    views = []
    for product in products:
        others = tuple(e for pid, grants in held.items() if pid != product.id for e in grants)
        result = evaluate(product, facts.holding(others), today)
        if result.price is None and not product.prices:
            continue
        views.append(
            ProductView(
                id=product.id,
                name=product.name,
                description=product.description,
                season_year=product.season_year,
                grants=sorted({grant.kind.value for grant in product.grants}),
                price=PriceView.model_validate(result.price, from_attributes=True)
                if result.price
                else None,
                purchasable=result.purchasable,
                locked_because=list(result.failures)
                if result.price
                else [*result.failures, "not on sale today"],
            )
        )
    return views


@router.get("")
def catalog(
    session: DatabaseSession,
    member: CurrentMember,
    today: CurrentDay,
    basket: Annotated[list[int] | None, Query()] = None,
) -> list[ProductView]:
    return catalog_for(session, member, today, tuple(basket or ()))
