"""Admin provisioning rules (local modes 2 and 3): what the admin session may touch."""

from __future__ import annotations

from pathlib import Path

import pytest

from yoriqnoma_core.provision.base import CreatedUser, Ledger, classify_role
from yoriqnoma_core.provision.guard import ProvisionGuard, create_target, object_key
from yoriqnoma_core.safety.url_guard import HostGuard

BASE = "http://127.0.0.1:8800/"


@pytest.fixture
def guard() -> ProvisionGuard:
    return ProvisionGuard(BASE, HostGuard(allow_private=True), signed_in=True)


def test_object_and_create_paths() -> None:
    assert object_key("/admin/helpdesk/user/17/delete/") == ("user", "17")
    assert object_key("/api/admin/users/7") == ("user", "7")
    assert object_key("/admin/") is None
    assert create_target("/admin/helpdesk/user/add/") == "user"
    assert create_target("/api/admin/users") == "user"
    assert create_target("/admin/auth/group/add/") is None
    assert create_target("/api/admin/settings") is None


@pytest.mark.parametrize(
    ("method", "path", "allowed"),
    [
        ("GET", "/admin/helpdesk/ticket/3/change/", True),  # reading is allowed
        ("POST", "/admin/helpdesk/user/add/", True),  # creating a user
        ("POST", "/api/admin/users", True),
        ("DELETE", "/api/admin/users/1", False),  # someone else
        ("PUT", "/api/admin/users/1/role", False),
        ("POST", "/admin/helpdesk/ticket/3/delete/", False),
        ("PUT", "/api/admin/settings", False),  # site settings
        ("POST", "/admin/auth/group/add/", False),  # roles and permissions
        ("POST", "/api/admin/orders/5/refund", False),
        ("GET", "/admin/logout/", False),
        ("POST", "/admin/logout/", False),
    ],
)
def test_guard_writes(guard: ProvisionGuard, method: str, path: str, allowed: bool) -> None:
    assert guard.decide(method, BASE.rstrip("/") + path, "fetch")[0] is allowed


def test_guard_allows_only_what_the_tool_made(guard: ProvisionGuard) -> None:
    guard.allow("users", "42")
    assert guard.decide("DELETE", BASE + "api/admin/users/42", "fetch")[0]
    assert guard.decide("POST", BASE + "admin/app/user/42/change/", "document")[0]
    assert not guard.decide("DELETE", BASE + "api/admin/users/43", "fetch")[0]
    assert not guard.decide("DELETE", BASE + "api/orders/42", "fetch")[0]  # other model
    guard.allow("order", "42")
    assert guard.decide("DELETE", BASE + "api/orders/42", "fetch")[0]


def test_guard_blocks_bulk_actions_and_other_sites(guard: ProvisionGuard) -> None:
    body = "csrfmiddlewaretoken=x&action=delete_selected&_selected_action=1&_selected_action=2"
    assert not guard.decide("POST", BASE + "admin/app/user/", "document", body)[0]
    assert not guard.decide("POST", "https://evil.example/collect", "fetch")[0]
    assert guard.decide("GET", "https://cdn.example/x.css", "stylesheet")[0]


def test_login_only_before_signing_in() -> None:
    fresh = ProvisionGuard(BASE, HostGuard(allow_private=True))
    assert fresh.decide("POST", BASE + "admin/login/", "document")[0]
    fresh.signed_in = True
    assert not fresh.decide("POST", BASE + "api/auth/login2", "fetch")[0]


@pytest.mark.parametrize(
    ("label", "value", "kind"),
    [
        ("Menejer", "manager", "role"),
        ("Kuryer", "courier", "role"),
        ("Administrator", "admin", "excluded"),
        ("Super admin", "superadmin", "excluded"),
        ("Админ", "x", "excluded"),
        ("", "", "excluded"),
    ],
)
def test_role_classification(label: str, value: str, kind: str) -> None:
    assert classify_role(label, value, "test", "role").kind == kind


def test_ledger_survives_a_restart_and_keeps_no_password(tmp_path: Path) -> None:
    path = tmp_path / "provision.json"
    ledger = Ledger(path)
    ledger.add(CreatedUser("manager", "A", "m.a@x.test", "m.a@x.test", "17", "user"))
    again = Ledger(path)
    assert [u.remote_id for u in again.pending()] == ["17"]
    again.users[0].cleaned = True
    again.save()
    assert Ledger(path).pending() == []
    assert "password" not in path.read_text(encoding="utf-8")
