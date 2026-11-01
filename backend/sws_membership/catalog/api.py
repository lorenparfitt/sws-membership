"""The catalog as a member sees it: every active product, priced and judged."""

from datetime import date

from ninja import Query, Router, Schema

from sws_membership import clock
from sws_membership.accounts.auth import member_auth
from sws_membership.catalog.eligibility import evaluate, evaluate_basket, would_grant
from sws_membership.catalog.facts import facts_for
from sws_membership.catalog.models import CURRENCY, products_for_sale

router = Router(tags=["catalog"])


class PriceView(Schema):
    id: int
    label: str
    amount_cents: int
    currency: str = CURRENCY
    members_only: bool
    ends_at: date | None


class ProductView(Schema):
    id: int
    name: str
    description: str
    season_year: int
    grants: list[str]
    price: PriceView | None
    purchasable: bool
    locked_because: list[str]


def catalog_for(member, today: date, basket: tuple[int, ...] = ()) -> list[ProductView]:
    """Every active product as one member sees it: price today, purchasable, why not.

    With a basket, what its purchasable products would grant counts as held,
    so adding the membership unlocks the pass next to it before any payment.
    """
    facts = facts_for(member)
    products = list(products_for_sale())
    specs = {p.id: p.spec() for p in products}
    chosen = [specs[p.id] for p in products if p.id in basket]
    basket_results = evaluate_basket(chosen, facts, today)
    held = {s.id: would_grant(s) for s in chosen if basket_results[s.id].purchasable}
    views = []
    for product in products:
        spec = specs[product.id]
        others = tuple(e for pid, grants in held.items() if pid != product.id for e in grants)
        result = evaluate(spec, facts.holding(others), today)
        if result.price is None and not spec.prices:
            continue
        views.append(
            ProductView(
                id=product.id,
                name=product.name,
                description=product.description,
                season_year=product.season_year,
                grants=sorted({grant.kind.value for grant in spec.grants}),
                price=PriceView(
                    id=result.price.id,
                    label=result.price.label,
                    amount_cents=result.price.amount_cents,
                    members_only=result.price.members_only,
                    ends_at=result.price.ends_at,
                )
                if result.price
                else None,
                purchasable=result.purchasable,
                locked_because=list(result.failures)
                if result.price
                else [*result.failures, "not on sale today"],
            )
        )
    return views


@router.get("", auth=member_auth, response=list[ProductView])
def catalog(request, basket: list[int] = Query(default=[])):  # noqa: B008
    """Products on sale to the signed-in member today, with prices and why any is locked;
    basket ids count as held.
    """
    return catalog_for(request.auth, clock.today(), tuple(basket))
