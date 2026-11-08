"""Fernet encryption of test-account passwords and human input (TZ SEC-12).

The key is ``YORIQNOMA_FERNET_KEY`` (env on the server, a git-ignored file in dev).
Encrypted values are removed when the job finishes (jobs.pipeline).
"""

from __future__ import annotations

import json
from functools import cache
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


@cache
def _fernet(key: str) -> Fernet:
    return Fernet(key.encode("ascii"))


def fernet() -> Fernet:
    return _fernet(str(settings.YORIQNOMA_FERNET_KEY))


def encrypt_text(value: str) -> bytes:
    return fernet().encrypt(value.encode("utf-8"))


def decrypt_text(token: bytes | memoryview | None) -> str:
    if not token:
        return ""
    try:
        return fernet().decrypt(bytes(token)).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("shifrlangan qiymatni ochib bo'lmadi (kalit almashganmi?)") from exc


def encrypt_json(value: Any) -> bytes:
    return encrypt_text(json.dumps(value, ensure_ascii=False))


def decrypt_json(token: bytes | memoryview | None) -> Any:
    text = decrypt_text(token)
    return json.loads(text) if text else None
