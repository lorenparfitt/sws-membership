"""Admin routes: catalog editing, rollover, reports, waiver history, cards to print."""

import csv
from datetime import date
from io import StringIO
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy import select

from sws_membership.admin import catalog_service as catalog
from sws_membership.admin.reports import REPORTS
from sws_membership.auth.dependencies import DatabaseSession, require_role
from sws_membership.catalog.models import Product, RuleKind
from sws_membership.entitlements.models import EntitlementKind
from sws_membership.members.models import Member, MemberRole
from sws_membership.waivers.models import WaiverReset, WaiverTemplate

router = APIRouter(prefix="/api/admin", tags=["admin"])
Admin = Annotated[Member, Depends(require_role(MemberRole.ADMIN))]


# --- catalog ---------------------------------------------------------------


class PriceView(BaseModel):
    id: int
    label: str
    amount_cents: int
    starts_at: date
    ends_at: date | None
    members_only: bool


class GrantView(BaseModel):
    id: int
    kind: str
    valid_from: date
    valid_to: date
    visit_count: int | None


class RuleView(BaseModel):
    id: int
    kind: str
    parameters: dict
    failure_message: str


class AdminProductView(BaseModel):
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
            prices=[PriceView.model_validate(x, from_attributes=True) for x in p.prices],
            grants=[
                GrantView(
                    id=g.id,
                    kind=g.kind.value,
                    valid_from=g.valid_from,
                    valid_to=g.valid_to,
                    visit_count=g.visit_count,
                )
                for g in p.grants
            ],
            rules=[
                RuleView(
                    id=r.id,
                    kind=r.kind.value,
                    parameters=r.parameters,
                    failure_message=r.failure_message,
                )
                for r in p.rules
            ],
        )


class ProductBody(BaseModel):
    name: str
    description: str = ""
    season_year: int
    sort_order: int = 0
    active: bool = True


class PriceBody(BaseModel):
    label: str = ""
    amount_cents: int
    starts_at: date
    ends_at: date | None = None
    members_only: bool = False


class GrantBody(BaseModel):
    kind: EntitlementKind
    valid_from: date
    valid_to: date
    visit_count: int | None = None


class RuleBody(BaseModel):
    kind: RuleKind
    parameters: dict = {}
    failure_message: str


class RolloverBody(BaseModel):
    from_year: int
    to_year: int


def _product(session, product_id: int) -> Product:
    try:
        return catalog.load_product(session, product_id)
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such product")


def _rejected(problem: Exception) -> HTTPException:
    return HTTPException(status.HTTP_400_BAD_REQUEST, str(problem))


@router.get("/catalog/options")
def catalog_options(admin: Admin) -> dict:
    return {
        "entitlement_kinds": [k.value for k in EntitlementKind],
        "rule_kinds": [
            {"kind": k.value, "parameters": catalog.RULE_PARAMETERS[k]} for k in RuleKind
        ],
    }


@router.get("/catalog/products")
def list_products(
    session: DatabaseSession, admin: Admin, season_year: int | None = None
) -> list[AdminProductView]:
    return [AdminProductView.of(p) for p in catalog.all_products(session, season_year)]


@router.post("/catalog/products", status_code=status.HTTP_201_CREATED)
def create_product(body: ProductBody, session: DatabaseSession, admin: Admin) -> AdminProductView:
    try:
        return AdminProductView.of(
            catalog.create_product(session, catalog.ProductInput(**body.model_dump()))
        )
    except catalog.CatalogRejected as why:
        raise _rejected(why)


@router.put("/catalog/products/{product_id}")
def update_product(
    product_id: int, body: ProductBody, session: DatabaseSession, admin: Admin
) -> AdminProductView:
    try:
        return AdminProductView.of(
            catalog.update_product(
                session, _product(session, product_id), catalog.ProductInput(**body.model_dump())
            )
        )
    except catalog.CatalogRejected as why:
        raise _rejected(why)


@router.post("/catalog/products/{product_id}/prices", status_code=status.HTTP_201_CREATED)
def add_price(
    product_id: int, body: PriceBody, session: DatabaseSession, admin: Admin
) -> AdminProductView:
    product = _product(session, product_id)
    try:
        catalog.add_price(session, product, catalog.PriceInput(**body.model_dump()))
    except catalog.CatalogRejected as why:
        raise _rejected(why)
    return AdminProductView.of(product)


@router.delete("/catalog/products/{product_id}/prices/{price_id}")
def remove_price(
    product_id: int, price_id: int, session: DatabaseSession, admin: Admin
) -> AdminProductView:
    product = _product(session, product_id)
    try:
        catalog.remove_price(session, product, price_id)
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such price")
    except catalog.CatalogRejected as why:
        raise _rejected(why)
    return AdminProductView.of(product)


