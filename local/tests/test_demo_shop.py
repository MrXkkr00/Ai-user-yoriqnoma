"""demo_shop smoke tests: every role reaches its own API, nobody but admin reaches /api/admin."""

from __future__ import annotations

import re
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest
from demo_shop import config, db
from demo_shop.main import create_app, init_db
from demo_shop.seed import OTHER_CUSTOMER, STAFF_ACCOUNTS
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("DEMO_SHOP_VAR", str(tmp_path))
    monkeypatch.delenv("MAILPIT_SMTP", raising=False)
    db.reset_engine()
    init_db(reset=True)
    with TestClient(create_app()) as c:
        yield c
    db.reset_engine()


def login(client: TestClient, role: str) -> TestClient:
    email, password, _ = STAFF_ACCOUNTS[role]
    assert client.post("/api/auth/login", json={"email": email, "password": password}).is_success
    return client


def register_customer(client: TestClient, email: str = "aziza@example.test") -> TestClient:
    body = {
        "full_name": "Aziza Rahimova",
        "email": email,
        "phone": "+998901112233",
        "password": "Sinov-parol-1",
    }
    assert client.post("/api/auth/register", json=body).status_code == 201
    mail = sorted(config.mail_dir().glob("*.eml"))[-1].read_text(encoding="utf-8")
    code = re.search(r"kodi: (\d{6})", mail)
    assert code, mail
    assert client.post("/api/auth/verify-email", json={"email": email, "code": code[1]}).is_success
    login_body = {"email": email, "password": "Sinov-parol-1"}
    assert client.post("/api/auth/login", json=login_body).is_success
    return client


ROLE_API = {
    "customer": "/api/orders",
    "manager": "/api/staff/orders",
    "courier": "/api/courier/orders",
}


def as_role(client: TestClient, role: str) -> TestClient:
    return register_customer(client) if role == "customer" else login(client, role)


@pytest.mark.parametrize("role", sorted(ROLE_API))
def test_each_role_reaches_only_its_own_api(client: TestClient, role: str) -> None:
    as_role(client, role)
    for other_role, path in ROLE_API.items():
        expected = 200 if other_role == role else 403
        assert client.get(path).status_code == expected, (role, path)


@pytest.mark.parametrize("role", ["guest", "customer", "manager", "courier"])
def test_admin_api_is_closed_to_everyone_but_admin(client: TestClient, role: str) -> None:
    if role != "guest":
        as_role(client, role)
    for path in ("/api/admin/users", "/api/admin/roles"):
        assert client.get(path).status_code in (401, 403)
    assert client.post("/api/admin/orders/1/refund").status_code in (401, 403)


def test_admin_api_opens_for_admin(client: TestClient) -> None:
    login(client, "admin")
    assert client.get("/api/admin/users").status_code == 200


def test_customer_never_sees_other_customers_orders(client: TestClient) -> None:
    register_customer(client)
    assert client.get("/api/orders").json() == []
    assert client.get("/api/orders/1").status_code == 404


def test_manager_sees_other_customer_with_attachment(client: TestClient) -> None:
    login(client, "manager")
    orders = client.get("/api/staff/orders").json()
    assert {o["customer_name"] for o in orders} == {OTHER_CUSTOMER[0]}
    first = client.get("/api/staff/orders/1").json()
    assert first["attachment_url"]
    image = client.get(first["attachment_url"])
    assert image.headers["content-type"] == "image/png"


def test_order_status_machine(client: TestClient) -> None:
    register_customer(client)
    body = {
        "product_id": 1,
        "quantity": 2,
        "address": "Toshkent, Yunusobod 4",
        "phone": "+998901112233",
    }
    order = client.post("/api/orders", json=body).json()
    assert order["status"] == "new"
    assert client.post(f"/api/orders/{order['id']}/pay").json()["status"] == "paid"
    assert client.post(f"/api/orders/{order['id']}/cancel").status_code == 409
    history = client.get(f"/api/orders/{order['id']}/history").json()
    assert [h["status"] for h in history] == ["new", "paid"]


def test_validation_rules(client: TestClient) -> None:
    short = {"full_name": "Al", "email": "x@y.uz", "phone": "123", "password": "short"}
    errors = client.post("/api/auth/register", json=short).json()["detail"]
    assert {e["loc"][-1] for e in errors} == {"full_name", "phone", "password"}
    register_customer(client)
    big = {"product_id": 1, "quantity": 100, "address": "Toshkent 1", "phone": "+998901112233"}
    assert client.post("/api/orders", json=big).status_code == 422


def test_login_requires_verified_email(client: TestClient) -> None:
    body = {
        "full_name": "Aziza",
        "email": "a@b.uz",
        "phone": "+998901112233",
        "password": "12345678",
    }
    client.post("/api/auth/register", json=body)
    login_body = {"email": "a@b.uz", "password": "12345678"}
    assert client.post("/api/auth/login", json=login_body).status_code == 403


def test_spa_fallback_serves_index(client: TestClient) -> None:
    response = client.get("/app/orders/5")
    assert response.status_code == 200
    assert '<div id="root">' in response.text


def test_built_frontend_is_committed() -> None:
    assert (config.WEB_DIST / "index.html").is_file()


@pytest.mark.slow
def test_demo_shop_server_starts(demo_shop_url: str) -> None:
    with urllib.request.urlopen(demo_shop_url + "catalog") as resp:
        assert resp.status == 200
        assert b'<div id="root">' in resp.read()
