"""Admin routes: catalog editing, rollover, reports, waiver history."""

import csv
from datetime import date, datetime
from io import StringIO
from typing import Any

from django.http import HttpResponse
from ninja import Router, Schema, Status
from ninja.errors import HttpError

from sws_membership.accounts.auth import admin_auth
from sws_membership.backoffice import catalog_service as catalog
from sws_membership.backoffice.reports import REPORTS
from sws_membership.catalog.models import Product, RuleKind
from sws_membership.entitlements.models import EntitlementKind
from sws_membership.waivers.models import WaiverReset, WaiverTemplate

router = Router(tags=["admin"], auth=admin_auth)


# --- catalog ---------------------------------------------------------------


class PriceView(Schema):
    id: int
    label: str
    amount_cents: int
    starts_at: date
    ends_at: date | None
    members_only: bool


class GrantView(Schema):
    id: int
    kind: str
    valid_from: date
    valid_to: date
    visit_count: int | None


class RuleView(Schema):
    id: int
    kind: str
    parameters: dict
    failure_message: str


class AdminProductView(Schema):
    id: int
    name: str
    description: str
    season_year: int
    sort_order: int
    active: bool
    prices: list[PriceView]
    grants: list[GrantView]
    rules: list[RuleView]

    @classmethod
    def of(cls, p: Product) -> "AdminProductView":
        return cls(
            id=p.id,
            name=p.name,
            description=p.description,
            season_year=p.season_year,
            sort_order=p.sort_order,
            active=p.active,
            prices=[PriceView.from_orm(x) for x in p.prices.all()],
            grants=[GrantView.from_orm(g) for g in p.grants.all()],
            rules=[RuleView.from_orm(r) for r in p.rules.all()],
        )


class ProductBody(Schema):
    name: str
    description: str = ""
    season_year: int
    sort_order: int = 0
    active: bool = True


class PriceBody(Schema):
    label: str = ""
    amount_cents: int
    starts_at: date
    ends_at: date | None = None
    members_only: bool = False


class GrantBody(Schema):
    kind: EntitlementKind
    valid_from: date
    valid_to: date
    visit_count: int | None = None


class RuleBody(Schema):
    kind: RuleKind
    parameters: dict = {}
    failure_message: str


class RolloverBody(Schema):
    from_year: int
    to_year: int


def _product(product_id: int) -> Product:
    try:
        return catalog.load_product(product_id)
    except LookupError:
        raise HttpError(404, "no such product")


def _fresh(product: Product) -> AdminProductView:
    return AdminProductView.of(catalog.load_product(product.id))


def _rejected(problem: Exception) -> HttpError:
    return HttpError(400, str(problem))


@router.get("/catalog/options")
def catalog_options(request) -> dict:
    return {
        "entitlement_kinds": [k.value for k in EntitlementKind],
        "rule_kinds": [
            {"kind": k.value, "parameters": catalog.RULE_PARAMETERS[k]} for k in RuleKind
        ],
    }


@router.get("/catalog/products", response=list[AdminProductView])
def list_products(request, season_year: int | None = None):
    return [AdminProductView.of(p) for p in catalog.all_products(season_year)]


@router.post("/catalog/products", response={201: AdminProductView})
def create_product(request, body: ProductBody):
    try:
        return Status(201, _fresh(catalog.create_product(catalog.ProductInput(**body.dict()))))
    except catalog.CatalogRejected as why:
        raise _rejected(why)


@router.put("/catalog/products/{product_id}", response=AdminProductView)
def update_product(request, product_id: int, body: ProductBody):
    try:
        return _fresh(
            catalog.update_product(_product(product_id), catalog.ProductInput(**body.dict()))
        )
    except catalog.CatalogRejected as why:
        raise _rejected(why)


@router.post("/catalog/products/{product_id}/prices", response={201: AdminProductView})
def add_price(request, product_id: int, body: PriceBody):
    product = _product(product_id)
    try:
        catalog.add_price(product, catalog.PriceInput(**body.dict()))
    except catalog.CatalogRejected as why:
        raise _rejected(why)
    return Status(201, _fresh(product))


