"""Reports are code: a closed registry of named queries with declared parameters.

Each report declares its parameters, so the admin page can draw the form
without knowing the report, and returns columns plus rows, which the page
shows as a table or hands over as CSV. Adding a report is adding a
function here and registering it; nothing else changes.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from sqlalchemy import Date, case, cast, func, select
from sqlalchemy.orm import Session

from sws_membership.cards.models import CardPrint
from sws_membership.catalog.models import Product
from sws_membership.entitlements.models import Entitlement, EntitlementKind
from sws_membership.kiosk.models import CheckIn
from sws_membership.members.models import Member, MemberSport
from sws_membership.orders.models import Order, OrderLine, OrderStatus
from sws_membership.waivers.models import WaiverSignature, WaiverTemplate


@dataclass(frozen=True)
class Parameter:
    name: str
    label: str
    kind: str  # "date" | "int" | "text"
    default: Any = None


@dataclass(frozen=True)
class ReportResult:
    columns: list[str]
    rows: list[list[Any]]


@dataclass(frozen=True)
class Report:
    name: str
    title: str
    description: str
    parameters: tuple[Parameter, ...]
    run: Callable[[Session, dict[str, Any]], ReportResult] = field(repr=False)


def _year(params: dict[str, Any]) -> int:
    return int(params.get("season_year") or date.today().year)


def _day(params: dict[str, Any], name: str, default: date) -> date:
    value = params.get(name)
    return date.fromisoformat(value) if isinstance(value, str) and value else (value or default)


def sales_by_product(session: Session, params: dict[str, Any]) -> ReportResult:
    year = _year(params)
    rows = session.execute(
        select(
            Product.name,
            Order.payment_method,
            func.count(OrderLine.id),
            func.sum(OrderLine.amount_cents),
        )
        .join(OrderLine, OrderLine.product_id == Product.id)
        .join(Order, Order.id == OrderLine.order_id)
        .where(Product.season_year == year, Order.status == OrderStatus.PAID)
        .group_by(Product.name, Order.payment_method)
        .order_by(Product.name, Order.payment_method)
    ).all()
    return ReportResult(
        ["Product", "Paid by", "Sold", "Revenue (CAD)"],
        [[name, method.value, count, (total or 0) / 100] for name, method, count, total in rows],
    )


def active_memberships(session: Session, params: dict[str, Any]) -> ReportResult:
    on = _day(params, "on", date.today())
    rows = session.execute(
        select(Product.name, func.count(Entitlement.id))
        .join(Product, Product.id == Entitlement.product_id)
        .where(
            Entitlement.kind == EntitlementKind.MEMBERSHIP,
            Entitlement.valid_from <= on,
            Entitlement.valid_to >= on,
        )
        .group_by(Product.name)
        .order_by(Product.name)
    ).all()
    total = sum(count for _, count in rows)
    return ReportResult(
        ["Product", "Active members"], [[n, c] for n, c in rows] + [["Total", total]]
    )


def attendance_by_day(session: Session, params: dict[str, Any]) -> ReportResult:
    until = _day(params, "until", date.today())
    since = _day(params, "since", until - timedelta(days=30))
    rows = session.execute(
        select(
            CheckIn.on_day,
            func.count(case((CheckIn.station == "spit", 1))),
            func.count(case((CheckIn.station == "shuttle", 1))),
        )
        .where(CheckIn.on_day >= since, CheckIn.on_day <= until)
        .group_by(CheckIn.on_day)
        .order_by(CheckIn.on_day)
    ).all()
    return ReportResult(["Day", "Spit", "Shuttle"], [[d.isoformat(), s, sh] for d, s, sh in rows])


def members_missing_profile(session: Session, params: dict[str, Any]) -> ReportResult:
    members = session.scalars(select(Member).order_by(Member.last_name, Member.first_name)).all()
    rows = [
        [
            m.member_number,
            f"{m.first_name} {m.last_name}",
            m.email,
            ", ".join(m.missing_profile_fields()),
        ]
        for m in members
        if m.missing_profile_fields()
    ]
    return ReportResult(["Number", "Name", "Email", "Missing"], rows)


def waiver_status(session: Session, params: dict[str, Any]) -> ReportResult:
    on = _day(params, "on", date.today())
    latest = session.scalars(
        select(WaiverTemplate).order_by(WaiverTemplate.version.desc()).limit(1)
    ).first()
    holders = session.scalars(
        select(Member)
        .join(Entitlement, Entitlement.member_id == Member.id)
        .where(Entitlement.valid_from <= on, Entitlement.valid_to >= on)
        .distinct()
        .order_by(Member.last_name, Member.first_name)
    ).all()
    signed_ids: set[int] = set()
    if latest is not None:
        signed_ids = set(
            session.scalars(
                select(WaiverSignature.member_id).where(WaiverSignature.template_id == latest.id)
            ).all()
        )
    rows = [
        [
            m.member_number,
            f"{m.first_name} {m.last_name}",
            "signed" if m.id in signed_ids else "NOT signed",
        ]
        for m in holders
    ]
    return ReportResult(["Number", "Name", f"Waiver v{latest.version if latest else '-'}"], rows)


def cards_to_print(session: Session, params: dict[str, Any]) -> ReportResult:
    on = _day(params, "on", date.today())
    printed = select(CardPrint.member_id).distinct()
    members = session.scalars(
        select(Member)
        .join(Entitlement, Entitlement.member_id == Member.id)
        .where(
            Entitlement.kind == EntitlementKind.MEMBERSHIP,
            Entitlement.valid_from <= on,
            Entitlement.valid_to >= on,
            Member.id.not_in(printed),
        )
        .distinct()
        .order_by(Member.last_name, Member.first_name)
    ).all()
    return ReportResult(
        ["Member id", "Number", "Name", "Photo"],
        [
            [m.id, m.member_number, f"{m.first_name} {m.last_name}", "yes" if m.photo_key else "NO"]
            for m in members
        ],
    )


def sports_breakdown(session: Session, params: dict[str, Any]) -> ReportResult:
    rows = session.execute(
        select(MemberSport.sport, func.count())
        .group_by(MemberSport.sport)
        .order_by(func.count().desc())
    ).all()
    return ReportResult(["Sport", "Members"], [[s.value, c] for s, c in rows])


def new_members_by_month(session: Session, params: dict[str, Any]) -> ReportResult:
    year = _year(params)
    month = func.to_char(cast(Member.created_at, Date), "YYYY-MM")
    rows = session.execute(
        select(month, func.count())
        .where(func.extract("year", Member.created_at) == year)
        .group_by(month)
        .order_by(month)
    ).all()
    return ReportResult(["Month", "New members"], [[m, c] for m, c in rows])


REPORTS: dict[str, Report] = {
    report.name: report
    for report in (
        Report(
            "sales_by_product",
            "Sales by product",
            "Paid orders in a season: how many of each product sold, by payment method, and the revenue.",
            (Parameter("season_year", "Season year", "int", date.today().year),),
            sales_by_product,
        ),
        Report(
            "active_memberships",
            "Active memberships",
            "Members holding an active membership on a day, by product.",
            (Parameter("on", "On date", "date", date.today().isoformat()),),
            active_memberships,
        ),
        Report(
            "attendance_by_day",
            "Attendance by day",
            "Check-ins per day at each station between two dates.",
            (
                Parameter("since", "From", "date", (date.today() - timedelta(days=30)).isoformat()),
                Parameter("until", "To", "date", date.today().isoformat()),
            ),
            attendance_by_day,
        ),
        Report(
            "members_missing_profile",
            "Members with incomplete profiles",
            "Who still cannot buy a pass, and what they are missing.",
            (),
            members_missing_profile,
        ),
        Report(
            "waiver_status",
            "Waiver status of active pass holders",
            "Members holding any active pass on a day, and whether they have signed the current waiver.",
            (Parameter("on", "On date", "date", date.today().isoformat()),),
            waiver_status,
        ),
        Report(
            "cards_to_print",
            "Cards to print",
            "Active members who have never had a card printed. Use the ids for a batch print.",
            (Parameter("on", "On date", "date", date.today().isoformat()),),
            cards_to_print,
        ),
        Report(
            "sports_breakdown",
            "Sports breakdown",
            "How many members ride each sport.",
            (),
            sports_breakdown,
        ),
        Report(
            "new_members_by_month",
            "New members by month",
            "Member records created in a year, by month.",
            (Parameter("season_year", "Year", "int", date.today().year),),
            new_members_by_month,
        ),
    )
}
