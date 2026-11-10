"""One job from start to finish (ARCHITECTURE §7.3), run by the Celery worker.

    queued -> preflight -> (scouting) -> exploring -> writing -> rendering -> done
                  waiting_input (SMS, captcha) in between; failed | cancelled at any time

* A:    uploaded blueprint -> explorer -> writer (Claude) -> renderer
* A':   uploaded bundle (capture already made by the local app) -> writer -> renderer
* B:    scout builds a blueprint from the site itself -> explorer -> writer -> renderer
* A+B:  uploaded blueprint first, the scout adds only what is new (merge) -> ...

The worker's run folder is temporary: results go to storage (MinIO) as artifacts and the
folder is removed when the job finishes. Passwords are removed from the database then too.
The Claude key is read from the worker's own environment here, nowhere else.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import os
import shutil
import zipfile
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.files.base import ContentFile
from django.utils import timezone
from pydantic import SecretBytes, SecretStr

from jobs.models import Artifact, Job
from jobs.sinks import (
    DbThread,
    JobCancelToken,
    JobHumanInput,
    JobProgressSink,
    add_event,
    set_status,
)
from jobs.uploads import UploadError, read_blueprint, read_bundle_file
from security.logfilter import mask_secrets
from security.robots import deny_globs, fetch_robots
from security.secrets import decrypt_json
from security.ssrf import check_public_url, private_allowed
from yoriqnoma_core.pipeline import (
    AccountCredentials,
    Cancelled,
    ExploreOptions,
    HumanInput,
    ProgressSink,
    RunAborted,
    run_explore,
    run_render,
    run_write,
)
from yoriqnoma_core.safety.url_guard import UrlBlocked
from yoriqnoma_core.writer.providers.base import LLMProvider, ProviderError
from yoriqnoma_core.writer.providers.claude import ClaudeProvider, make_sanitizer, prices_from
from yoriqnoma_schemas import Blueprint, CaptureRun, load_json

SOURCE_MODE = {"A": "A", "A_PRIME": "A'", "B": "B", "A_PLUS_B": "A+B"}
ARTIFACTS = [
    ("dist/manual.pdf", "manual.pdf", "PDF"),
    ("dist/manual.docx", "manual.docx", "DOCX"),
    ("dist/coverage_report.html", "coverage_report.html", "Qamrov hisoboti"),
    ("manual.json", "manual.json", "manual.json"),
    ("blueprint.json", "blueprint.json", "blueprint.json"),
]
FOLDERS = [
    ("dist/html", "manual-html.zip", "Yo'riqnoma (HTML, offline sayt)"),
    ("dist/tour", "tour.zip", "Interaktiv tur (Driver.js)"),
    ("dist/gif", "gif.zip", "GIF'lar"),
]

ProviderFactory = Callable[[Job, Path, ProgressSink], LLMProvider]
Explore = Callable[..., Coroutine[Any, Any, CaptureRun]]


class JobFailed(Exception):
    """A clear reason for the user; the job fails with it."""


def claude_provider(job: Job, run_dir: Path, progress: ProgressSink) -> LLMProvider:
    """The writer's provider: Claude, with the job budget and the SEC-7 checks."""
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        raise JobFailed("Claude API kaliti workerda yo'q (ANTHROPIC_API_KEY)")
    capture = load_json(run_dir / "capture" / "capture.json", CaptureRun)
    spent = float(Job.objects.values_list("cost_usd", flat=True).get(pk=job.pk))
    return ClaudeProvider(
        api_key=SecretStr(key),
        models=dict(settings.YORIQNOMA_MODELS),
        prices=prices_from(settings.YORIQNOMA_PRICES),
        budget_usd=max(0.0, float(job.budget_usd) - spent),
        on_cost=lambda payload: progress.event(str(payload.get("kind", "cost")), payload),
        sanitize=make_sanitizer(set(capture.test_values) | set(capture.public_values)),
        image_roots=[run_dir / "capture"],
    )


# Replaced in tests (no Claude, no browser in unit tests).
provider_factory: ProviderFactory = claude_provider
explore: Explore = run_explore


def run_dir_for(job: Job) -> Path:
    return Path(settings.VAR_DIR) / "jobs" / str(job.pk)


