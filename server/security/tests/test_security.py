"""Server security (T23, QM-5): SSRF, secrets, log masking, robots, rate limit, checks."""

from __future__ import annotations

import logging
from typing import Any

import httpx
import pytest
from django.core.checks import run_checks
from django.test import override_settings

import security.ssrf
from security.logfilter import SecretsFilter, mask_secrets
from security.ratelimit import MemoryRateLimiter
from security.robots import deny_globs, parse_robots
from security.secrets import decrypt_json, decrypt_text, encrypt_json, encrypt_text
from security.ssrf import check_public_url, safe_get
from yoriqnoma_core.safety.url_guard import UrlBlocked
from yoriqnoma_server.worker_env import worker_env_problems

FAKE_KEY = "sk-ant-test-0123456789abcdefXYZ"


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://localhost:8000/",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/",
        "http://0x7f000001/",
        "http://2130706433/",
        "http://017700000001/",
        "http://10.1.2.3/",
        "http://192.168.0.10/",
        "https://internal.example.uz/",
        "https://mixed.example.uz/",  # one public and one private answer
        "https://metadata.example.uz/",
        "ftp://shop.example.uz/",
        "file:///etc/passwd",
        "https://user:pass@shop.example.uz/",
        "https://no-such-host.example.uz/",
    ],
)
def test_server_blocks_private_and_odd_urls(url: str) -> None:
    with pytest.raises(UrlBlocked):
        check_public_url(url)


def test_public_url_passes() -> None:
    assert check_public_url("https://shop.example.uz/app") == "https://shop.example.uz/app"


def test_private_allowlist_only_by_setting() -> None:
    with pytest.raises(UrlBlocked):
        check_public_url("http://127.0.0.1:8800/")
    with override_settings(YORIQNOMA_PRIVATE_ALLOWLIST=["127.0.0.1"]):
        assert check_public_url("http://127.0.0.1:8800/")
        with pytest.raises(UrlBlocked):  # metadata stays blocked even then
            check_public_url("http://169.254.169.254/")


def _transport(handler: Any) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


def test_safe_get_pins_the_checked_address_and_sends_host() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, text="ok token")

    answer = safe_get("https://shop.example.uz/.well-known/x.txt", transport=_transport(handler))

    assert answer.status == 200 and answer.text == "ok token"
    assert seen[0].url.host == "93.184.216.34"  # connected to the address that was checked
    assert seen[0].headers["host"] == "shop.example.uz"
    assert seen[0].extensions["sni_hostname"] == "shop.example.uz"
    assert "AI-user-yoriqnoma/" in seen[0].headers["user-agent"]


def test_safe_get_checks_every_redirect() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/"})

    with pytest.raises(UrlBlocked):
        safe_get("https://shop.example.uz/go", transport=_transport(handler))

    def to_internal(request: httpx.Request) -> httpx.Response:
        return httpx.Response(301, headers={"location": "https://internal.example.uz/"})

    with pytest.raises(UrlBlocked):
        safe_get("https://shop.example.uz/go", transport=_transport(to_internal))


def test_dns_rebinding_second_answer_is_never_used(monkeypatch: pytest.MonkeyPatch) -> None:
    answers = iter([["93.184.216.34"], ["127.0.0.1"], ["127.0.0.1"]])
    monkeypatch.setattr(security.ssrf, "resolver", lambda host: next(answers))
    hosts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        hosts.append(request.url.host)
        return httpx.Response(200, text="x")

    safe_get("https://rebind.example.uz/", transport=_transport(handler))

    assert hosts == ["93.184.216.34"]  # one resolution, pinned; the private answer unused


def test_safe_get_size_limit() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * 5000)

    with pytest.raises(UrlBlocked, match="katta"):
        safe_get("https://shop.example.uz/big", max_bytes=1000, transport=_transport(handler))


def test_log_filter_masks_key_header_password_cookie() -> None:
    record = logging.LogRecord(
        "anthropic",
        logging.ERROR,
        __file__,
        1,
        "request failed: x-api-key: %s password=%s Cookie: sessionid=abc; csrftoken=def",
        (FAKE_KEY, "Sir-123"),
        None,
    )
    SecretsFilter().filter(record)
    text = record.getMessage()

    assert FAKE_KEY not in text and "x-api-key: ***" in text
    assert "Sir-123" not in text and "abc" not in text
    assert "Authorization: ***" in mask_secrets("Authorization: Bearer abc.def")
    assert FAKE_KEY not in mask_secrets(f"error {FAKE_KEY} at 401")


def test_log_filter_on_exceptions() -> None:
    try:
        raise RuntimeError(f"401 key {FAKE_KEY}")
    except RuntimeError:
        import sys

        record = logging.LogRecord("x", logging.ERROR, __file__, 1, "boom", None, sys.exc_info())
    SecretsFilter().filter(record)
    assert FAKE_KEY not in record.getMessage() and record.exc_info is None


def test_fernet_round_trip() -> None:
    token = encrypt_text("Parol-1")
    assert b"Parol-1" not in token and decrypt_text(token) == "Parol-1"
    data = {"customer": {"A": {"login": "a@x.uz", "password": "p"}}}
    assert decrypt_json(encrypt_json(data)) == data
    assert decrypt_text(None) == ""


def test_robots_rules() -> None:
    robots = parse_robots(
        "User-agent: *\nDisallow: /private\nDisallow: /tmp/\nSitemap: https://s.uz/sitemap.xml\n"
    )
    assert not robots.allowed("https://s.uz/private/a")
    assert robots.allowed("https://s.uz/catalog")
    assert robots.sitemaps == ["https://s.uz/sitemap.xml"]
    assert deny_globs(robots) == ["/private*", "/tmp/*"]
    assert parse_robots("", 403).disallow_all
    assert parse_robots("", 404).allowed("https://s.uz/x")


def test_memory_rate_limiter() -> None:
    limiter = MemoryRateLimiter(rate_per_s=2.0, burst=1)
    assert limiter.try_acquire("s.uz", now=0.0) == 0.0
    wait = limiter.try_acquire("s.uz", now=0.1)
    assert wait == pytest.approx(0.4)
    assert limiter.try_acquire("other.uz", now=0.1) == 0.0
    assert limiter.try_acquire("s.uz", now=0.6) == 0.0


def test_worker_refuses_to_start_without_keys() -> None:
    problems = worker_env_problems({})
    assert len(problems) == 3 and "ANTHROPIC_API_KEY" in problems[0]
    ok = {
        "ANTHROPIC_API_KEY": FAKE_KEY,
        "YORIQNOMA_PSEUDONYM_KEY": "x" * 32,
        "YORIQNOMA_FERNET_KEY": "k",
    }
    assert worker_env_problems(ok) == []
    assert FAKE_KEY not in " ".join(worker_env_problems({"ANTHROPIC_API_KEY": FAKE_KEY}))


def test_worker_init_signal_stops_the_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    from yoriqnoma_server.celery import check_worker_env

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(SystemExit, match="ANTHROPIC_API_KEY"):
        check_worker_env()


def test_claude_key_in_web_process_is_flagged(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
    monkeypatch.delenv("YORIQNOMA_ROLE", raising=False)
    ids = [m.id for m in run_checks()]
    assert "security.W001" in ids
    monkeypatch.setenv("YORIQNOMA_ROLE", "worker")
    assert "security.W001" not in [m.id for m in run_checks()]
