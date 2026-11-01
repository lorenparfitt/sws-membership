"""The rule engine, judged without a database."""

from datetime import date

from sws_membership.catalog.eligibility import (
    GrantSpec,
    Held,
    MemberFacts,
    PriceSpec,
    ProductSpec,
    RuleSpec,
    evaluate,
    evaluate_basket,
)
from sws_membership.catalog.models import RuleKind
from sws_membership.entitlements.models import EntitlementKind

TODAY = date(2026, 6, 15)
SEASON = (date(2026, 5, 1), date(2026, 9, 30))


def _price(label="Regular", amount=1000, starts=date(2026, 3, 1), ends=None, members_only=False):
    return PriceSpec(
        id=None,
        label=label,
        amount_cents=amount,
        starts_at=starts,
        ends_at=ends,
        members_only=members_only,
    )


def _product(rules=(), prices=None, product_id=1, season_year=2026, grants=()) -> ProductSpec:
    return ProductSpec(
        id=product_id,
        name="Thing",
        season_year=season_year,
        prices=tuple(prices) if prices is not None else (_price(),),
        grants=tuple(grants),
        rules=tuple(RuleSpec(kind, parameters, message) for kind, parameters, message in rules),
    )


def _held(kind, product_id=99, season_year=2026, visits=None, window=SEASON) -> Held:
    return Held(
        kind=kind,
        product_id=product_id,
        season_year=season_year,
        valid_from=window[0],
        valid_to=window[1],
        visits_remaining=visits,
    )


def test_no_rules_and_a_live_price_is_purchasable():
    result = evaluate(_product(), MemberFacts(date_of_birth=None), TODAY)
    assert result.purchasable and result.price.amount_cents == 1000


def test_a_product_with_no_price_on_sale_today_is_not_purchasable():
    expired = _price("Early", 500, date(2026, 3, 1), date(2026, 4, 30))
    result = evaluate(_product(prices=[expired]), MemberFacts(date_of_birth=None), TODAY)
    assert result.price is None and not result.purchasable


def test_members_only_price_is_chosen_for_members_and_hidden_from_others():
    public = _price("Regular", 3500)
    member = _price("Member", 2500, members_only=True)
    product = _product(prices=[public, member])
    assert evaluate(product, MemberFacts(None), TODAY).price is public
    with_membership = MemberFacts(None, (_held(EntitlementKind.MEMBERSHIP),))
    assert evaluate(product, with_membership, TODAY).price is member


def test_requires_active_entitlement_checks_kind_season_and_window():
    rule = (
        RuleKind.REQUIRES_ACTIVE_ENTITLEMENT,
        {"kind": "membership", "season_year": 2026},
        "Needs a 2026 membership",
    )
    product = _product(rules=[rule])
    nobody = MemberFacts(None)
    assert evaluate(product, nobody, TODAY).failures == ("Needs a 2026 membership",)
    last_year = MemberFacts(None, (_held(EntitlementKind.MEMBERSHIP, season_year=2025),))
    assert evaluate(product, last_year, TODAY).failures == ("Needs a 2026 membership",)
    lapsed = MemberFacts(
        None, (_held(EntitlementKind.MEMBERSHIP, window=(date(2026, 5, 1), date(2026, 6, 1))),)
    )
    assert evaluate(product, lapsed, TODAY).failures == ("Needs a 2026 membership",)
    current = MemberFacts(None, (_held(EntitlementKind.MEMBERSHIP),))
    assert evaluate(product, current, TODAY).purchasable


def test_age_rules_use_the_age_on_the_day_and_fail_without_a_birth_date():
    adult = _product(rules=[(RuleKind.AGE_AT_LEAST, {"years": 19}, "19 and over")])
    youth = _product(rules=[(RuleKind.AGE_AT_MOST, {"years": 18}, "18 and under")])
    turns_19_tomorrow = MemberFacts(date(2007, 6, 16))
    assert evaluate(adult, turns_19_tomorrow, TODAY).failures == ("19 and over",)
    assert evaluate(youth, turns_19_tomorrow, TODAY).purchasable
    turned_19_today = MemberFacts(date(2007, 6, 15))
    assert evaluate(adult, turned_19_today, TODAY).purchasable
    assert evaluate(youth, turned_19_today, TODAY).failures == ("18 and under",)
    unknown = MemberFacts(None)
    assert evaluate(adult, unknown, TODAY).failures == ("19 and over",)
    assert evaluate(youth, unknown, TODAY).failures == ("18 and under",)


def test_one_per_season_blocks_a_second_purchase_of_the_same_product():
    product = _product(
        rules=[(RuleKind.ONE_PER_MEMBER_PER_SEASON, {}, "Already held")], product_id=5
    )
    held = MemberFacts(None, (_held(EntitlementKind.SEASON_ACCESS, product_id=5),))
    assert evaluate(product, held, TODAY).failures == ("Already held",)
    other = MemberFacts(None, (_held(EntitlementKind.SEASON_ACCESS, product_id=6),))
    assert evaluate(product, other, TODAY).purchasable


def test_every_failing_rule_is_reported_not_just_the_first():
    product = _product(
        rules=[
            (RuleKind.AGE_AT_LEAST, {"years": 19}, "19 and over"),
            (RuleKind.REQUIRES_ACTIVE_ENTITLEMENT, {"kind": "membership"}, "Needs a membership"),
        ]
    )
    result = evaluate(product, MemberFacts(date(2010, 1, 1)), TODAY)
    assert result.failures == ("19 and over", "Needs a membership")


def test_day_visits_entitlement_is_active_only_while_visits_remain():
    spent = _held(EntitlementKind.DAY_VISITS, visits=0)
    unspent = _held(EntitlementKind.DAY_VISITS, visits=1)
    assert not spent.is_active_on(TODAY)
    assert unspent.is_active_on(TODAY)


def test_a_basket_counts_what_its_other_products_would_grant():
    membership = _product(
        rules=[(RuleKind.ONE_PER_MEMBER_PER_SEASON, {}, "already held")],
        product_id=1,
        grants=[GrantSpec(EntitlementKind.MEMBERSHIP, SEASON[0], SEASON[1])],
    )
    season_pass = _product(
        rules=[
            (
                RuleKind.REQUIRES_ACTIVE_ENTITLEMENT,
                {"kind": "membership", "season_year": 2026},
                "needs a membership",
            )
        ],
        prices=[_price("Regular", 1000), _price("Member", 700, members_only=True)],
        product_id=2,
    )
    facts = MemberFacts(date_of_birth=date(1990, 1, 1))

    assert evaluate(season_pass, facts, TODAY).failures == ("needs a membership",)

    judged = evaluate_basket([season_pass, membership], facts, TODAY)
    assert judged[2].purchasable and judged[2].price.amount_cents == 700
    # Its own grant never counts against the membership.
    assert judged[1].purchasable
