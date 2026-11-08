"""Domains (T23, TZ SEC-9): normalizing, three ways to verify, matching job URLs, pages."""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from domains import services
from domains.models import Domain
from domains.services import DomainError, add_domain, check_methods, domain_for, normalize_host


@pytest.mark.parametrize(
    ("raw", "host"),
    [
        ("Shop.Example.uz", "shop.example.uz"),
        ("https://shop.example.uz/app/x?y=1", "shop.example.uz"),
        ("shop.example.uz.", "shop.example.uz"),
        ("bozor.o'zbek.uz".replace("'", ""), "bozor.xn--ozbek-uta.uz"),
    ],
)
def test_normalize_host(raw: str, host: str) -> None:
    if "xn--" in host:
        assert normalize_host(raw).startswith("bozor.")
    else:
        assert normalize_host(raw) == host


@pytest.mark.parametrize("raw", ["", "127.0.0.1", "localhost", "a.local", "no_dots", "x..uz"])
def test_normalize_host_refuses(raw: str) -> None:
    with pytest.raises(DomainError):
        normalize_host(raw)


def test_verification_methods(user: User) -> None:
    domain = add_domain(user, "shop.example.uz")
    token = domain.token

    def wellknown(url: str) -> str | None:
        return f"{token}\n" if url.endswith("yoriqnoma-verify.txt") else None

    def meta(url: str) -> str | None:
        if url.endswith("/"):
            return f'<html><head><meta name="yoriqnoma-verify" content="{token}"></head></html>'
        return None

    assert check_methods(domain, wellknown, lambda h: []) == "wellknown"
    assert check_methods(domain, meta, lambda h: []) == "meta"
    assert check_methods(domain, lambda u: None, lambda h: [f"yoriqnoma-verify={token}"]) == "dns"
    assert check_methods(domain, lambda u: "wrong", lambda h: ["other"]) is None


def test_verify_saves_method(user: User, monkeypatch: pytest.MonkeyPatch) -> None:
    domain = add_domain(user, "shop.example.uz")
    with pytest.raises(DomainError):
        services.verify(domain, lambda u: None, lambda h: [])
    services.verify(domain, lambda u: None, lambda h: [f"yoriqnoma-verify={domain.token}"])
    domain.refresh_from_db()
    assert domain.verified and domain.method == "dns"


def test_domain_for_matches_host_www_and_dns_subdomains(user: User, other_user: User) -> None:
    file_verified = Domain.objects.create(
        owner=user, host="shop.example.uz", verified_at=timezone.now(), method="wellknown"
    )
    dns_verified = Domain.objects.create(
        owner=user, host="example.org", verified_at=timezone.now(), method="dns"
    )
    assert domain_for(user, "https://shop.example.uz/app") == file_verified
    assert domain_for(user, "https://www.shop.example.uz/") == file_verified
    assert domain_for(user, "https://staging.shop.example.uz/") is None  # file: no subdomains
    assert domain_for(user, "https://staging.example.org/") == dns_verified
    assert domain_for(other_user, "https://shop.example.uz/") is None


def test_domain_pages(user: User, monkeypatch: pytest.MonkeyPatch) -> None:
    client = Client()
    assert client.get(reverse("domains:list")).status_code == 302  # login needed
    client.force_login(user)
    client.post(reverse("domains:list"), {"host": "https://shop.example.uz/"})
    domain = Domain.objects.get(owner=user)
    page = client.get(reverse("domains:list")).content.decode()
    assert domain.token in page and "yoriqnoma-verify" in page

    monkeypatch.setattr(services, "check_methods", lambda d, *a, **k: "meta")
    client.post(reverse("domains:verify", args=[domain.pk]))
    domain.refresh_from_db()
    assert domain.method == "meta"


def test_other_users_domain_is_hidden(user: User, other_user: User) -> None:
    domain = Domain.objects.create(owner=other_user, host="other.example.uz")
    client = Client()
    client.force_login(user)
    assert client.post(reverse("domains:verify", args=[domain.pk])).status_code == 404
    assert client.post(reverse("domains:delete", args=[domain.pk])).status_code == 404
