"""Shared fixtures: a running demo_shop (subprocess, port 8800 by default)."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest

DEMO_SHOP_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "demo_shop"


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


@pytest.fixture(scope="session")
def demo_shop_var(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("demo_shop_var")


@pytest.fixture(scope="session")
def demo_shop_url(demo_shop_var: Path) -> Iterator[str]:
    """Start demo_shop with a fresh database in a temp folder; stop it at the end."""
    port = _free_port()
    env = {**os.environ, "DEMO_SHOP_VAR": str(demo_shop_var)}
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
