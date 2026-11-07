"""Runs: start, execute (explore -> write -> render), cancel, human input (FR-L4, FR-L7).

The core pipeline runs in an asyncio loop inside a Huey worker thread (never in a view).
Django ORM calls from that loop go through ``_db``: a dedicated thread, because Django
forbids synchronous ORM calls from an async context.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import secrets
import shutil
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, TypeVar

from django.conf import settings
from django.db import close_old_connections
from django.utils import timezone
from pydantic import SecretBytes, SecretStr

from projects.models import BlueprintVersion, Project
from projects.services import accounts_for, effective_blueprint
from runs.models import InputRequest, Run, RunEvent
from settings_app.models import AppSettings
from yoriqnoma_core.pipeline import (
    AccountCredentials,
    Cancelled,
    ExploreOptions,
    RunAborted,
    make_bundle,
    run_explore,
    run_render,
    run_write,
)
from yoriqnoma_core.writer.providers import OllamaProvider
from yoriqnoma_core.writer.providers.base import ProviderError
from yoriqnoma_local.keys import decrypt, encrypt, pseudonym_key
from yoriqnoma_schemas import save_json

T = TypeVar("T")
FORMATS = ("html", "pdf", "docx")


class RunError(ValueError):
    pass


def new_run_id() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S-") + secrets.token_hex(3)


def start_run(
    project: Project,
    output: str,
    role: str = "",
    model: str = "",
    formats: list[str] | None = None,
    enqueue: bool = True,
) -> Run:
    """Create a run (one per role) and queue it. ``blueprint`` output finishes at once."""
    version = project.current_blueprint()
    if version is None:
        raise RunError("Avval loyihani skanerlang yoki blueprint yuklang")
    bp, _ = effective_blueprint(version)
    if output != "blueprint":
        info = bp.role(role)
        if info is None or info.kind != "role":
            raise RunError(f"«{role}» rolini tanlab bo'lmaydi")
    run_id = new_run_id()
    run_dir = Path(settings.MEDIA_ROOT) / project.slug / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    run = Run.objects.create(
        project=project,
        blueprint=version,
        role=role if output != "blueprint" else "",
        output=output,
        model=model or AppSettings.load().ollama_model,
        formats=[f for f in (formats or list(FORMATS)) if f in FORMATS] or ["html"],
        run_dir=str(run_dir),
    )
    if output == "blueprint":
        save_json(run_dir / "blueprint.json", bp)
        if version.report_path and Path(version.report_path).is_file():
            shutil.copy(version.report_path, run_dir / "scan_report.md")
        run.status = "done"
        run.started_at = run.finished_at = timezone.now()
        run.save()
        log(
            run,
            "info",
            "blueprint.json tayyor. Uni server sahifasidagi «Yangi ish» formasida yuklang.",
        )
        return run
    if enqueue:
        from runs.tasks import execute_run_task

        execute_run_task(run.pk)
    return run


def log(run: Run, level: str, message: str, stage: str = "") -> None:
    RunEvent.objects.create(run=run, level=level, stage=stage or run.stage, message=message[:2000])


def cancel_run(run: Run) -> None:
    if run.finished:
        return
    run.cancel_requested = True
    if run.status == "queued":
        run.status = "cancelled"
        run.finished_at = timezone.now()
    run.save(update_fields=["cancel_requested", "status", "finished_at"])


def answer_input(request: InputRequest, value: str) -> None:
    request.value_enc = encrypt(value)
    request.answered_at = timezone.now()
    request.save(update_fields=["value_enc", "answered_at"])


# --- bridges between the core pipeline and the database ---------------------------------


class _DbThread:
    """Runs ORM calls on one worker thread (allowed), not on the event loop thread."""

    def __init__(self) -> None:
        self.pool = concurrent.futures.ThreadPoolExecutor(1, thread_name_prefix="run-db")

    def __call__(self, fn: Callable[[], T]) -> T:
        def wrapped() -> T:
            close_old_connections()
            return fn()

        return self.pool.submit(wrapped).result()

    def close(self) -> None:
        def close_here() -> None:
            from django.db import connection  # this thread's own connection

            connection.close()

        self.pool.submit(close_here).result()
        self.pool.shutdown()


class DbProgressSink:
    def __init__(self, run_id: int, db: _DbThread) -> None:
        self.run_id = run_id
        self.db = db
        self._last_flush = 0.0
        self._pending = 0

    def stage(self, name: str, total: int) -> None:
        stage = name if name in dict(Run.STAGES) else ""

        def go() -> None:
            Run.objects.filter(pk=self.run_id).update(
                stage=stage, progress_done=0, progress_total=total
            )

        self.db(go)

    def advance(self, n: int = 1) -> None:
        self._pending += n
        if time.monotonic() - self._last_flush < 1.0:
            return
        self._flush()

    def _flush(self) -> None:
        pending, self._pending = self._pending, 0
        self._last_flush = time.monotonic()
        if pending:
            from django.db.models import F

            self.db(
                lambda: Run.objects.filter(pk=self.run_id).update(
                    progress_done=F("progress_done") + pending
                )
            )

    def log(self, level: str, message: str) -> None:
        self._flush()

        def go() -> None:
            run = Run.objects.get(pk=self.run_id)
            log(run, level, message)

        self.db(go)

    def event(self, kind: str, payload: dict[str, object]) -> None:
        return None


class DbCancelToken:
    def __init__(self, run_id: int, db: _DbThread) -> None:
        self.run_id = run_id
        self.db = db
        self._checked = 0.0
        self._value = False

    def is_cancelled(self) -> bool:
        if self._value or time.monotonic() - self._checked < 1.0:
            return self._value
        self._checked = time.monotonic()
        self._value = self.db(
            lambda: bool(Run.objects.filter(pk=self.run_id, cancel_requested=True).exists())
        )
        return self._value


class DbHumanInput:
    """Asks the person on the run page; waits up to 10 minutes (FR-E5)."""

    def __init__(self, run_id: int, db: _DbThread, timeout_s: int = 600) -> None:
        self.run_id = run_id
        self.db = db
        self.timeout_s = timeout_s

    async def ask(self, kind: Literal["sms_code", "captcha", "confirm"], message: str) -> str:
        def create() -> int:
            Run.objects.filter(pk=self.run_id).update(status="waiting_input")
            return InputRequest.objects.create(run_id=self.run_id, kind=kind, message=message).pk

        req_id = self.db(create)
        deadline = time.monotonic() + self.timeout_s
        while time.monotonic() < deadline:
            await asyncio.sleep(2)

            def check() -> str | None:
                req = InputRequest.objects.get(pk=req_id)
                if req.answered_at is None:
                    return None
                Run.objects.filter(pk=self.run_id).update(status="running")
                return decrypt(req.value_enc)

            answer = self.db(check)
            if answer is not None:
                return answer
        raise RunAborted("odam javobini kutish vaqti tugadi (10 daqiqa)")


# --- execution ------------------------------------------------------------------------


def explore_options(run: Run, mailbox_target: str | None = None) -> ExploreOptions:
    project = run.project
    accounts = {
        role: {
            alias: AccountCredentials(login=login, password=SecretStr(password))
            for alias, (login, password) in aliases.items()
        }
        for role, aliases in accounts_for(project).items()
    }
    return ExploreOptions(
        base_url=project.base_url,
        role=run.role,
        environment=project.environment,  # type: ignore[arg-type]
        accounts=accounts,
        mailbox_kind="mailpit" if project.mailbox_kind == "mailpit" else "dir",
        mailbox_target=mailbox_target or project.mailbox_target,
        allow_private=True,  # the local app may study a site on 127.0.0.1 (TZ SEC-10)
        headless=True,
        pseudonym_key=SecretBytes(pseudonym_key()),
        run_id=Path(run.run_dir).name,
    )


def provider_for(run: Run) -> OllamaProvider:
    cfg = AppSettings.load()
    return OllamaProvider(
        host=cfg.ollama_host, model=run.model or cfg.ollama_model, num_ctx=cfg.num_ctx
    )


def _finish(run: Run, status: str, error: str = "") -> None:
    run.status = status
    run.error = error[:4000]
    run.finished_at = timezone.now()
    run.save(update_fields=["status", "error", "finished_at"])


def execute_run(run_id: int) -> Run:
    """Explore, then (full) write with Ollama and render, or (bundle) package."""
    run = Run.objects.select_related("project", "blueprint").get(pk=run_id)
    if run.finished or run.cancel_requested:
        if not run.finished:
            _finish(run, "cancelled")
        return run
    run.status = "running"
    run.started_at = timezone.now()
    run.save(update_fields=["status", "started_at"])
    run_dir = Path(run.run_dir)
    db = _DbThread()
    progress = DbProgressSink(run.pk, db)
    cancel = DbCancelToken(run.pk, db)
    human = DbHumanInput(run.pk, db)
    try:
        bp, notes = effective_blueprint(run.blueprint)
        for note in notes:
            log(run, "info", note, "explore")
        provider = provider_for(run) if run.output == "full" else None
        if provider is not None:
            provider.check()  # fail early with a clear message (FR-L11)
        opts = explore_options(run)
        capture = asyncio.run(run_explore(bp, run_dir, opts, human, progress, cancel))
        verified = sum(1 for f in capture.flows if not f.helper and f.status == "verified")
        total = sum(1 for f in capture.flows if not f.helper)
        stats: dict[str, Any] = {
            "flows_verified": verified,
            "flows_total": total,
            "states": len(capture.states),
            "blocked_requests": len(capture.firewall_log),
        }
        if run.output == "bundle":
            Run.objects.filter(pk=run.pk).update(stage="package")
            make_bundle(run_dir)
        elif provider is not None:
            manual = asyncio.run(
                run_write(
                    run_dir,
                    provider,
                    progress,
                    cancel,
                    cache_dir=Path(settings.VAR_DIR) / "cache" / "llm",
                )
            )
            stats["coverage"] = manual.coverage.percent.get("total", 0)
            stats["needs_review"] = sum(a.needs_review for s in manual.sections for a in s.articles)
            Run.objects.filter(pk=run.pk).update(stage="render")
            run_render(run_dir, set(run.formats))
        run.refresh_from_db()
        run.stats = stats
        run.save(update_fields=["stats"])
        _finish(run, "done")
        log(run, "info", "Tayyor.")
    except Cancelled:
        run.refresh_from_db()
        _finish(run, "cancelled")
        log(run, "warning", "Ish bekor qilindi. Davom ettirish mumkin.")
    except (RunAborted, ProviderError) as exc:
        run.refresh_from_db()
        _finish(run, "failed", str(exc))
        log(run, "error", str(exc))
    except Exception as exc:  # noqa: BLE001 - shown on the run page, never silent
        run.refresh_from_db()
        _finish(run, "failed", f"{type(exc).__name__}: {exc}")
        log(run, "error", f"Kutilmagan xato: {type(exc).__name__}: {exc}")
    finally:
        db.close()
    return run


def resume_run(run: Run) -> Run:
    """Restart a stopped run in the same folder: finished flows are not repeated (FR-E12)."""
    if run.status not in {"failed", "cancelled"}:
        raise RunError("Faqat to'xtagan ishni davom ettirish mumkin")
    run.status = "queued"
    run.cancel_requested = False
    run.error = ""
    run.finished_at = None
    run.save()
    from runs.tasks import execute_run_task

    execute_run_task(run.pk)
    return run


def run_files(run: Run) -> list[dict[str, Any]]:
    """Downloadable results of a run (only files inside run_dir)."""
    base = Path(run.run_dir)
    names = [
        ("dist/html/index.html", "Yo'riqnoma (HTML)"),
        ("dist/manual.pdf", "PDF"),
        ("dist/manual.docx", "DOCX"),
        ("dist/coverage_report.html", "Qamrov hisoboti"),
        ("blueprint.json", "blueprint.json"),
        ("bundle.zip", "bundle.zip"),
        ("scan_report.md", "Skan hisoboti"),
        ("manual.json", "manual.json"),
    ]
    out = []
    for rel, label in names:
        path = base / rel
        if path.is_file():
            import hashlib

            out.append(
                {
                    "rel": rel,
                    "label": label,
                    "size": path.stat().st_size,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest()
                    if rel in {"blueprint.json", "bundle.zip"}
                    else "",
                }
            )
    return out


def blueprint_version_for(run: Run) -> BlueprintVersion:
    return run.blueprint
