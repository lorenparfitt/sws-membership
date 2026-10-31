"""Editing the catalog, and rolling a season forward.

Products, prices, grants and rules are rows the admin edits here. Rule
parameters are validated against the closed list of rule kinds so a bad
row can never reach the engine. Rollover copies one season's products to
the next with every date moved a year, as drafts the admin then adjusts.
"""

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from sws_membership.catalog.models import (
    EligibilityRule,
    EntitlementGrant,
    Price,
    Product,
    RuleKind,
)
from sws_membership.entitlements.models import EntitlementKind


class CatalogRejected(ValueError):
    pass


RULE_PARAMETERS: dict[RuleKind, dict[str, str]] = {
    RuleKind.REQUIRES_ACTIVE_ENTITLEMENT: {
        "kind": "entitlement kind",
        "season_year": "optional season year",
    },
    RuleKind.REQUIRES_CURRENT_WAIVER: {},
    RuleKind.PROFILE_COMPLETE: {},
    RuleKind.AGE_AT_LEAST: {"years": "minimum age in years"},
    RuleKind.AGE_AT_MOST: {"years": "maximum age in years"},
    RuleKind.ONE_PER_MEMBER_PER_SEASON: {},
}


def validate_rule_parameters(kind: RuleKind, parameters: dict) -> dict:
    allowed = RULE_PARAMETERS[kind]
    unknown = set(parameters) - set(allowed)
    if unknown:
        raise CatalogRejected(f"{kind.value} does not take {', '.join(sorted(unknown))}")
    clean: dict = {}
    if kind is RuleKind.REQUIRES_ACTIVE_ENTITLEMENT:
        try:
            clean["kind"] = EntitlementKind(parameters.get("kind")).value
        except ValueError:
            raise CatalogRejected("requires_active_entitlement needs an entitlement kind") from None
        if parameters.get("season_year") not in (None, ""):
            clean["season_year"] = int(parameters["season_year"])
    if kind in (RuleKind.AGE_AT_LEAST, RuleKind.AGE_AT_MOST):
        try:
            clean["years"] = int(parameters["years"])
        except (KeyError, TypeError, ValueError):
            raise CatalogRejected(f"{kind.value} needs years") from None
        if not 0 <= clean["years"] <= 120:
            raise CatalogRejected("years must be between 0 and 120")
    return clean


def load_product(session: Session, product_id: int) -> Product:
    product = session.get(
        Product,
        product_id,
        options=[
            selectinload(Product.prices),
            selectinload(Product.grants),
            selectinload(Product.rules),
        ],
    )
    if product is None:
        raise LookupError(product_id)
    return product


def all_products(session: Session, season_year: int | None = None) -> list[Product]:
    query = select(Product).options(
        selectinload(Product.prices), selectinload(Product.grants), selectinload(Product.rules)
    )
    if season_year is not None:
        query = query.where(Product.season_year == season_year)
    return list(
        session.scalars(
            query.order_by(Product.season_year.desc(), Product.sort_order, Product.name)
        )
    )


@dataclass(frozen=True)
class ProductInput:
    name: str
    description: str
    season_year: int
    sort_order: int
    active: bool


def create_product(session: Session, given: ProductInput) -> Product:
    if not given.name.strip():
        raise CatalogRejected("name is required")
    product = Product(
        name=given.name.strip(),
        description=given.description,
        season_year=given.season_year,
        sort_order=given.sort_order,
        active=given.active,
    )
    session.add(product)
    session.flush()
    return product


def update_product(session: Session, product: Product, given: ProductInput) -> Product:
    if not given.name.strip():
        raise CatalogRejected("name is required")
    product.name = given.name.strip()
    product.description = given.description
    product.season_year = given.season_year
    product.sort_order = given.sort_order
    product.active = given.active
    session.flush()
    return product


@dataclass(frozen=True)
class PriceInput:
    label: str
    amount_cents: int
    starts_at: date
    ends_at: date | None
    members_only: bool


