"""Editing the catalog, and rolling a season forward.

Products, prices, grants and rules are rows the admin edits here. Rule
parameters are validated against the closed list of rule kinds so a bad
row can never reach the engine. Rollover copies one season's products to
the next with every date moved a year, as drafts the admin then adjusts.
"""

from dataclasses import dataclass
from datetime import date

from django.db import transaction

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
    if kind == RuleKind.REQUIRES_ACTIVE_ENTITLEMENT:
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


def _with_rows():
    return Product.objects.prefetch_related("prices", "grants", "rules")


def load_product(product_id: int) -> Product:
    product = _with_rows().filter(id=product_id).first()
    if product is None:
        raise LookupError(product_id)
    return product


def all_products(season_year: int | None = None) -> list[Product]:
    query = _with_rows()
    if season_year is not None:
        query = query.filter(season_year=season_year)
    return list(query.order_by("-season_year", "sort_order", "name"))


@dataclass(frozen=True)
class ProductInput:
    name: str
    description: str
    season_year: int
    sort_order: int
    active: bool


def create_product(given: ProductInput) -> Product:
    if not given.name.strip():
        raise CatalogRejected("name is required")
    return Product.objects.create(
        name=given.name.strip(),
        description=given.description,
        season_year=given.season_year,
        sort_order=given.sort_order,
        active=given.active,
    )


def update_product(product: Product, given: ProductInput) -> Product:
    if not given.name.strip():
        raise CatalogRejected("name is required")
    product.name = given.name.strip()
    product.description = given.description
    product.season_year = given.season_year
    product.sort_order = given.sort_order
    product.active = given.active
    product.save()
    return product


@dataclass(frozen=True)
class PriceInput:
    label: str
    amount_cents: int
    starts_at: date
    ends_at: date | None
    members_only: bool


def add_price(product: Product, given: PriceInput) -> Price:
    if given.amount_cents < 0:
        raise CatalogRejected("amount cannot be negative")
    if given.ends_at is not None and given.ends_at < given.starts_at:
        raise CatalogRejected("price ends before it starts")
    return Price.objects.create(product=product, **given.__dict__)


def remove_price(product: Product, price_id: int) -> None:
    price = product.prices.filter(id=price_id).first()
    if price is None:
        raise LookupError(price_id)
    if price.order_lines_exist():
        raise CatalogRejected("that price has been sold; end it instead of deleting it")
    price.delete()


@dataclass(frozen=True)
class GrantInput:
    kind: EntitlementKind
    valid_from: date
    valid_to: date
    visit_count: int | None


def add_grant(product: Product, given: GrantInput) -> EntitlementGrant:
    if given.valid_to < given.valid_from:
        raise CatalogRejected("grant ends before it starts")
    if (
        given.kind in (EntitlementKind.DAY_VISITS, EntitlementKind.SHUTTLE_ACCESS)
        and not given.visit_count
    ):
        raise CatalogRejected(f"{given.kind.value} needs a visit count")
    return EntitlementGrant.objects.create(product=product, **given.__dict__)


def remove_grant(product: Product, grant_id: int) -> None:
    deleted, _ = product.grants.filter(id=grant_id).delete()
    if not deleted:
        raise LookupError(grant_id)


def add_rule(product: Product, kind: RuleKind, parameters: dict, message: str) -> EligibilityRule:
    if not message.strip():
        raise CatalogRejected("a failure message is required")
    return EligibilityRule.objects.create(
        product=product,
        kind=kind,
        parameters=validate_rule_parameters(kind, parameters),
        failure_message=message.strip(),
    )


def remove_rule(product: Product, rule_id: int) -> None:
    deleted, _ = product.rules.filter(id=rule_id).delete()
    if not deleted:
        raise LookupError(rule_id)


def _shift(day: date | None, years: int) -> date | None:
    if day is None:
        return None
    try:
        return day.replace(year=day.year + years)
    except ValueError:  # 29 February
        return day.replace(year=day.year + years, day=28)


@transaction.atomic
def rollover_season(from_year: int, to_year: int) -> list[Product]:
    """Copy every product of one season to another, dates and names moved along.

    The copies are created inactive so nothing goes on sale until the admin
    has checked prices. A product whose name already exists in the target
    season is skipped, so running twice adds nothing.
    """
    if to_year <= from_year:
        raise CatalogRejected("the target season must be later")
    years = to_year - from_year
    existing = {p.name for p in all_products(to_year)}
    created: list[Product] = []
    for source in all_products(from_year):
        name = source.name.replace(str(from_year), str(to_year))
        if name in existing:
            continue
        copy = Product.objects.create(
            name=name,
            description=source.description.replace(str(from_year), str(to_year)),
            season_year=to_year,
            sort_order=source.sort_order,
            active=False,
        )
        Price.objects.bulk_create(
            Price(
                product=copy,
                label=p.label,
                amount_cents=p.amount_cents,
                starts_at=_shift(p.starts_at, years),
                ends_at=_shift(p.ends_at, years),
                members_only=p.members_only,
            )
            for p in source.prices.all()
        )
        EntitlementGrant.objects.bulk_create(
            EntitlementGrant(
                product=copy,
                kind=g.kind,
                valid_from=_shift(g.valid_from, years),
                valid_to=_shift(g.valid_to, years),
                visit_count=g.visit_count,
            )
            for g in source.grants.all()
        )
        EligibilityRule.objects.bulk_create(
            EligibilityRule(
                product=copy,
                kind=r.kind,
                parameters={
                    **r.parameters,
                    **({"season_year": to_year} if "season_year" in r.parameters else {}),
                },
                failure_message=r.failure_message.replace(str(from_year), str(to_year)),
            )
            for r in source.rules.all()
        )
        created.append(load_product(copy.id))
    return created
