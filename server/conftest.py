"""Shared test fixtures of the server app.

No real DNS, no Claude and no browser in unit tests: the SSRF resolver is replaced by a
small table, the writer uses ``FakeProvider``. Samples of the local app's output (the
blueprint and bundle formats) are built from docs/schemas/examples — exactly what a
person would upload (TZ FR-SV9).
"""

from __future__ import annotations

import os
import socket
import subprocess
import time
import urllib.request
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from django.contrib.auth.models import User
from django.utils import timezone

import security.ssrf
from domains.models import Domain
from jobs.tests.samples import EXAMPLES, build_bundle

SERVER = Path(__file__).resolve().parent
PUBLIC_IP = "93.184.216.34"
DNS = {
    "shop.example.uz": [PUBLIC_IP],
    "www.shop.example.uz": [PUBLIC_IP],
    "unverified.example.uz": [PUBLIC_IP],
    "other.example.uz": [PUBLIC_IP],
    "internal.example.uz": ["10.0.0.5"],
    "mixed.example.uz": [PUBLIC_IP, "127.0.0.1"],
    "metadata.example.uz": ["169.254.169.254"],
}


def fake_resolver(host: str) -> list[str]:
    if host not in DNS:
        raise OSError(f"no such host in tests: {host}")
    return list(DNS[host])


@pytest.fixture(autouse=True)
def _no_real_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(security.ssrf, "resolver", fake_resolver)


@pytest.fixture
def user(db: Any) -> User:
    return User.objects.create_user("ali", "ali@example.uz", "Parol-12345!")


@pytest.fixture
def other_user(db: Any) -> User:
    return User.objects.create_user("vali", "vali@example.uz", "Parol-12345!")


@pytest.fixture
def domain(user: User) -> Domain:
    return Domain.objects.create(
        owner=user, host="shop.example.uz", verified_at=timezone.now(), method="dns"
    )


@pytest.fixture
def unverified(user: User) -> Domain:
    return Domain.objects.create(owner=user, host="unverified.example.uz")


@pytest.fixture
def blueprint_bytes() -> bytes:
    return (EXAMPLES / "blueprint.example.json").read_bytes()


@pytest.fixture
def bundle_path(tmp_path: Path) -> Path:
    return build_bundle(tmp_path)


# --- demo_shop for slow tests: started from the local folder as a separate process --------


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _local_python() -> Path | None:
    local = SERVER.parent / "local" / ".venv"
    for candidate in (local / "Scripts" / "python.exe", local / "bin" / "python"):
        if candidate.exists():
            return candidate
    return None


@pytest.fixture(scope="module")
def demo_shop(tmp_path_factory: pytest.TempPathFactory) -> Iterator[tuple[str, Path]]:
    """The test site (local/fixtures/demo_shop) as its own process: nothing is imported."""
    python = _local_python()
    if python is None:
        pytest.skip("demo_shop needs the local app's environment (cd local && uv sync)")
    var = tmp_path_factory.mktemp("demo_shop")
    port = _free_port()
    env = {**os.environ, "DEMO_SHOP_VAR": str(var)}
    env.pop("MAILPIT_SMTP", None)
    proc = subprocess.Popen(
        [str(python), "-m", "demo_shop", "--port", str(port), "--reset"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}/"
    try:
        deadline = time.monotonic() + 40
        while True:
            try:
                urllib.request.urlopen(url, timeout=2)  # noqa: S310 - local test site
                break
            except OSError:
                if time.monotonic() > deadline or proc.poll() is not None:
                    pytest.skip("demo_shop did not start")
                time.sleep(0.3)
        yield url, var
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
