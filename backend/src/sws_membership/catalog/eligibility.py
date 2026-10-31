"""Whether a member may buy a product today: one pure function over facts.

Nothing here reads the database. The caller gathers MemberFacts, and the
same evaluation serves the catalog page (why is this locked?), checkout
(refuse the order) and the staff point of sale. Each RuleKind has exactly
one checker below; adding a condition means adding a kind and a checker.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date

from sws_membership.catalog.models import EligibilityRule, Price, Product, RuleKind
from sws_membership.entitlements.models import Entitlement, EntitlementKind


@dataclass(frozen=True)
class PendingEntitlement:
    """What a product in the basket would grant once paid, judged as if held.

    Shaped like an Entitlement for the checkers, so a membership in the same
    basket unlocks the season pass next to it and earns its member price.
    """

    kind: EntitlementKind
    product: Product
    valid_from: date
    valid_to: date
    visits_remaining: int | None

    @property
    def product_id(self) -> int:
        return self.product.id

    def is_active_on(self, day: date) -> bool:
        if not (self.valid_from <= day <= self.valid_to):
            return False
        if self.kind is EntitlementKind.DAY_VISITS:
            return (self.visits_remaining or 0) > 0
        return True


def would_grant(product: Product) -> tuple[PendingEntitlement, ...]:
    return tuple(
        PendingEntitlement(
            kind=grant.kind,
            product=product,
            valid_from=grant.valid_from,
            valid_to=grant.valid_to,
            visits_remaining=grant.visit_count,
        )
        for grant in product.grants
    )


Held = Entitlement | PendingEntitlement


@dataclass(frozen=True)
class MemberFacts:
    date_of_birth: date | None
    entitlements: tuple[Held, ...] = ()
    has_current_waiver: bool = False
    profile_complete: bool = True

    def active_entitlements(self, day: date) -> list[Held]:
        return [e for e in self.entitlements if e.is_active_on(day)]

    def holding(self, pending: tuple[PendingEntitlement, ...]) -> "MemberFacts":
        """The same member, counting what the basket would grant as held."""
        if not pending:
            return self
        return MemberFacts(
            date_of_birth=self.date_of_birth,
            entitlements=self.entitlements + pending,
            has_current_waiver=self.has_current_waiver,
            profile_complete=self.profile_complete,
        )

    def is_member_on(self, day: date) -> bool:
        return any(e.kind is EntitlementKind.MEMBERSHIP for e in self.active_entitlements(day))

    def age_on(self, day: date) -> int | None:
        if self.date_of_birth is None:
            return None
        born = self.date_of_birth
        return day.year - born.year - ((day.month, day.day) < (born.month, born.day))


@dataclass(frozen=True)
class Eligibility:
    price: Price | None
    failures: tuple[str, ...] = field(default_factory=tuple)

    @property
    def purchasable(self) -> bool:
        return self.price is not None and not self.failures


Checker = Callable[[EligibilityRule, Product, MemberFacts, date], bool]


def _requires_active_entitlement(
    rule: EligibilityRule, product: Product, facts: MemberFacts, day: date
) -> bool:
    wanted = EntitlementKind(rule.parameters["kind"])
    season_year = rule.parameters.get("season_year")
    return any(
        e.kind is wanted and (season_year is None or e.product.season_year == season_year)
        for e in facts.active_entitlements(day)
    )


def _requires_current_waiver(
    rule: EligibilityRule, product: Product, facts: MemberFacts, day: date
) -> bool:
    return facts.has_current_waiver


def _profile_complete(
    rule: EligibilityRule, product: Product, facts: MemberFacts, day: date
) -> bool:
    return facts.profile_complete


def _age_at_least(rule: EligibilityRule, product: Product, facts: MemberFacts, day: date) -> bool:
    age = facts.age_on(day)
    return age is not None and age >= int(rule.parameters["years"])


def _age_at_most(rule: EligibilityRule, product: Product, facts: MemberFacts, day: date) -> bool:
    age = facts.age_on(day)
    return age is not None and age <= int(rule.parameters["years"])


def _one_per_member_per_season(
    rule: EligibilityRule, product: Product, facts: MemberFacts, day: date
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


def evaluate(product: Product, facts: MemberFacts, day: date) -> Eligibility:
    price = product.price_on(day, member_prices=facts.is_member_on(day))
    failures = tuple(
        rule.failure_message
        for rule in product.rules
        if not CHECKERS[rule.kind](rule, product, facts, day)
    )
    return Eligibility(price=price, failures=failures)


def evaluate_basket(
    products: list[Product], facts: MemberFacts, day: date
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
