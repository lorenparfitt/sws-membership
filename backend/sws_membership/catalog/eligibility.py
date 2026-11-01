"""Whether a member may buy a product today: one pure function over facts.

Nothing here reads the database. The caller gathers MemberFacts and hands
over ProductSpecs (Product.spec() builds one from the rows), and the same
evaluation serves the catalog page (why is this locked?), checkout (refuse
the order) and the staff point of sale. Each RuleKind has exactly one
checker below; adding a condition means adding a kind and a checker.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date

from sws_membership.catalog.models import RuleKind
from sws_membership.entitlements.models import EntitlementKind, active_on


@dataclass(frozen=True)
class PriceSpec:
    id: int | None
    label: str
    amount_cents: int
    starts_at: date
    ends_at: date | None = None
    members_only: bool = False

    def is_on_sale(self, day: date) -> bool:
        return self.starts_at <= day and (self.ends_at is None or day <= self.ends_at)


@dataclass(frozen=True)
class GrantSpec:
    kind: EntitlementKind
    valid_from: date
    valid_to: date
    visit_count: int | None = None


@dataclass(frozen=True)
class RuleSpec:
    kind: RuleKind
    parameters: dict
    failure_message: str


@dataclass(frozen=True)
class ProductSpec:
    id: int | None
    name: str
    season_year: int
    prices: tuple[PriceSpec, ...] = ()
    grants: tuple[GrantSpec, ...] = ()
    rules: tuple[RuleSpec, ...] = ()

    def price_on(self, day: date, member_prices: bool) -> PriceSpec | None:
        """The price in force on a day; the members-only one wins when allowed."""
        candidates = [
            price
            for price in self.prices
            if price.is_on_sale(day) and (member_prices or not price.members_only)
        ]
        candidates.sort(key=lambda price: (not price.members_only, price.amount_cents))
        return candidates[0] if candidates else None


@dataclass(frozen=True)
class Held:
    """An entitlement as the checkers see it: a row, or what a basket would grant.

    A membership in the same basket unlocks the season pass next to it and
    earns its member price, so both shapes are judged alike.
    """

    kind: EntitlementKind
    product_id: int | None
    season_year: int
    valid_from: date
    valid_to: date
    visits_remaining: int | None = None

    def is_active_on(self, day: date) -> bool:
        return active_on(self.kind, self.valid_from, self.valid_to, self.visits_remaining, day)

    @classmethod
    def of_row(cls, entitlement) -> "Held":
        return cls(
            kind=EntitlementKind(entitlement.kind),
            product_id=entitlement.product_id,
            season_year=entitlement.product.season_year,
            valid_from=entitlement.valid_from,
            valid_to=entitlement.valid_to,
            visits_remaining=entitlement.visits_remaining,
        )


def would_grant(product: ProductSpec) -> tuple[Held, ...]:
    return tuple(
        Held(
            kind=grant.kind,
            product_id=product.id,
            season_year=product.season_year,
            valid_from=grant.valid_from,
            valid_to=grant.valid_to,
            visits_remaining=grant.visit_count,
        )
        for grant in product.grants
    )


@dataclass(frozen=True)
class MemberFacts:
    date_of_birth: date | None
    entitlements: tuple[Held, ...] = ()
    has_current_waiver: bool = False
    profile_complete: bool = True

    def active_entitlements(self, day: date) -> list[Held]:
        return [e for e in self.entitlements if e.is_active_on(day)]

    def is_member_on(self, day: date) -> bool:
        return any(e.kind is EntitlementKind.MEMBERSHIP for e in self.active_entitlements(day))

    def age_on(self, day: date) -> int | None:
        if self.date_of_birth is None:
            return None
        born = self.date_of_birth
        return day.year - born.year - ((day.month, day.day) < (born.month, born.day))

    def holding(self, pending: tuple[Held, ...]) -> "MemberFacts":
        """The same member, counting what the basket would grant as held."""
        if not pending:
            return self
        return MemberFacts(
            date_of_birth=self.date_of_birth,
            entitlements=self.entitlements + pending,
            has_current_waiver=self.has_current_waiver,
            profile_complete=self.profile_complete,
        )


@dataclass(frozen=True)
class Eligibility:
    price: PriceSpec | None
    failures: tuple[str, ...] = field(default_factory=tuple)

    @property
    def purchasable(self) -> bool:
        return self.price is not None and not self.failures


Checker = Callable[[RuleSpec, ProductSpec, MemberFacts, date], bool]


def _requires_active_entitlement(
    rule: RuleSpec, product: ProductSpec, facts: MemberFacts, day: date
) -> bool:
    wanted = EntitlementKind(rule.parameters["kind"])
    season_year = rule.parameters.get("season_year")
    return any(
        e.kind is wanted and (season_year is None or e.season_year == season_year)
        for e in facts.active_entitlements(day)
    )


def _requires_current_waiver(
    rule: RuleSpec, product: ProductSpec, facts: MemberFacts, day: date
) -> bool:
    return facts.has_current_waiver


def _profile_complete(rule: RuleSpec, product: ProductSpec, facts: MemberFacts, day: date) -> bool:
    return facts.profile_complete


def _age_at_least(rule: RuleSpec, product: ProductSpec, facts: MemberFacts, day: date) -> bool:
    age = facts.age_on(day)
    return age is not None and age >= int(rule.parameters["years"])


def _age_at_most(rule: RuleSpec, product: ProductSpec, facts: MemberFacts, day: date) -> bool:
    age = facts.age_on(day)
    return age is not None and age <= int(rule.parameters["years"])


def _one_per_member_per_season(
    rule: RuleSpec, product: ProductSpec, facts: MemberFacts, day: date
) -> bool:
    return not any(e.product_id == product.id for e in facts.entitlements)


CHECKERS: dict[RuleKind, Checker] = {
    RuleKind.REQUIRES_ACTIVE_ENTITLEMENT: _requires_active_entitlement,
    RuleKind.REQUIRES_CURRENT_WAIVER: _requires_current_waiver,
    RuleKind.PROFILE_COMPLETE: _profile_complete,
    RuleKind.AGE_AT_LEAST: _age_at_least,
    RuleKind.AGE_AT_MOST: _age_at_most,
    RuleKind.ONE_PER_MEMBER_PER_SEASON: _one_per_member_per_season,
}
assert set(CHECKERS) == set(RuleKind), "every rule kind needs exactly one checker"


def evaluate(product: ProductSpec, facts: MemberFacts, day: date) -> Eligibility:
    price = product.price_on(day, member_prices=facts.is_member_on(day))
    failures = tuple(
        rule.failure_message
        for rule in product.rules
        if not CHECKERS[rule.kind](rule, product, facts, day)
    )
    return Eligibility(price=price, failures=failures)


def evaluate_basket(
    products: list[ProductSpec], facts: MemberFacts, day: date
) -> dict[int, Eligibility]:
    """Judge every product in a basket, each one counting the others as held.

    A product is judged against the member's real entitlements plus what the
    other purchasable products in the basket would grant, never its own
    grants (or one-per-season would refuse it). Settles by repetition: a
    product that fails alone can pass once the membership beside it counts.
    """
    results: dict[int, Eligibility] = {}
    for _ in range(len(products) + 1):
        pending = {
            p.id: would_grant(p)
            for p in products
            if results.get(p.id, Eligibility(None)).purchasable
        }
        judged = {}
        for product in products:
            others = tuple(
                e for pid, grants in pending.items() if pid != product.id for e in grants
            )
            judged[product.id] = evaluate(product, facts.holding(others), day)
        if judged == results:
            break
        results = judged
    return results
