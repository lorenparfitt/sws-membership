"""A development catalog shaped like the society's real one.

Products mirror what WellnessLiving sells today: adult and youth
memberships, season passes that bundle a membership, a non-member day pass,
and a member-priced shuttle pass that is gated behind membership. The
windows span the whole calendar year of the chosen season, so the sample is
on sale whenever a developer runs it. Loading is idempotent on (name,
season_year), so the seed task can run repeatedly.
"""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from sws_membership.catalog.models import (
    EligibilityRule,
    EntitlementGrant,
    Price,
    Product,
    RuleKind,
)
from sws_membership.entitlements.models import EntitlementKind

ONCE_RULE = (RuleKind.ONE_PER_MEMBER_PER_SEASON, {}, "Already held for this season")
ADULT_RULE = (RuleKind.AGE_AT_LEAST, {"years": 19}, "For members 19 and over")
YOUTH_RULE = (RuleKind.AGE_AT_MOST, {"years": 18}, "For members 18 and under")
WAIVER_RULE = (RuleKind.REQUIRES_CURRENT_WAIVER, {}, "Sign the current waiver first")


def member_only_rule(season_year: int) -> tuple:
    return (
        RuleKind.REQUIRES_ACTIVE_ENTITLEMENT,
        {"kind": EntitlementKind.MEMBERSHIP.value, "season_year": season_year},
        f"Needs an active {season_year} membership",
    )


def _season(year: int, kind: EntitlementKind, visits: int | None = None) -> dict:
    return {
        "kind": kind,
        "valid_from": date(year, 1, 1),
        "valid_to": date(year, 12, 31),
        "visit_count": visits,
    }


def _prices(
    year: int, regular: int, early_bird: int | None = None, members_only: bool = False
) -> list[dict]:
    prices = []
    if early_bird is not None:
        prices.append(
            {
                "label": "Early bird",
                "amount_cents": early_bird,
                "starts_at": date(year, 1, 1),
                "ends_at": date(year, 4, 30),
                "members_only": members_only,
            }
        )
    prices.append(
        {
            "label": "Regular",
            "amount_cents": regular,
            "starts_at": date(year, 5, 1) if early_bird is not None else date(year, 1, 1),
            "ends_at": date(year, 12, 31),
            "members_only": members_only,
        }
    )
    return prices


def sample_products(year: int) -> list[dict]:
    return [
        {
            "name": f"Adult SWS Membership {year}",
            "description": f"Society membership for the {year} season.",
            "sort_order": 10,
            "prices": _prices(year, regular=4000),
            "grants": [_season(year, EntitlementKind.MEMBERSHIP)],
            "rules": [ADULT_RULE, ONCE_RULE],
        },
        {
            "name": f"Youth SWS Membership {year}",
            "description": "Society membership for riders 18 and under.",
            "sort_order": 20,
            "prices": _prices(year, regular=2000),
            "grants": [_season(year, EntitlementKind.MEMBERSHIP)],
            "rules": [YOUTH_RULE, ONCE_RULE],
        },
        {
            "name": f"Adult Season Pass {year}",
            "description": "Membership plus unlimited Spit access all season.",
            "sort_order": 30,
            "prices": _prices(year, regular=30000, early_bird=25000),
            "grants": [
                _season(year, EntitlementKind.MEMBERSHIP),
                _season(year, EntitlementKind.SEASON_ACCESS),
            ],
            "rules": [ADULT_RULE, ONCE_RULE, WAIVER_RULE],
        },
        {
            "name": f"Youth Season Pass {year}",
            "description": "Membership plus unlimited Spit access for riders 18 and under.",
            "sort_order": 40,
            "prices": _prices(year, regular=15000, early_bird=12500),
            "grants": [
                _season(year, EntitlementKind.MEMBERSHIP),
                _season(year, EntitlementKind.SEASON_ACCESS),
            ],
            "rules": [YOUTH_RULE, ONCE_RULE, WAIVER_RULE],
        },
        {
            "name": f"Day Pass {year}",
            "description": "One day at the Spit. No membership needed.",
            "sort_order": 50,
            "prices": _prices(year, regular=3500),
            "grants": [_season(year, EntitlementKind.DAY_VISITS, visits=1)],
            "rules": [WAIVER_RULE],
        },
        {
            "name": f"Member Day Shuttle Pass {year}",
            "description": f"One shuttle day, at the member price. Needs a {year} membership.",
            "sort_order": 60,
            "prices": _prices(year, regular=2500, members_only=True),
            "grants": [_season(year, EntitlementKind.SHUTTLE_ACCESS, visits=1)],
            "rules": [member_only_rule(year), WAIVER_RULE],
        },
    ]


def load_sample_catalog(session: Session, season_year: int | None = None) -> int:
    """Create any missing sample product and re-sync the rules of existing ones.

    Returns how many were created. Rules are replaced on existing products so
    a developer database follows the sample as it changes; prices and grants
    are left alone because orders already point at them.
    """
    season_year = season_year or date.today().year
    created = 0
    for spec in sample_products(season_year):
        exists = session.scalars(
            select(Product).where(Product.name == spec["name"], Product.season_year == season_year)
        ).first()
        if exists:
            exists.rules = [
                EligibilityRule(kind=kind, parameters=parameters, failure_message=message)
                for kind, parameters, message in spec["rules"]
            ]
            continue
        product = Product(
            name=spec["name"],
            description=spec["description"],
            season_year=season_year,
            sort_order=spec["sort_order"],
            prices=[Price(**price) for price in spec["prices"]],
            grants=[EntitlementGrant(**grant) for grant in spec["grants"]],
            rules=[
                EligibilityRule(kind=kind, parameters=parameters, failure_message=message)
                for kind, parameters, message in spec["rules"]
            ],
        )
        session.add(product)
        created += 1
    session.flush()
    return created
