"""Scout pieces without a browser (T26, T27): templates, JS routes, forms, API inference,
blueprint building (default-deny, admin excluded) and the A+B merge."""

from __future__ import annotations

import json
from typing import Any

import pytest

from jobs.tests.samples import EXAMPLES
from scout.auth_flow import AuthForms, auth_flows, find_auth_forms
from scout.blueprint_builder import build
from scout.crawler import CrawlResult, PageSeen
from scout.forms import classify, data_kind, fill_steps, signup_roles, to_form
from scout.js_routes import (
    api_paths_from_js,
    routes_from_js,
    routes_from_source_map,
    source_map_url,
)
from scout.merge import merge
from scout.network_infer import ApiCall, infer_entities, json_key_names
from scout.preflight import parse_sitemap
from scout.urls import clean_url, template_path
from yoriqnoma_schemas import Blueprint

BASE = "https://shop.example.uz/"


@pytest.mark.parametrize(
    ("path", "template"),
    [
        ("/app/orders/123", "/app/orders/:id"),
        ("/x/550e8400-e29b-41d4-a716-446655440000/edit", "/x/:id/edit"),
        ("/news/2026-yil-yangi-qonun-12", "/news/:slug"),
        ("/catalog", "/catalog"),
        ("/", "/"),
    ],
)
def test_template_path(path: str, template: str) -> None:
    assert template_path(path) == template


def test_clean_url() -> None:
    assert clean_url("/app#x", BASE) == "https://shop.example.uz/app"
    assert clean_url("https://evil.uz/", BASE) is None
    assert clean_url("mailto:a@b.uz", BASE) is None
    assert clean_url("/static/app.js", BASE) is None


JS = """
const routes = createBrowserRouter([{path: "/app/orders", element: x},
  {path: "/app/orders/:id"}, {path: "/admin/users"}]);
jsx(Route, {path: "/app/messages"}); navigate("/app/profile"); fetch(`/api/orders/${id}/cancel`);
<Route path="/app/settings" element={<S/>} /> <Link to="/catalog">x</Link>
//# sourceMappingURL=index.js.map
"""


def test_routes_from_js_and_source_maps() -> None:
    routes = routes_from_js(JS)
    assert {
        "/app/orders",
        "/app/orders/:id",
        "/app/messages",
        "/app/profile",
        "/app/settings",
        "/catalog",
        "/admin/users",
    } <= routes
    assert api_paths_from_js(JS) == {"/api/orders/:id/cancel"}
    assert source_map_url(JS, "https://shop.example.uz/assets/index.js") == (
        "https://shop.example.uz/assets/index.js.map"
    )
    assert source_map_url("//# sourceMappingURL=https://cdn.x/a.map", BASE + "a.js") is None
    pages, apis = routes_from_source_map(json.dumps({"sourcesContent": [JS, None]}))
    assert "/app/orders" in pages and "/api/orders/:id/cancel" in apis


LOGIN = {
    "index": 0,
    "submit": "Kirish",
    "action": "",
    "method": "post",
    "fields": [
        {"name": "email", "type": "email", "label": "Email", "required": True},
        {"name": "password", "type": "password", "label": "Parol", "required": True},
    ],
}
REGISTER = {
    "index": 0,
    "submit": "Ro'yxatdan o'tish",
    "action": "",
    "method": "post",
    "fields": [
        {
            "name": "full_name",
            "type": "text",
            "label": "To'liq ism",
            "required": True,
            "minlength": 3,
        },
        {"name": "email", "type": "email", "label": "Email", "required": True},
        {"name": "phone", "type": "tel", "label": "Telefon", "pattern": "\\+998\\d{9}"},
        {"name": "account_type", "type": "radio", "label": "Xaridor", "options": ["Xaridor"]},
        {"name": "account_type", "type": "radio", "label": "Sotuvchi", "options": ["Sotuvchi"]},
        {"name": "password", "type": "password", "label": "Parol", "minlength": 8},
    ],
}
ORDER = {
    "index": 0,
    "submit": "Buyurtma berish",
    "action": "",
    "method": "post",
    "fields": [
        {"name": "quantity", "type": "number", "label": "Miqdor", "min": "1", "max": "99"},
        {"name": "address", "type": "text", "label": "Manzil", "required": True},
    ],
}


