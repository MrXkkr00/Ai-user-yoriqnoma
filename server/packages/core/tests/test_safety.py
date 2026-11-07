from __future__ import annotations

import pytest

from yoriqnoma_core.safety.pii import (
    find_pii,
    is_name_header,
    is_pii_field,
    is_site_email,
    luhn_ok,
    mask_text,
)
from yoriqnoma_core.safety.policy_engine import ClickContext, PolicyEngine, RequestContext
from yoriqnoma_core.safety.url_guard import UrlBlocked, check_url
from yoriqnoma_core.text_uz import contains_word, normalize_uz
from yoriqnoma_schemas import Policy


def public_dns(host: str) -> list[str]:
    return {
        "example.com": ["93.184.216.34"],
        "rebind.test": ["93.184.216.34", "10.0.0.5"],
        "v6.test": ["2606:4700::1111"],
        "inner.test": ["192.168.1.10"],
    }.get(host, [])


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://127.1/",
        "http://localhost:8000/",
        "http://app.localhost/",
        "http://[::1]/",
        "http://[::ffff:127.0.0.1]/",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.1.2.3/",
        "http://172.16.0.1/",
        "http://192.168.0.1/",
        "http://100.64.0.1/",
        "http://0.0.0.0/",
        "http://2130706433/",
        "http://0x7f000001/",
        "http://0177.0.0.1/",
        "http://[fd00::1]/",
        "http://[fe80::1]/",
        "http://224.0.0.1/",
        "ftp://example.com/",
        "file:///etc/passwd",
        "http://user:pass@example.com/",
        "http://rebind.test/",
        "http://inner.test/",
        "http:///nohost",
    ],
)
def test_url_guard_blocks(url: str) -> None:
    with pytest.raises(UrlBlocked):
        check_url(url, allow_private=False, resolver=public_dns)


@pytest.mark.parametrize("url", ["https://example.com/a?b=1", "http://v6.test/"])
def test_url_guard_allows_public(url: str) -> None:
    assert check_url(url, allow_private=False, resolver=public_dns) == url


def test_allow_private_is_for_the_local_app_only() -> None:
    assert check_url("http://127.0.0.1:8800/", allow_private=True)
    with pytest.raises(UrlBlocked):  # cloud metadata stays blocked even locally
        check_url("http://169.254.169.254/", allow_private=True)


@pytest.mark.parametrize(
    "text", ["o'chirish", "oʻchirish", "O‘CHIRISH", "Öçiriş", "o`chirish", "  O’chirish "]
)
def test_normalize_uz_both_alphabets(text: str) -> None:
    assert normalize_uz(text) == "o'chirish"


def test_contains_word() -> None:
    assert contains_word("Hisobni Öçiriş", "o'chirish")
    assert contains_word("Tölaş", "to'lash")
    assert not contains_word("To'lovlar tarixi", "to'lash")


def test_find_pii_kinds() -> None:
    text = (
        "Email: ali.valiyev@mail.uz, tel +998 90 123-45-67, karta 4111 1111 1111 1111, "
        "pasport AB1234567, JSHSHIR 31234567890123. Ism: Ali Valiyev. Manzil: Toshkent, Chilonzor"
    )
    kinds = {m.kind for m in find_pii(text)}

    assert kinds == {"email", "phone", "card", "passport", "pinfl", "name", "address"}


def test_find_pii_ignores_generated_and_public_values() -> None:
    text = "info@demo-shop.uz +998 71 200-00-00 test.a@yoriqnoma.test"
    ignore = ["info@demo-shop.uz", "+998712000000", "test.a@yoriqnoma.test"]

    assert find_pii(text, ignore) == []


def test_find_pii_no_false_phones_in_prices() -> None:
    assert find_pii("Narxi: 1 250 000 so'm, 289 000 so'm, 2026-11-08") == []


def test_card_needs_luhn() -> None:
    assert luhn_ok("4111111111111111")
    assert find_pii("1234 5678 9012 3456") == []


def test_mask_text() -> None:
    assert mask_text("Tel: +998901234567") == "Tel: •••"


def test_field_and_header_helpers() -> None:
    assert is_pii_field("customer_name") and is_pii_field("phone") and is_pii_field("avatar_url")
    assert not is_pii_field("notify_email") and not is_pii_field("status")
    assert is_name_header("F.I.Sh") and is_name_header(" Mijoz ") and is_name_header("ФИО")
    assert not is_name_header("Status")
    assert is_site_email("info@kun.uz", "https://kun.uz/news")
    assert is_site_email("press@mail.kun.uz", "https://www.kun.uz/")
    assert not is_site_email("someone@gmail.com", "https://kun.uz/")


@pytest.fixture
def engine() -> PolicyEngine:
    return PolicyEngine(Policy(target_role="customer"), "http://127.0.0.1:8800/")


@pytest.mark.parametrize(
    ("method", "url", "rtype", "allowed"),
    [
        ("GET", "http://127.0.0.1:8800/api/orders", "fetch", True),
        ("GET", "http://127.0.0.1:8800/api/admin/users", "fetch", False),
        ("GET", "http://127.0.0.1:8800/admin", "document", False),
        ("GET", "https://cdn.example.com/x.css", "stylesheet", True),
        ("GET", "https://evil.example.com/collect", "fetch", False),
        ("POST", "https://evil.example.com/collect", "fetch", False),
        ("GET", "https://evil.example.com/", "document", False),
        ("POST", "http://127.0.0.1:8800/api/orders", "fetch", True),
        ("POST", "http://127.0.0.1:8800/api/orders/7/cancel", "fetch", True),
        ("POST", "http://127.0.0.1:8800/api/orders/1/cancel", "fetch", False),
        ("DELETE", "http://127.0.0.1:8800/api/orders/1", "fetch", False),
        ("PUT", "http://127.0.0.1:8800/api/profile", "fetch", True),
        ("POST", "http://127.0.0.1:8800/api/products/1/reviews", "fetch", True),
    ],
)
def test_policy_requests(
    engine: PolicyEngine, method: str, url: str, rtype: str, allowed: bool
) -> None:
    ctx = RequestContext(own_ids={"7"}, collections={"reviews", "orders"})

    assert engine.allows_request(method, url, rtype, ctx)[0] is allowed


def test_probe_mode_allows_only_get_to_denied_paths(engine: PolicyEngine) -> None:
    ctx = RequestContext(probe=True)
    url = "http://127.0.0.1:8800/api/admin/users"

    assert engine.allows_request("GET", url, "fetch", ctx)[0]
    assert not engine.allows_request("POST", url, "fetch", ctx)[0]


@pytest.mark.parametrize(
    "name", ["O'chirish", "Öçiriş", "Tölaş", "Bekor qilish", "Chiqish", "Удалить"]
)
def test_policy_click_denies_dangerous_words(engine: PolicyEngine, name: str) -> None:
    assert not engine.allows_click(name, ClickContext())[0]


def test_policy_click_own_object_on_staging(engine: PolicyEngine) -> None:
    assert engine.allows_click("Bekor qilish", ClickContext(own_object=True, flow_step=True))[0]
    assert engine.allows_click("Tarix", ClickContext())[0]
    prod = PolicyEngine(Policy(target_role="customer", environment="production"), "http://x/")
    assert not prod.allows_click("Bekor qilish", ClickContext(own_object=True, flow_step=True))[0]
