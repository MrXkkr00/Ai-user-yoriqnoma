"""System checks of the server's security settings (TZ SEC-12, SEC-17)."""

from __future__ import annotations

import os
from typing import Any

from django.conf import settings
from django.core.checks import CheckMessage, Error, Tags, Warning, register


@register(Tags.security)
def claude_key_only_in_worker(app_configs: Any = None, **kwargs: Any) -> list[CheckMessage]:
    """The Claude key is given to the Celery worker only, never to web or beat."""
    if os.environ.get("ANTHROPIC_API_KEY") and os.environ.get("YORIQNOMA_ROLE") != "worker":
        return [
            Warning(
                "ANTHROPIC_API_KEY bu jarayonda bor. Kalit faqat worker servisiga beriladi "
                "(docker/worker.env), web va beat'ga emas.",
                id="security.W001",
            )
        ]
    return []


@register(Tags.security, deploy=True)
def keys_present(app_configs: Any = None, **kwargs: Any) -> list[CheckMessage]:
    problems: list[CheckMessage] = []
    if not getattr(settings, "YORIQNOMA_FERNET_KEY", ""):
        problems.append(Error("YORIQNOMA_FERNET_KEY berilmagan", id="security.E001"))
    if len(str(getattr(settings, "YORIQNOMA_PSEUDONYM_KEY", ""))) < 16:
        problems.append(
            Error("YORIQNOMA_PSEUDONYM_KEY berilmagan yoki juda qisqa", id="security.E002")
        )
    return problems
