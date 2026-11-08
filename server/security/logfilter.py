"""Log filter that masks secrets in every log line (TZ SEC-12, NFR-6).

Masked: the Claude key (``sk-ant-...``) and the ``x-api-key`` header, ``Authorization``,
``Cookie``/``Set-Cookie`` values, passwords, tokens, secrets, session and CSRF cookies.
The filter rewrites the formatted message, so values hidden in ``%s`` arguments are
masked too. It is attached to the console handler (settings.LOGGING), which Django,
Celery (root logger not hijacked), anthropic and httpx all write to.
"""

from __future__ import annotations

import logging
import re

MASK = "***"

_PATTERNS = [
    re.compile(r"sk-ant-[A-Za-z0-9_\-]+"),
    re.compile(
        r"(?i)(?P<k>\b(?:x-api-key|authorization|proxy-authorization|cookie|set-cookie)"
        r"[\"']?\s*[:=]\s*)(?P<v>\"[^\"]*\"|'[^']*'|[^\r\n,}]+)"
    ),
    re.compile(
        r"(?i)(?P<k>\b(?:password|passwd|parol|pwd|token|secret|api[_-]?key|sessionid|"
        r"csrftoken|csrfmiddlewaretoken|fernet[_-]?key|pseudonym[_-]?key)"
        r"[\"']?\s*[:=]\s*)(?P<v>\"[^\"]*\"|'[^']*'|[^\s,&;}\]]+)"
    ),
]


def mask_secrets(text: str) -> str:
    out = _PATTERNS[0].sub("sk-ant-" + MASK, text)
    for pattern in _PATTERNS[1:]:
        out = pattern.sub(lambda m: m.group("k") + MASK, out)
    return out


class SecretsFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except (TypeError, ValueError):
            message = str(record.msg)
        masked = mask_secrets(message)
        if record.exc_info and record.exc_info[1] is not None:
            # the traceback is formatted later: keep only a masked one-line reason
            exc = record.exc_info[1]
            masked += f" | {type(exc).__name__}: {mask_secrets(str(exc))}"
            record.exc_info = None
            record.exc_text = None
        record.msg = masked
        record.args = None
        return True