def test_forms_classification_and_steps() -> None:
    assert classify(LOGIN, "/login") == "login"
    assert classify(REGISTER, "/register") == "register"
    assert classify(ORDER, "/app/orders/new") == "other"
    form = to_form(REGISTER, "/register", "register_0")
    phone = next(f for f in form.fields if f.name == "phone")
    assert phone.rules == "regex:\\+998\\d{9}" and data_kind(phone) == "fake:phone_uz"
    radio = next(f for f in form.fields if f.name == "account_type")
    assert radio.options == ["Xaridor", "Sotuvchi"]
    assert signup_roles(REGISTER) == ["Xaridor", "Sotuvchi"]
    order = to_form(ORDER, "/app/orders/new", "o")
    assert order.fields[0].rules == "min:1|max:99" and data_kind(order.fields[1]) == "fake:address"
    login_steps = fill_steps(to_form(LOGIN, "/login", "l"), login=True)
    assert [s.data for s in login_steps] == ["fake:email", "fake:password"]


def test_network_inference_keeps_only_key_names() -> None:
    calls = [
        ApiCall("GET", "/api/orders", 200, ["id", "status", "customer_name", "phone", "user_id"]),
        ApiCall("POST", "/api/orders", 201, []),
        ApiCall("GET", "/api/orders/7", 200, []),
        ApiCall("POST", "/api/orders/7/cancel", 200, []),
        ApiCall("GET", "/api/me", 200, ["email"]),
        ApiCall("DELETE", "/api/orders/7", 403, []),
    ]
    (order,) = infer_entities(calls)
    assert order.name == "order" and order.actions == ["cancel", "create", "list", "view"]
    assert {"customer_name", "phone"} <= set(order.pii_fields)
    assert order.status_field == "status" and order.owner_field == "user_id"
    keys = json_key_names({"items": [{"name": "Ali", "phone": "+998901112233"}], "total": 1})
    assert keys == ["items", "name", "phone", "total"]  # names, never the values


def test_sitemap_parsing() -> None:
    xml = (
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        "<url><loc>https://s.uz/a</loc></url><url><loc>https://s.uz/b</loc></url></urlset>"
    )
    assert parse_sitemap(xml) == (["https://s.uz/a", "https://s.uz/b"], [])
    assert parse_sitemap("<broken") == ([], [])


def _page(tpl: str, **kw: Any) -> PageSeen:
    return PageSeen(url=BASE.rstrip("/") + tpl, template=tpl, title=kw.pop("title", tpl), **kw)


def _crawls() -> tuple[CrawlResult, CrawlResult]:
    guest = CrawlResult()
    guest.pages = {
        "/": _page("/", title="Demo Shop"),
        "/catalog": _page("/catalog", title="Katalog — Demo Shop"),
        "/login": _page("/login", forms=[LOGIN]),
        "/register": _page("/register", forms=[REGISTER]),
        "/app/orders": _page("/app/orders", login_wall=True, redirected_to="/login"),
        "/admin": _page("/admin", login_wall=True, redirected_to="/login"),
    }
    guest.nav = [{"label": "Katalog", "path": "/catalog"}, {"label": "Admin", "path": "/admin"}]
    member = CrawlResult()
    member.pages = {
        "/app/orders": _page("/app/orders", title="Buyurtmalarim"),
        "/app/orders/new": _page("/app/orders/new", title="Yangi buyurtma", forms=[ORDER]),
        "/app/orders/:id": _page("/app/orders/:id", title="Ali Valiyev buyurtmasi"),
    }
    member.api_calls = [ApiCall("POST", "/api/orders", 201, ["id", "status"])]
    return guest, member


async def _auth(guest: CrawlResult) -> AuthForms:
    return await find_auth_forms(guest)