def add_price(session: Session, product: Product, given: PriceInput) -> Price:
    if given.amount_cents < 0:
        raise CatalogRejected("amount cannot be negative")
    if given.ends_at is not None and given.ends_at < given.starts_at:
        raise CatalogRejected("price ends before it starts")
    price = Price(**given.__dict__)
    product.prices.append(price)
    session.flush()
    return price


def remove_price(session: Session, product: Product, price_id: int) -> None:
    price = next((p for p in product.prices if p.id == price_id), None)
    if price is None:
        raise LookupError(price_id)
    if price.order_lines_exist(session):
        raise CatalogRejected("that price has been sold; end it instead of deleting it")
    product.prices.remove(price)
    session.flush()


@dataclass(frozen=True)
class GrantInput:
    kind: EntitlementKind
    valid_from: date
    valid_to: date
    visit_count: int | None


def add_grant(session: Session, product: Product, given: GrantInput) -> EntitlementGrant:
    if given.valid_to < given.valid_from:
        raise CatalogRejected("grant ends before it starts")
    if (
        given.kind in (EntitlementKind.DAY_VISITS, EntitlementKind.SHUTTLE_ACCESS)
        and not given.visit_count
    ):
        raise CatalogRejected(f"{given.kind.value} needs a visit count")
    grant = EntitlementGrant(**given.__dict__)
    product.grants.append(grant)
    session.flush()
    return grant


def remove_grant(session: Session, product: Product, grant_id: int) -> None:
    grant = next((g for g in product.grants if g.id == grant_id), None)
    if grant is None:
        raise LookupError(grant_id)
    product.grants.remove(grant)
    session.flush()


def add_rule(
    session: Session, product: Product, kind: RuleKind, parameters: dict, message: str
) -> EligibilityRule:
    if not message.strip():
        raise CatalogRejected("a failure message is required")
    rule = EligibilityRule(
        kind=kind,
        parameters=validate_rule_parameters(kind, parameters),
        failure_message=message.strip(),
    )
    product.rules.append(rule)
    session.flush()
    return rule


def remove_rule(session: Session, product: Product, rule_id: int) -> None:
    rule = next((r for r in product.rules if r.id == rule_id), None)
    if rule is None:
        raise LookupError(rule_id)
    product.rules.remove(rule)
    session.flush()


def _shift(day: date | None, years: int) -> date | None:
    if day is None:
        return None
    try:
        return day.replace(year=day.year + years)
    except ValueError:  # 29 February
        return day.replace(year=day.year + years, day=28)


def rollover_season(session: Session, from_year: int, to_year: int) -> list[Product]:
    """Copy every product of one season to another, dates and names moved along.

    The copies are created inactive so nothing goes on sale until the admin
    has checked prices. A product whose name already exists in the target
    season is skipped, so running twice adds nothing.
    """
    if to_year <= from_year:
        raise CatalogRejected("the target season must be later")
    years = to_year - from_year
    existing = {p.name for p in all_products(session, to_year)}
    created: list[Product] = []
    for source in all_products(session, from_year):
        name = source.name.replace(str(from_year), str(to_year))
        if name in existing:
            continue
        copy = Product(
            name=name,
            description=source.description.replace(str(from_year), str(to_year)),
            season_year=to_year,
            sort_order=source.sort_order,
            active=False,
            prices=[
                Price(
                    label=p.label,
                    amount_cents=p.amount_cents,
                    starts_at=_shift(p.starts_at, years),
                    ends_at=_shift(p.ends_at, years),
                    members_only=p.members_only,
                )
                for p in source.prices
            ],
            grants=[
                EntitlementGrant(
                    kind=g.kind,
                    valid_from=_shift(g.valid_from, years),
                    valid_to=_shift(g.valid_to, years),
                    visit_count=g.visit_count,
                )
                for g in source.grants
            ],
            rules=[
                EligibilityRule(
                    kind=r.kind,
                    parameters={
                        **r.parameters,
                        **({"season_year": to_year} if "season_year" in r.parameters else {}),
                    },
                    failure_message=r.failure_message.replace(str(from_year), str(to_year)),
                )
                for r in source.rules
            ],
        )
        session.add(copy)
        created.append(copy)
    session.flush()
    return created
