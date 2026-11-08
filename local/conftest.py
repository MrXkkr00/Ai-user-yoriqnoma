"""Shared fixtures: an isolated var/ folder per test and a running demo_shop."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture(autouse=True)
def _isolated_var(request: pytest.FixtureRequest, tmp_path: Path) -> None:
    if "settings" not in request.fixturenames and not request.node.get_closest_marker("django_db"):
        return
    settings: Any = request.getfixturevalue("settings")
    var = tmp_path / "var"
    (var / "runs").mkdir(parents=True)
    settings.VAR_DIR = var
    settings.MEDIA_ROOT = var / "runs"


DEMO_SHOP_DIR = Path(__file__).resolve().parent / "fixtures" / "demo_shop"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_until_ready(url: str, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url + "api/health", timeout=2) as resp:
                if resp.status == 200:
                    return
        except OSError:
            time.sleep(0.2)
    raise RuntimeError(f"demo_shop did not start at {url}")


@contextmanager
def running_demo_shop(var: Path) -> Iterator[str]:
    """demo_shop with a fresh database in ``var``; stopped when the block ends."""
    port = _free_port()
    env = {**os.environ, "DEMO_SHOP_VAR": str(var)}
    env.pop("MAILPIT_SMTP", None)  # mail goes to <var>/mail/*.eml (DirMailbox)
    proc = subprocess.Popen(
        [sys.executable, "-m", "demo_shop", "--port", str(port), "--reset"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    url = f"http://127.0.0.1:{port}/"
    try:
        wait_until_ready(url)
        yield url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


@pytest.fixture(scope="session")
def demo_shop_var(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("demo_shop_var")


@pytest.fixture(scope="session")
def demo_shop_url(demo_shop_var: Path) -> Iterator[str]:
    """One demo_shop for the session (tests that only add their own data)."""
    with running_demo_shop(demo_shop_var) as url:
        yield url


@pytest.fixture(scope="module")
def fresh_demo_shop(tmp_path_factory: pytest.TempPathFactory) -> Iterator[tuple[str, Path]]:
    """A demo_shop of its own for one test module: only the seed data, nothing from
    other tests (the explorer tests count what the seed holds)."""
    var = tmp_path_factory.mktemp("demo_shop_fresh")
    with running_demo_shop(var) as url:
        yield url, var