def _accounts(job: Job) -> dict[str, dict[str, AccountCredentials]]:
    raw: dict[str, dict[str, dict[str, str]]] = decrypt_json(job.accounts_enc) or {}
    return {
        role: {
            alias: AccountCredentials(login=c["login"], password=SecretStr(c["password"]))
            for alias, c in aliases.items()
        }
        for role, aliases in raw.items()
    }


def explore_options(job: Job) -> ExploreOptions:
    key = str(settings.YORIQNOMA_PSEUDONYM_KEY).encode("utf-8")
    return ExploreOptions(
        base_url=job.url,
        role=job.role,
        environment=job.environment,  # type: ignore[arg-type]
        accounts=_accounts(job),
        mailbox_kind="mailpit",
        mailbox_target=str(settings.YORIQNOMA_MAILPIT_URL),
        mail_domain=str(settings.YORIQNOMA_MAIL_DOMAIN),
        # the server never visits private addresses (TZ SEC-10); the only exception is the
        # e2e test site named in YORIQNOMA_PRIVATE_ALLOWLIST (always empty in prod.py)
        allow_private=private_allowed(job.url),
        passive=job.passive,
        headless=True,
        device_scale_factor=2.0,
        pseudonym_key=SecretBytes(key),
        run_id=f"job-{job.pk}",
        step_delay_ms=int(1000 / max(0.5, float(settings.YORIQNOMA_REQUESTS_PER_SECOND))),
    )


def _with_deny(bp: Blueprint, extra: list[str]) -> Blueprint:
    if not extra:
        return bp
    deny = sorted(set(bp.policy.deny_paths) | set(extra))
    return bp.model_copy(update={"policy": bp.policy.model_copy(update={"deny_paths": deny})})


def _zip_folder(folder: Path) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(folder).as_posix())
    return buffer.getvalue()


def store_artifacts(job: Job, run_dir: Path) -> list[Artifact]:
    stored = []
    items: list[tuple[str, str, bytes]] = []
    for rel, name, label in ARTIFACTS:
        path = run_dir / rel
        if path.is_file():
            items.append((name, label, path.read_bytes()))
    for rel, name, label in FOLDERS:
        folder = run_dir / rel
        if folder.is_dir() and any(folder.iterdir()):
            items.append((name, label, _zip_folder(folder)))
    for name, label, data in items:
        Artifact.objects.filter(job=job, name=name).delete()
        artifact = Artifact(
            job=job,
            name=name,
            label=label,
            size=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
        )
        artifact.file.save(name, ContentFile(data), save=False)
        artifact.save()
        add_event(job.pk, "artifact", {"name": name, "size": len(data)})
        stored.append(artifact)
    return stored


def _finish(job_id: int, status: str, error: str = "") -> None:
    Job.objects.filter(pk=job_id).update(
        status=status,
        error=mask_secrets(error)[:4000],
        finished_at=timezone.now(),
        accounts_enc=None,  # passwords live only as long as the job (TZ SEC-12)
    )
    add_event(job_id, "status", {"status": status, "error": mask_secrets(error)[:500]})


def _preflight(job: Job, progress: ProgressSink) -> list[str]:
    """URL check again (DNS may have changed since creation) and robots.txt."""
    if job.mode == "A_PRIME":
        return []
    try:
        check_public_url(job.url)
    except UrlBlocked as exc:
        raise JobFailed(f"Sayt manziliga kirib bo'lmaydi: {exc}") from exc
    robots = fetch_robots(job.url)
    if robots.disallow_all and job.passive:
        raise JobFailed("robots.txt saytni o'rganishni taqiqlaydi (passiv rejim)")
    extra = deny_globs(robots) if job.passive else []
    if robots.disallowed_paths:
        progress.log(
            "info",
            f"robots.txt: {len(robots.disallowed_paths)} ta yopiq yo'l"
            + (" — passiv rejimda ular o'rganilmaydi" if job.passive else ""),
        )
    return extra


