"""What the Celery worker needs before it takes the first job (TZ SEC-12).

Checked in the ``worker_init`` signal (yoriqnoma_server.celery): without the Claude key
or the pseudonym key the worker stops at once with a clear message instead of failing
on the first job. Pure Python, no Django: it runs before Django settings matter.
"""

from __future__ import annotations

from collections.abc import Mapping


def worker_env_problems(environ: Mapping[str, str]) -> list[str]:
    problems = []
    if not environ.get("ANTHROPIC_API_KEY", "").strip():
        problems.append(
            "ANTHROPIC_API_KEY berilmagan: kalitni docker/worker.env fayliga yozing "
            "(faqat worker servisi uchun) va worker'ni qayta ishga tushiring."
        )
    if len(environ.get("YORIQNOMA_PSEUDONYM_KEY", "").strip()) < 16:
        problems.append(
            "YORIQNOMA_PSEUDONYM_KEY berilmagan yoki juda qisqa: docker/.env ga uzun tasodifiy "
            "qiymat yozing (begona ma'lumotni almashtirish kaliti, TZ FR-E10)."
        )
    if not environ.get("YORIQNOMA_FERNET_KEY", "").strip():
        problems.append("YORIQNOMA_FERNET_KEY berilmagan: docker/.env ga Fernet kalitini yozing.")
    return problems
