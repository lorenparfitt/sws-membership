"""Render docs/api.md from the routes themselves.

The routes are the point of truth: their paths, auth classes, parameter and
response models, and docstrings. This module reads them and writes one
Markdown page, so the page cannot drift from the code. A test compares the
rendered text with the committed file.
"""

from __future__ import annotations

import inspect
import types
import typing
from dataclasses import dataclass
from typing import Any

from ninja import NinjaAPI
from ninja.constants import NOT_SET

from sws_membership.accounts.auth import admin_auth, member_auth, staff_auth

ROLE_OF_AUTH = ((member_auth, "member"), (staff_auth, "staff"), (admin_auth, "admin"))
ROLE_ORDER = {"none": 0, "member": 1, "staff": 2, "admin": 3}
DEVELOPMENT_ONLY_PREFIX = "/api/payments/fake"


@dataclass(frozen=True)
class Route:
    method: str
    path: str
    role: str
    tag: str
    does: str
    request: str
    response: str
    hidden: bool


def _type_name(annotation: Any) -> str:
    """A type as a reader writes it: list[OrderView], int or None, str."""
    if annotation is None or annotation is type(None):
        return "None"
    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)
    if origin in (typing.Union, types.UnionType):
        return " or ".join(_type_name(a) for a in args)
    if origin is not None:
        inner = ", ".join(_type_name(a) for a in args)
        return f"{_type_name(origin)}[{inner}]"
    return getattr(annotation, "__name__", str(annotation))


def _role(op, router) -> str:
    callbacks = op.auth_callbacks or (router.auth if router.auth not in (NOT_SET, None) else [])
    if not isinstance(callbacks, (list, tuple)):
        callbacks = [callbacks]
    for callback in callbacks:
        for auth, role in ROLE_OF_AUTH:
            if callback is auth:
                return role
    return "none" if not callbacks else type(callbacks[0]).__name__


def _request(op) -> str:
    parts: list[str] = []
    for model in op.models:
        kind = model.__name__
        fields = model.model_fields
        if kind == "PathParams":
            continue
        if kind == "QueryParams":
            parts.append(
                "query " + ", ".join(f"{n}: {_type_name(f.annotation)}" for n, f in fields.items())
            )
        elif kind == "BodyParams":
            parts.append("body " + ", ".join(_type_name(f.annotation) for f in fields.values()))
        elif kind == "FileParams":
            parts.append("file " + ", ".join(fields))
        elif kind == "FormParams":
            parts.append(
                "form " + ", ".join(f"{n}: {_type_name(f.annotation)}" for n, f in fields.items())
            )
    return "; ".join(parts) or "-"


def _untyped_response(op) -> str:
    """A route with no response model returns what its view does: JSON for a
    dict or list annotation, otherwise a file or text (HttpResponse)."""
    returns = inspect.signature(op.view_func).return_annotation
    if returns is inspect.Signature.empty:
        return "bytes or text"
    origin = typing.get_origin(returns) or returns
    if origin is dict:
        return "JSON object"
    if origin is list:
        return "JSON list"
    return "bytes or text"


def _response(op) -> str:
    if not op.response_models:
        return "-"
    parts = []
    for code, model in sorted(op.response_models.items()):
        if model is NOT_SET or type(model) is type(NOT_SET):
            parts.append(f"{code} {_untyped_response(op)}")
        elif model is None:
            parts.append(f"{code} empty")
        else:
            inner = model.model_fields.get("response")
            named = _type_name(inner.annotation) if inner else _type_name(model)
            parts.append(f"{code} {'JSON object' if named == 'dict' else named}")
    return "; ".join(parts)


def _does(op) -> str:
    doc = inspect.getdoc(op.view_func)
    if doc:
        return " ".join(doc.split("\n\n")[0].split())
    return op.summary


def routes_of(api: NinjaAPI) -> list[Route]:
    api.urls  # noqa: B018 -- building the URL patterns binds router-level auth to each operation
    found: list[Route] = []
    for prefix, router in api._routers:
        for path, path_view in router.path_operations.items():
            for op in path_view.operations:
                full = "/api" + prefix + path
                for method in op.methods:
                    found.append(
                        Route(
                            method=method,
                            path=full,
                            role=_role(op, router),
                            tag=(op.tags or router.tags or ["other"])[0],
                            does=_does(op),
                            request=_request(op),
                            response=_response(op),
                            hidden=not op.include_in_schema,
                        )
                    )
    return sorted(found, key=lambda r: (r.path, r.method))


