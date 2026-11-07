"""Password hashing and session tokens."""

from __future__ import annotations

import hashlib
import hmac
import secrets


def hash_password(password: str) -> str:
    salt = secrets.token_hex(8)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 60_000).hex()
    return f"{salt}${digest}"


def check_password(password: str, stored: str) -> bool:
    salt, _, digest = stored.partition("$")
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 60_000).hex()
    return hmac.compare_digest(candidate, digest)


def new_token() -> str:
    return secrets.token_hex(24)


def new_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"
