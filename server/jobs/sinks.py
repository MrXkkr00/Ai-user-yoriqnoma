"""Bridges between the core pipeline and the job's database rows (ARCHITECTURE §7.3).

The pipeline runs in an asyncio loop inside a Celery worker; Django forbids synchronous
ORM calls from an async context, so every ORM call goes through ``DbThread`` (one
dedicated thread). Log lines pass the secrets filter before they are stored.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import time
from collections.abc import Callable
from decimal import Decimal
from typing import Any, Literal, TypeVar

from django.db import close_old_connections
from django.db.models import F

from jobs.models import InputRequest, Job, JobEvent
from security.logfilter import mask_secrets
from security.secrets import decrypt_text
from yoriqnoma_core.pipeline import RunAborted

T = TypeVar("T")
STAGE_STATUS = {
    "preflight": "preflight",
    "scout": "scouting",
    "explore": "exploring",
    "write": "writing",
    "render": "rendering",
}


class DbThread:
    """Runs ORM calls on one worker thread (allowed), not on the event loop thread."""

    def __init__(self) -> None:
        self.pool = concurrent.futures.ThreadPoolExecutor(1, thread_name_prefix="job-db")

    def __call__(self, fn: Callable[[], T]) -> T:
        def wrapped() -> T:
            close_old_connections()
            return fn()

        return self.pool.submit(wrapped).result()

    def close(self) -> None:
        def close_here() -> None:
            from django.db import connection

            connection.close()

        self.pool.submit(close_here).result()
        self.pool.shutdown()


def add_event(job_id: int, kind: str, payload: dict[str, Any]) -> None:
    JobEvent.objects.create(job_id=job_id, kind=kind, payload=payload)


def set_status(job_id: int, status: str) -> None:
    Job.objects.filter(pk=job_id).update(status=status)
    add_event(job_id, "status", {"status": status})


class JobProgressSink:
    def __init__(self, job_id: int, db: DbThread) -> None:
        self.job_id = job_id
        self.db = db
        self._pending = 0
        self._last = 0.0

    def stage(self, name: str, total: int) -> None:
        status = STAGE_STATUS.get(name)

        def go() -> None:
            Job.objects.filter(pk=self.job_id).update(progress_done=0, progress_total=total)
            if status:
                set_status(self.job_id, status)

        self.db(go)

    def advance(self, n: int = 1) -> None:
        self._pending += n
        if time.monotonic() - self._last >= 1.0:
            self.flush()

    def flush(self) -> None:
        pending, self._pending = self._pending, 0
        self._last = time.monotonic()
        if pending:
            self.db(
                lambda: Job.objects.filter(pk=self.job_id).update(
                    progress_done=F("progress_done") + pending
                )
            )

    def log(self, level: str, message: str) -> None:
        self.flush()
        text = mask_secrets(message)[:2000]
        self.db(lambda: add_event(self.job_id, "log", {"level": level, "message": text}))

    def event(self, kind: str, payload: dict[str, object]) -> None:
        if kind == "cost":
            self.cost(dict(payload))
        elif kind == "pii_masked":
            self.log(
                "warning",
                f"{payload.get('task')}: Claude'ga yuborishdan oldin "
                f"{payload.get('count')} ta shaxsiy qiymat yashirildi (SEC-7)",
            )
        else:
            self.db(lambda: add_event(self.job_id, "log", {"level": "info", "message": kind}))

    def cost(self, payload: dict[str, Any]) -> None:
        """A Claude call was paid for: add it to the job (TZ FR-SV6)."""
        cost = Decimal(str(payload.get("cost_usd", 0) or 0))
        tokens_in = int(payload.get("input_tokens", 0) or 0)
        tokens_out = int(payload.get("output_tokens", 0) or 0)

        def go() -> None:
            Job.objects.filter(pk=self.job_id).update(
                cost_usd=F("cost_usd") + cost,
                tokens_in=F("tokens_in") + tokens_in,
                tokens_out=F("tokens_out") + tokens_out,
            )
            add_event(
                self.job_id,
                "cost",
                {
                    "task": payload.get("task"),
                    "model": payload.get("model"),
                    "cost_usd": float(cost),
                    "spent_usd": payload.get("spent_usd"),
                },
            )

        self.db(go)


class JobCancelToken:
    def __init__(self, job_id: int, db: DbThread) -> None:
        self.job_id = job_id
        self.db = db
        self._checked = 0.0
        self._value = False

    def is_cancelled(self) -> bool:
        if self._value or time.monotonic() - self._checked < 1.0:
            return self._value
        self._checked = time.monotonic()
        self._value = self.db(
            lambda: Job.objects.filter(pk=self.job_id, cancel_requested=True).exists()
        )
        return self._value


class JobHumanInput:
    """Asks the person on the job page (SMS code, captcha); waits with a time limit."""

    def __init__(self, job_id: int, db: DbThread, timeout_s: int = 600) -> None:
        self.job_id = job_id
        self.db = db
        self.timeout_s = timeout_s

    async def ask(self, kind: Literal["sms_code", "captcha", "confirm"], message: str) -> str:
        def create() -> tuple[int, str]:
            previous = Job.objects.get(pk=self.job_id).status
            request = InputRequest.objects.create(job_id=self.job_id, kind=kind, message=message)
            set_status(self.job_id, "waiting_input")
            add_event(
                self.job_id,
                "need_input",
                {"request_id": request.pk, "kind": kind, "message": message},
            )
            return request.pk, previous

        request_id, previous = self.db(create)
        deadline = time.monotonic() + self.timeout_s
        while time.monotonic() < deadline:
            await asyncio.sleep(2)

            def check() -> str | None:
                request = InputRequest.objects.get(pk=request_id)
                if request.answered_at is None:
                    return None
                value = decrypt_text(request.value_enc)
                InputRequest.objects.filter(pk=request_id).update(value_enc=None)
                set_status(self.job_id, previous)
                return value

            answer = self.db(check)
            if answer is not None:
                return answer
        raise RunAborted(f"javob kutish vaqti tugadi ({self.timeout_s // 60} daqiqa)")
