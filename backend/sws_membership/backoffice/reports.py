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

from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncMonth

from sws_membership.cards.models import CardPrint
from sws_membership.entitlements.models import Entitlement, EntitlementKind
from sws_membership.kiosk.models import CheckIn
from sws_membership.members.models import Member, MemberSport
from sws_membership.orders.models import OrderLine, OrderStatus
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
    run: Callable[[dict[str, Any]], ReportResult] = field(repr=False)


def _year(params: dict[str, Any]) -> int:
    return int(params.get("season_year") or date.today().year)


def _day(params: dict[str, Any], name: str, default: date) -> date:
    value = params.get(name)
    return date.fromisoformat(value) if isinstance(value, str) and value else (value or default)


def _active(on: date):
    return Q(valid_from__lte=on, valid_to__gte=on, revoked_at__isnull=True)


def sales_by_product(params: dict[str, Any]) -> ReportResult:
    year = _year(params)
    rows = (
        OrderLine.objects.filter(product__season_year=year, order__status=OrderStatus.PAID)
        .values("product__name", "order__payment_method")
        .annotate(sold=Count("id"), revenue=Sum("amount_cents"))
        .order_by("product__name", "order__payment_method")
    )
    return ReportResult(
        ["Product", "Paid by", "Sold", "Revenue (CAD)"],
        [
            [r["product__name"], r["order__payment_method"], r["sold"], (r["revenue"] or 0) / 100]
            for r in rows
        ],
    )


def active_memberships(params: dict[str, Any]) -> ReportResult:
    on = _day(params, "on", date.today())
    rows = (
        Entitlement.objects.filter(_active(on), kind=EntitlementKind.MEMBERSHIP)
        .values("product__name")
        .annotate(n=Count("id"))
        .order_by("product__name")
    )
    listed = [[r["product__name"], r["n"]] for r in rows]
    return ReportResult(
        ["Product", "Active members"], listed + [["Total", sum(c for _, c in listed)]]
    )


def attendance_by_day(params: dict[str, Any]) -> ReportResult:
    until = _day(params, "until", date.today())
    since = _day(params, "since", until - timedelta(days=30))
    rows = (
        CheckIn.objects.filter(on_day__gte=since, on_day__lte=until)
        .values("on_day")
        .annotate(
            spit=Count("id", filter=Q(station="spit")),
            shuttle=Count("id", filter=Q(station="shuttle")),
        )
        .order_by("on_day")
    )
    return ReportResult(
        ["Day", "Spit", "Shuttle"],
        [[r["on_day"].isoformat(), r["spit"], r["shuttle"]] for r in rows],
    )


def members_missing_profile(params: dict[str, Any]) -> ReportResult:
    rows = [
        [
            m.member_number,
            f"{m.first_name} {m.last_name}",
            m.email,
            ", ".join(m.missing_profile_fields()),
        ]
        for m in Member.objects.prefetch_related("sports").order_by("last_name", "first_name")
        if m.missing_profile_fields()
    ]
    return ReportResult(["Number", "Name", "Email", "Missing"], rows)


def waiver_status(params: dict[str, Any]) -> ReportResult:
    on = _day(params, "on", date.today())
    latest = WaiverTemplate.objects.order_by("-version").first()
    holders = (
        Member.objects.filter(
            entitlements__valid_from__lte=on,
            entitlements__valid_to__gte=on,
            entitlements__revoked_at__isnull=True,
        )
        .distinct()
        .order_by("last_name", "first_name")
    )
    signed_ids: set[int] = set()
    if latest is not None:
        signed_ids = set(
            WaiverSignature.objects.filter(template=latest).values_list("member_id", flat=True)
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


def cards_to_print(params: dict[str, Any]) -> ReportResult:
    on = _day(params, "on", date.today())
    printed = CardPrint.objects.values("member_id")
    members = (
        Member.objects.filter(
            entitlements__kind=EntitlementKind.MEMBERSHIP,
            entitlements__valid_from__lte=on,
            entitlements__valid_to__gte=on,
            entitlements__revoked_at__isnull=True,
        )
        .exclude(id__in=printed)
        .distinct()
        .order_by("last_name", "first_name")
    )
    return ReportResult(
        ["Member id", "Number", "Name", "Photo"],
        [
            [m.id, m.member_number, f"{m.first_name} {m.last_name}", "yes" if m.photo_key else "NO"]
            for m in members
        ],
    )


def sports_breakdown(params: dict[str, Any]) -> ReportResult:
    rows = MemberSport.objects.values("sport").annotate(n=Count("id")).order_by("-n")
    return ReportResult(["Sport", "Members"], [[r["sport"], r["n"]] for r in rows])


def new_members_by_month(params: dict[str, Any]) -> ReportResult:
    year = _year(params)
    rows = (
        Member.objects.filter(created_at__year=year)
        .annotate(month=TruncMonth("created_at"))
        .values("month")
        .annotate(n=Count("id"))
        .order_by("month")
    )
    return ReportResult(
        ["Month", "New members"], [[r["month"].strftime("%Y-%m"), r["n"]] for r in rows]
    )


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
