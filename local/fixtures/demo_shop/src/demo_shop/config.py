"""Paths and settings of demo_shop. Values come from the environment, never from .env."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # fixtures/demo_shop
WEB_DIST = ROOT / "web" / "dist"


def var_dir() -> Path:
    path = Path(os.environ.get("DEMO_SHOP_VAR") or ROOT / "var")
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path() -> Path:
    return var_dir() / "demo.db"


def mail_dir() -> Path:
    path = var_dir() / "mail"
    path.mkdir(parents=True, exist_ok=True)
    return path


def uploads_dir() -> Path:
    path = var_dir() / "uploads"
    path.mkdir(parents=True, exist_ok=True)
    return path


def smtp_target() -> tuple[str, int] | None:
    raw = os.environ.get("MAILPIT_SMTP", "")
    if not raw:
        return None
    host, _, port = raw.partition(":")
    return host, int(port or "1025")