def test_discovered_blueprint_is_default_deny() -> None:
    import asyncio

    guest, member = _crawls()
    auth = asyncio.run(_auth(guest))
    bp = build(
        base_url=BASE,
        project="shop",
        role="customer",
        role_label="Mijoz",
        self_signup=True,
        guest=guest,
        member=member,
        js_pages={"/app/secret", "/admin/users"},
        auth=auth,
        signup_choices=["Xaridor"],
        agent_flows=[],
        probed_forms={},
        verify_email=True,
        extra_deny=[],
        public_values=set(),
    )
    Blueprint.model_validate(bp.model_dump())  # schema-valid
    access = {p.path: p.access for p in bp.pages}
    assert access["/catalog"] == "guest" and access["/app/orders"] == "roles"
    excluded = {p.path for p in bp.excluded}
    assert {"/admin", "/admin/users", "/app/secret"} <= excluded  # admin and JS-only pages
    roles = {r.id: r.kind for r in bp.roles}
    assert (
        roles["admin"] == "excluded" and roles["customer"] == "role" and roles["xaridor"] == "role"
    )
    ids = {f.id for f in bp.flows}
    assert {"customer.register", "customer.login"} <= ids
    register = next(f for f in bp.flows if f.id == "customer.register")
    assert register.steps[-1].action == "verify_email"
    assert any(f.action == "submit" and f.role == "customer" for f in bp.flows)
    assert all("admin" not in (s.path or "") for f in bp.flows for s in f.steps)
    assert not any("Ali Valiyev" in f.title for f in bp.flows)  # detail page titles are generic
    assert all(n["path"] != "/admin" for n in bp.nav)
    assert bp.entities[0].name == "order" and bp.entities[0].created_by == ["customer"]


def test_role_with_given_accounts_has_no_sign_up_flow() -> None:
    import asyncio

    guest, member = _crawls()
    bp = build(
        base_url=BASE,
        project="shop",
        role="manager",
        role_label="Menejer",
        self_signup=False,
        guest=guest,
        member=member,
        js_pages=set(),
        auth=asyncio.run(_auth(guest)),
        signup_choices=[],
        agent_flows=[],
        probed_forms={},
        verify_email=False,
        extra_deny=["/private*"],
        public_values=set(),
    )
    assert "manager.register" not in {f.id for f in bp.flows}
    login = next(f for f in bp.flows if f.id == "manager.login")
    assert login.requires == [] and "/private*" in bp.policy.deny_paths


def test_auth_flows_shape() -> None:
    import asyncio

    guest, _ = _crawls()
    flows = auth_flows("customer", asyncio.run(_auth(guest)), verify_email=False)
    login = next(f for f in flows if f.action == "login")
    assert login.requires == ["customer.register"]
    assert login.steps[-1].action == "expect_url" and login.steps[-1].path.startswith("re:")  # type: ignore[union-attr]


def test_merge_code_wins_and_adds_only_new() -> None:
    import asyncio

    code = Blueprint.model_validate_json((EXAMPLES / "blueprint.example.json").read_text("utf-8"))
    guest, member = _crawls()
    found = build(
        base_url=BASE,
        project="shop",
        role="customer",
        role_label="Mijoz",
        self_signup=True,
        guest=guest,
        member=member,
        js_pages=set(),
        auth=asyncio.run(_auth(guest)),
        signup_choices=[],
        agent_flows=[],
        probed_forms={},
        verify_email=False,
        extra_deny=[],
        public_values=set(),
    )
    merged, notes = merge(code, found)

    assert merged.source == "merged" and notes[0].startswith("A+B")
    code_paths = {p.path for p in code.pages}
    assert code_paths <= {p.path for p in merged.pages}
    assert {r.id for r in merged.roles} == {r.id for r in code.roles}
    assert {f.id for f in code.flows} <= {f.id for f in merged.flows}
    assert not any(
        f.action in {"register", "login"} and f.source.startswith("discovered")
        for f in merged.flows
        if f.id not in {x.id for x in code.flows}
    )
    excluded_code = {p.path for p in code.excluded}
    assert not ({p.path for p in merged.pages} & excluded_code)  # code's default-deny kept


def test_confirmation_step_uses_the_code_form() -> None:
    from scout.auth_flow import verify_steps_for

    code_form = {
        "index": 0,
        "submit": "Tasdiqlash",
        "fields": [
            {"name": "email", "type": "email", "label": "Email"},
            {"name": "code", "type": "text", "label": "Tasdiqlash kodi"},
        ],
    }
    steps = verify_steps_for([code_form])
    assert [s.action for s in steps] == ["verify_email", "click"]
    assert steps[0].target is not None and steps[0].target.label == "Tasdiqlash kodi"
    assert [s.action for s in verify_steps_for([])] == ["verify_email"]  # a link in the mail