def _json_type(schema: dict, components: dict) -> str:
    if "$ref" in schema:
        return schema["$ref"].rsplit("/", 1)[-1]
    if "anyOf" in schema:
        options = [_json_type(s, components) for s in schema["anyOf"]]
        if "null" in options:
            options = [o for o in options if o != "null"] + ["null"]
        return " or ".join(options)
    if "enum" in schema:
        return " | ".join(f"`{v}`" for v in schema["enum"])
    kind = schema.get("type", "any")
    if kind == "array":
        return f"list of {_json_type(schema.get('items', {}), components)}"
    if kind == "string" and schema.get("format"):
        return schema["format"]
    if kind == "object" and "additionalProperties" in schema:
        inner = schema["additionalProperties"]
        return "object" if inner is True else f"object of {_json_type(inner, components)}"
    return kind


def _shapes(api: NinjaAPI) -> list[str]:
    schema = api.get_openapi_schema()
    components = schema["components"]["schemas"]
    lines: list[str] = []
    for name in sorted(components):
        definition = components[name]
        if definition.get("type") != "object" or not definition.get("properties"):
            if "enum" in definition:
                lines.append(f"- **{name}**: {_json_type(definition, components)}")
            continue
        required = set(definition.get("required", []))
        fields = ", ".join(
            f"{field}{'' if field in required else '?'}: {_json_type(spec, components)}"
            for field, spec in definition["properties"].items()
        )
        lines.append(f"- **{name}**: {fields}")
    return lines


HEADER = """# API

Every route of the JSON API, generated from the routes themselves by
`uv run doit api_doc`. Edit the route docstrings and models, not this file;
a test fails when the two disagree. The interactive version, with every
field and a try-it button, is served at `/api/docs`, and the OpenAPI
document at `/api/openapi.json`.

## Conventions

- **Who** is the role the route requires. `none` is open; `member` is any
  signed-in member; `staff` is the staff or admin role; `admin` is the admin
  role. No session answers 401, a session without the role 403.
- Sessions are cookies set by the sign-in routes. Every write (POST, PUT,
  DELETE) must echo the `csrftoken` cookie in an `X-CSRFToken` header; the
  processor webhook and the sign-in routes are exempt.
- Bodies and responses are JSON unless the response says bytes or text.
  Money is integer cents in CAD. Dates are ISO 8601.
- A request that is well formed but not allowed answers 409. When the cause
  is eligibility (a product the member cannot buy), the body is
  `{"detail": {"refused": {"<product or order>": ["<reason>", ...]}}}`;
  otherwise `detail` is a sentence. 404 is both missing and not yours.
- Routes marked *development only* exist only when the fake payment
  processor is configured.
"""


def render(api: NinjaAPI) -> str:
    routes = routes_of(api)
    out = [HEADER]
    by_tag: dict[str, list[Route]] = {}
    for route in routes:
        by_tag.setdefault(route.tag, []).append(route)
    for tag in sorted(by_tag):
        out.append(f"## {tag}\n")
        out.append("| Method | Path | Who | Does | Request | Response |")
        out.append("|---|---|---|---|---|---|")
        for r in by_tag[tag]:
            who = r.role
            if r.path.startswith(DEVELOPMENT_ONLY_PREFIX):
                who += " (development only)"
            does = r.does + (" Not in the OpenAPI document." if r.hidden else "")
            cells = (r.method, f"`{r.path}`", who, does, r.request, r.response)
            out.append("| " + " | ".join(c.replace("|", r"\|") for c in cells) + " |")
        out.append("")
    out.append("## Shapes\n")
    out.append("Request and response bodies. A trailing `?` marks a field the sender may omit.\n")
    out.extend(_shapes(api))
    out.append("")
    return "\n".join(out)


def render_api_doc() -> str:
    from sws_membership.api import api

    return render(api)
