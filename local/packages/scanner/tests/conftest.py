from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from yoriqnoma_scanner.api import ScanResult, scan

DEMO_SHOP = Path(__file__).resolve().parents[3] / "fixtures" / "demo_shop"
DEMO_DJANGO = Path(__file__).resolve().parents[3] / "fixtures" / "demo_django"
BASE_URL = "http://127.0.0.1:8800"


@pytest.fixture(scope="session")
def demo_scan() -> ScanResult:
    if not DEMO_SHOP.is_dir():
        pytest.skip("fixtures/demo_shop is not in this checkout")
    return scan(DEMO_SHOP, BASE_URL, project="demo_shop")


@pytest.fixture(scope="session")
def django_scan() -> ScanResult:
    if not DEMO_DJANGO.is_dir():
        pytest.skip("fixtures/demo_django is not in this checkout")
    return scan(DEMO_DJANGO, "http://127.0.0.1:8810", project="demo_django")


@pytest.fixture
def demo_django_dir() -> Path:
    if not DEMO_DJANGO.is_dir():
        pytest.skip("fixtures/demo_django is not in this checkout")
    return DEMO_DJANGO


def write(root: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


Writer = Callable[[Path, dict[str, str]], Path]


@pytest.fixture
def write_files() -> Writer:
    return write


@pytest.fixture
def demo_shop_dir() -> Path:
    if not DEMO_SHOP.is_dir():
        pytest.skip("fixtures/demo_shop is not in this checkout")
    return DEMO_SHOP
