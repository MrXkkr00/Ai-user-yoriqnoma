"""Local secrets in var/ (never in git, capture, bundle or logs).

* ``secret.key`` — Fernet key for test account passwords and input answers (FR-L2);
* ``pseudonym.key`` — HMAC key for stable fakes of other people's data (FR-E10).

Both are created on first use with owner-only permissions where the OS supports it.
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path

from cryptography.fernet import Fernet
from django.conf import settings


def _key_file(name: str, make: bytes) -> bytes:
    path = Path(settings.VAR_DIR) / name
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return path.read_bytes().strip()
    with os.fdopen(fd, "wb") as fh:
        fh.write(make)
    return make


def fernet() -> Fernet:
    return Fernet(_key_file("secret.key", Fernet.generate_key()))


def pseudonym_key() -> bytes:
    return _key_file("pseudonym.key", secrets.token_hex(32).encode())


def encrypt(text: str) -> bytes:
    return fernet().encrypt(text.encode("utf-8"))


def decrypt(token: bytes | memoryview | None) -> str:
    if token is None:
        return ""
    return fernet().decrypt(bytes(token)).decode("utf-8")
