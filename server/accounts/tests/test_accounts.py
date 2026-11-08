"""Server users (TZ FR-SV2, SEC-15, SEC-17): sign-up, sign-in, limited login attempts."""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

pytestmark = pytest.mark.django_db


def test_register_logs_in_and_goes_to_domains() -> None:
    client = Client()
    response = client.post(
        reverse("register"),
        {
            "username": "nodira",
            "email": "Nodira@Example.uz",
            "password1": "Uzun-parol-2026!",
            "password2": "Uzun-parol-2026!",
        },
    )
    assert response.status_code == 302 and response["Location"] == reverse("domains:list")
    user = User.objects.get(username="nodira")
    assert user.email == "nodira@example.uz" and not user.is_staff
    assert client.get(reverse("jobs:list")).status_code == 200


def test_duplicate_email_and_weak_password(user: User) -> None:
    response = Client().post(
        reverse("register"),
        {"username": "x", "email": "ALI@example.uz", "password1": "123", "password2": "123"},
    )
    page = response.content.decode()
    assert response.status_code == 200 and "allaqachon bor" in page
    assert not User.objects.filter(username="x").exists()


def test_login_and_lockout_after_failures(user: User) -> None:
    client = Client()
    ok = client.post(reverse("login"), {"username": "ali", "password": "Parol-12345!"})
    assert ok.status_code == 302
    attacker = Client()
    for _ in range(5):
        attacker.post(reverse("login"), {"username": "ali", "password": "notogri"})
    locked = attacker.post(reverse("login"), {"username": "ali", "password": "Parol-12345!"})
    assert locked.status_code in {403, 429}
    assert "vaqtincha yopildi" in locked.content.decode()


def test_ops_admin_is_for_staff_only(user: User) -> None:
    client = Client()
    client.force_login(user)
    assert client.get("/ops/").status_code == 302  # to the staff login
    assert client.get("/admin/").status_code == 404
