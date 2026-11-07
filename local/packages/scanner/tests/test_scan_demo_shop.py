"""QM-1 on demo_shop: roles, 100% of each role's paths, no admin path anywhere else."""

from __future__ import annotations

import pytest

from yoriqnoma_scanner import overrides
from yoriqnoma_scanner.api import ScanResult
from yoriqnoma_schemas import Blueprint

ROLE_PAGES = {
    "guest": {
        "/",
        "/catalog",
        "/catalog/:id",
        "/register",
        "/login",
        "/verify-email",
        "/forgot-password",
    },
    "customer": {
        "/app/dashboard",
        "/app/profile",
        "/app/settings",
        "/app/orders",
        "/app/orders/new",
        "/app/orders/:id",
        "/app/messages",
        "/app/account/delete",
    },
    "manager": {
        "/app/dashboard",
        "/app/profile",
        "/app/settings",
        "/staff/orders",
        "/staff/orders/:id",
    },
    "courier": {
        "/app/dashboard",
        "/app/profile",
        "/app/settings",
        "/courier",
        "/courier/orders/:id",
    },
}


def test_roles_are_found_and_classified(demo_scan: ScanResult) -> None:
    kinds = {r.id: r.kind for r in demo_scan.blueprint.roles}

    assert kinds == {
        "guest": "guest",
        "customer": "role",
        "manager": "role",
        "courier": "role",
        "admin": "excluded",
    }
    customer = demo_scan.blueprint.role("customer")
    assert customer is not None and customer.self_signup
    assert not demo_scan.blueprint.role("manager").self_signup  # type: ignore[union-attr]


@pytest.mark.parametrize("role", sorted(ROLE_PAGES))
def test_every_page_of_each_role_is_found(demo_scan: ScanResult, role: str) -> None:
    pages = [p for p in demo_scan.blueprint.pages if p.kind == "page"]
    if role == "guest":
        found = {p.path for p in pages if p.access == "guest"}
    else:
        found = {p.path for p in pages if role in p.roles}

    assert found == ROLE_PAGES[role]


def test_admin_paths_only_in_excluded(demo_scan: ScanResult) -> None:
    bp = demo_scan.blueprint
    kept = {p.path for p in bp.pages}

    assert not [p for p in kept if p.startswith(("/admin", "/api/admin"))]
    excluded = {p.path for p in bp.excluded}
    assert {"/admin", "/admin/users", "/admin/roles", "/api/admin/users"} <= excluded
    for flow in bp.flows:
        for step in flow.steps:
            assert not (step.path or "").startswith(("/admin", "/api/admin")), flow.id
    assert all(not n["path"].startswith("/admin") for n in bp.nav)


def test_order_entity_actions_and_status_reachability(demo_scan: ScanResult) -> None:
    order = demo_scan.blueprint.entity("order")
    assert order is not None

    assert set(order.actions) == {
        "create",
        "list",
        "view",
        "pay",
        "cancel",
        "download_invoice",
        "ship",
        "deliver",
    }
    reach = {s.value: s.reachable_by for s in order.statuses}
    assert reach == {
        "new": ["customer"],
        "paid": ["customer"],
        "shipped": ["manager"],
        "delivered": ["courier"],
        "cancelled": ["customer"],
        "refunded": [],
    }
    assert order.owner_field == "user_id"
    assert {"customer_name", "phone", "address"} <= set(order.pii_fields)
    labels = {s.value: s.label for s in order.statuses}
    assert labels["shipped"] == "Jo'natilgan"


def test_flows_requires_and_stages(demo_scan: ScanResult) -> None:
    bp = demo_scan.blueprint
    flows = {f.id: f for f in bp.flows}

    assert flows["customer.register"].steps[-2].action == "verify_email"
    assert "e2e/test_register.py" in flows["customer.register"].source
    assert "customer.order.pay" in flows["manager.order.ship"].requires
    assert "manager.order.ship" in flows["courier.order.deliver"].requires
    assert flows["customer.order.cancel"].steps[-1].destructive
    assert flows["customer.order.pay"].stage == "payment"
    assert flows["customer.order.pay"].steps[-1].payment
    assert flows["customer.delete_account"].stage == "exit"
    order = [f.id for f in bp.topo_order()]
    assert order.index("customer.order.create") < order.index("customer.order.pay")
    assert order[-1].endswith("delete_account") or "customer.delete_account" in order
    customer_flows = [f for f in bp.topo_order() if f.role == "customer"]
    assert customer_flows[-1].id == "customer.delete_account"


def test_blueprint_round_trips_through_the_schema(demo_scan: ScanResult) -> None:
    raw = demo_scan.blueprint.model_dump_json()

    assert Blueprint.model_validate_json(raw) == demo_scan.blueprint


def test_report_mentions_roles_and_skipped(demo_scan: ScanResult) -> None:
    report = demo_scan.report_md

    assert "## Rollar" in report and "`admin`" in report and "excluded" in report
    assert "`.env`" in report


def test_overrides_only_reduce(demo_scan: ScanResult) -> None:
    bp = demo_scan.blueprint
    result, notes = overrides.apply(
        bp,
        {
            "exclude_flows": ["customer.order.create"],
            "exclude_pages": ["/app/messages"],
            "rename_flows": {"customer.login": "Kabinetga kirish"},
        },
    )
    ids = {f.id for f in result.flows}

    assert "customer.order.create" not in ids
    assert "customer.order.pay" not in ids  # depends on the excluded flow
    assert "manager.order.ship" not in ids
    assert "customer.message.list" not in ids  # opens the excluded page
    assert result.flow("customer.login").title == "Kabinetga kirish"  # type: ignore[union-attr]
    assert len(result.excluded) == len(bp.excluded)
    assert any("bog'liq" in n for n in notes)


def test_overrides_cannot_bring_back_excluded(demo_scan: ScanResult) -> None:
    with pytest.raises(ValueError, match="noma'lum"):
        overrides.apply(demo_scan.blueprint, {"include_pages": ["/admin"]})