@router.post("/catalog/products/{product_id}/grants", status_code=status.HTTP_201_CREATED)
def add_grant(
    product_id: int, body: GrantBody, session: DatabaseSession, admin: Admin
) -> AdminProductView:
    product = _product(session, product_id)
    try:
        catalog.add_grant(session, product, catalog.GrantInput(**body.model_dump()))
    except catalog.CatalogRejected as why:
        raise _rejected(why)
    return AdminProductView.of(product)


@router.delete("/catalog/products/{product_id}/grants/{grant_id}")
def remove_grant(
    product_id: int, grant_id: int, session: DatabaseSession, admin: Admin
) -> AdminProductView:
    product = _product(session, product_id)
    try:
        catalog.remove_grant(session, product, grant_id)
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such grant")
    return AdminProductView.of(product)


@router.post("/catalog/products/{product_id}/rules", status_code=status.HTTP_201_CREATED)
def add_rule(
    product_id: int, body: RuleBody, session: DatabaseSession, admin: Admin
) -> AdminProductView:
    product = _product(session, product_id)
    try:
        catalog.add_rule(session, product, body.kind, body.parameters, body.failure_message)
    except catalog.CatalogRejected as why:
        raise _rejected(why)
    return AdminProductView.of(product)


@router.delete("/catalog/products/{product_id}/rules/{rule_id}")
def remove_rule(
    product_id: int, rule_id: int, session: DatabaseSession, admin: Admin
) -> AdminProductView:
    product = _product(session, product_id)
    try:
        catalog.remove_rule(session, product, rule_id)
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such rule")
    return AdminProductView.of(product)


@router.post("/catalog/rollover", status_code=status.HTTP_201_CREATED)
def rollover(body: RolloverBody, session: DatabaseSession, admin: Admin) -> list[AdminProductView]:
    try:
        return [
            AdminProductView.of(p)
            for p in catalog.rollover_season(session, body.from_year, body.to_year)
        ]
    except catalog.CatalogRejected as why:
        raise _rejected(why)


# --- reports ---------------------------------------------------------------


class ParameterView(BaseModel):
    name: str
    label: str
    kind: str
    default: Any


class ReportView(BaseModel):
    name: str
    title: str
    description: str
    parameters: list[ParameterView]


class ReportRun(BaseModel):
    parameters: dict[str, Any] = {}


class ReportOutput(BaseModel):
    title: str
    columns: list[str]
    rows: list[list[Any]]


@router.get("/reports")
def list_reports(admin: Admin) -> list[ReportView]:
    return [
        ReportView(
            name=r.name,
            title=r.title,
            description=r.description,
            parameters=[ParameterView(**p.__dict__) for p in r.parameters],
        )
        for r in REPORTS.values()
    ]


def _run(session, name: str, parameters: dict[str, Any]):
    report = REPORTS.get(name)
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such report")
    try:
        return report, report.run(session, parameters)
    except (ValueError, TypeError) as why:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"bad parameters: {why}")


@router.post("/reports/{name}/run")
def run_report(name: str, body: ReportRun, session: DatabaseSession, admin: Admin) -> ReportOutput:
    report, result = _run(session, name, body.parameters)
    return ReportOutput(title=report.title, columns=result.columns, rows=result.rows)


@router.post("/reports/{name}/csv")
def report_csv(name: str, body: ReportRun, session: DatabaseSession, admin: Admin) -> Response:
    _, result = _run(session, name, body.parameters)
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(result.columns)
    writer.writerows(result.rows)
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"content-disposition": f'attachment; filename="{name}.csv"'},
    )


# --- waiver history --------------------------------------------------------


class TemplateView(BaseModel):
    id: int
    version: int
    title: str
    body_text: str
    published_at: object


class ResetView(BaseModel):
    reset_at: object
    reason: str


@router.get("/waiver/history")
def waiver_history(session: DatabaseSession, admin: Admin) -> dict:
    templates = session.scalars(
        select(WaiverTemplate).order_by(WaiverTemplate.version.desc())
    ).all()
    resets = session.scalars(
        select(WaiverReset).order_by(WaiverReset.reset_at.desc()).limit(20)
    ).all()
    return {
        "templates": [
            {
                "id": t.id,
                "version": t.version,
                "title": t.title,
                "body_text": t.body_text,
                "published_at": t.published_at.isoformat(),
            }
            for t in templates
        ],
        "resets": [{"reset_at": r.reset_at.isoformat(), "reason": r.reason} for r in resets],
    }