@router.delete("/catalog/products/{product_id}/prices/{price_id}", response=AdminProductView)
def remove_price(request, product_id: int, price_id: int):
    product = _product(product_id)
    try:
        catalog.remove_price(product, price_id)
    except LookupError:
        raise HttpError(404, "no such price")
    except catalog.CatalogRejected as why:
        raise _rejected(why)
    return _fresh(product)


@router.post("/catalog/products/{product_id}/grants", response={201: AdminProductView})
def add_grant(request, product_id: int, body: GrantBody):
    product = _product(product_id)
    try:
        catalog.add_grant(product, catalog.GrantInput(**body.dict()))
    except catalog.CatalogRejected as why:
        raise _rejected(why)
    return Status(201, _fresh(product))


@router.delete("/catalog/products/{product_id}/grants/{grant_id}", response=AdminProductView)
def remove_grant(request, product_id: int, grant_id: int):
    product = _product(product_id)
    try:
        catalog.remove_grant(product, grant_id)
    except LookupError:
        raise HttpError(404, "no such grant")
    return _fresh(product)


@router.post("/catalog/products/{product_id}/rules", response={201: AdminProductView})
def add_rule(request, product_id: int, body: RuleBody):
    product = _product(product_id)
    try:
        catalog.add_rule(product, body.kind, body.parameters, body.failure_message)
    except catalog.CatalogRejected as why:
        raise _rejected(why)
    return Status(201, _fresh(product))


@router.delete("/catalog/products/{product_id}/rules/{rule_id}", response=AdminProductView)
def remove_rule(request, product_id: int, rule_id: int):
    product = _product(product_id)
    try:
        catalog.remove_rule(product, rule_id)
    except LookupError:
        raise HttpError(404, "no such rule")
    return _fresh(product)


@router.post("/catalog/rollover", response={201: list[AdminProductView]})
def rollover(request, body: RolloverBody):
    try:
        copies = catalog.rollover_season(body.from_year, body.to_year)
        return Status(201, [AdminProductView.of(p) for p in copies])
    except catalog.CatalogRejected as why:
        raise _rejected(why)


# --- reports ---------------------------------------------------------------


class ParameterView(Schema):
    name: str
    label: str
    kind: str
    default: Any


class ReportView(Schema):
    name: str
    title: str
    description: str
    parameters: list[ParameterView]


class ReportRun(Schema):
    parameters: dict[str, Any] = {}


class ReportOutput(Schema):
    title: str
    columns: list[str]
    rows: list[list[Any]]


@router.get("/reports", response=list[ReportView])
def list_reports(request):
    return [
        ReportView(
            name=r.name,
            title=r.title,
            description=r.description,
            parameters=[ParameterView(**p.__dict__) for p in r.parameters],
        )
        for r in REPORTS.values()
    ]


def _run(name: str, parameters: dict[str, Any]):
    report = REPORTS.get(name)
    if report is None:
        raise HttpError(404, "no such report")
    try:
        return report, report.run(parameters)
    except (ValueError, TypeError) as why:
        raise HttpError(400, f"bad parameters: {why}")


@router.post("/reports/{name}/run", response=ReportOutput)
def run_report(request, name: str, body: ReportRun):
    report, result = _run(name, body.parameters)
    return ReportOutput(title=report.title, columns=result.columns, rows=result.rows)


@router.post("/reports/{name}/csv")
def report_csv(request, name: str, body: ReportRun):
    _, result = _run(name, body.parameters)
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(result.columns)
    writer.writerows(result.rows)
    response = HttpResponse(buffer.getvalue(), content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{name}.csv"'
    return response


# --- waiver history --------------------------------------------------------


class TemplateView(Schema):
    id: int
    version: int
    title: str
    body_text: str
    published_at: datetime


class ResetView(Schema):
    reset_at: datetime
    reason: str


class WaiverHistory(Schema):
    templates: list[TemplateView]
    resets: list[ResetView]


@router.get("/waiver/history", response=WaiverHistory)
def waiver_history(request):
    return WaiverHistory(
        templates=[TemplateView.from_orm(t) for t in WaiverTemplate.objects.order_by("-version")],
        resets=[ResetView.from_orm(r) for r in WaiverReset.objects.order_by("-reset_at")[:20]],
    )