def _blueprint_for(
    job: Job, run_dir: Path, human: HumanInput, progress: ProgressSink, cancel: JobCancelToken
) -> Blueprint:
    uploaded: Blueprint | None = None
    if job.mode in {"A", "A_PLUS_B"}:
        if not job.blueprint:
            raise JobFailed("blueprint.json fayli topilmadi")
        with job.blueprint.open("rb") as stream:
            uploaded = read_blueprint(stream)
    if job.mode == "A":
        assert uploaded is not None
        return uploaded
    from scout.discover import discover

    discovered = asyncio.run(discover(job, run_dir, human, progress, cancel, base=uploaded))
    if uploaded is None:
        return discovered
    from yoriqnoma_core.discovery.merge import merge

    merged, notes = merge(uploaded, discovered)
    for note in notes:
        progress.log("info", note)
    return merged


def execute(job_id: int) -> Job:
    job = Job.objects.get(pk=job_id)
    if job.finished:
        return job
    if job.cancel_requested:
        _finish(job.pk, "cancelled")
        return Job.objects.get(pk=job_id)
    job.started_at = job.started_at or timezone.now()
    job.save(update_fields=["started_at"])
    run_dir = run_dir_for(job)
    run_dir.mkdir(parents=True, exist_ok=True)
    db = DbThread()
    progress = JobProgressSink(job.pk, db)
    cancel = JobCancelToken(job.pk, db)
    human = JobHumanInput(job.pk, db, timeout_s=int(settings.YORIQNOMA_INPUT_TIMEOUT_S))
    final_status, error = "done", ""
    try:
        set_status(job.pk, "preflight")
        extra_deny = _preflight(job, progress)
        if job.mode == "A_PRIME":
            if not job.bundle:
                raise JobFailed("bundle.zip fayli topilmadi")
            local = run_dir / "upload" / "bundle.zip"
            local.parent.mkdir(parents=True, exist_ok=True)
            with job.bundle.open("rb") as stream, local.open("wb") as out:
                shutil.copyfileobj(stream, out)
            bundle = read_bundle_file(local)
            bundle.extract(run_dir)
            shutil.rmtree(local.parent, ignore_errors=True)
            progress.log("info", f"bundle ochildi: {len(bundle.capture.states)} ta ekran")
        else:
            bp = _with_deny(_blueprint_for(job, run_dir, human, progress, cancel), extra_deny)
            if bp.role(job.role) is None or bp.role(job.role).kind != "role":  # type: ignore[union-attr]
                raise JobFailed(f"«{job.role}» roli saytda topilmadi yoki taqiqlangan")
            capture = asyncio.run(
                explore(bp, run_dir, explore_options(job), human, progress, cancel)
            )
            verified = sum(1 for f in capture.flows if not f.helper and f.status == "verified")
            total = sum(1 for f in capture.flows if not f.helper)
            Job.objects.filter(pk=job.pk).update(
                stats={
                    "flows_verified": verified,
                    "flows_total": total,
                    "states": len(capture.states),
                }
            )
        if cancel.is_cancelled():
            raise Cancelled("ish bekor qilindi")
        job.refresh_from_db()
        provider = provider_factory(job, run_dir, progress)
        manual = asyncio.run(
            run_write(
                run_dir,
                provider,
                progress,
                cancel,
                cache_dir=Path(settings.VAR_DIR) / "cache" / "llm",
                source_mode=SOURCE_MODE[job.mode],
            )
        )
        progress.stage("render", 1)
        run_render(run_dir, set(job.formats))
        store_artifacts(job, run_dir)
        stats: dict[str, Any] = dict(Job.objects.get(pk=job.pk).stats or {})
        stats["coverage"] = manual.coverage.percent.get("total", 0)
        stats["needs_review"] = sum(a.needs_review for s in manual.sections for a in s.articles)
        Job.objects.filter(pk=job.pk).update(stats=stats)
    except Cancelled:
        final_status, error = "cancelled", ""
    except (JobFailed, RunAborted, ProviderError, UploadError) as exc:
        final_status, error = "failed", str(exc)
    except Exception as exc:  # noqa: BLE001 - shown on the job page, never silent
        final_status, error = "failed", f"Kutilmagan xato: {type(exc).__name__}: {exc}"
    finally:
        progress.flush()
        db.close()
    _finish(job.pk, final_status, error)
    if error:
        add_event(job.pk, "log", {"level": "error", "message": mask_secrets(error)[:2000]})
    shutil.rmtree(run_dir, ignore_errors=True)
    return Job.objects.get(pk=job_id)
