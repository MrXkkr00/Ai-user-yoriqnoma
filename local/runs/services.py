"""Runs: start, execute (explore -> write -> render), cancel, human input (FR-L4, FR-L7).

Modes with an admin login (2: code + admin, 3: admin only): before exploring, test users
of the needed roles are made through the admin panel; mode 3 then learns the pages and
tasks from the site itself (core discovery). Right after exploring — also when it fails
or is cancelled — the test users and what they created are removed (``provision.json``
keeps the list, «Tozalashni qayta urinish» repeats it).

The core pipeline runs in an asyncio loop inside a Huey worker thread (never in a view).
Django ORM calls from that loop go through ``_db``: a dedicated thread, because Django
forbids synchronous ORM calls from an async context.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
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
from yoriqnoma_core.safety.sso import parse_hosts
from yoriqnoma_core.writer.providers import OllamaProvider
from yoriqnoma_core.writer.providers.base import ProviderError
from yoriqnoma_local.keys import decrypt, encrypt, pseudonym_key
from yoriqnoma_schemas import Blueprint, CaptureRun, load_json, save_json

T = TypeVar("T")
FORMATS = ("html", "pdf", "docx", "tour", "gif")
DEFAULT_FORMATS = ("html", "pdf", "docx")
# Sites without code (modes 3, 4): every link of the site is followed (two samples of each
# page template), and the agent then picks the tasks worth a manual.
DISCOVERY_MAX_PAGES = 150
DISCOVERY_AGENT_STEPS = 30


class DeleteBlocked(RuntimeError):
    """Deleting is refused; the reason is shown to the user."""


ACTIVE_STATUSES = {"queued", "running", "waiting_input"}


def remove_run_folder(path: Path) -> None:
    """Delete a folder of ``var/runs`` (never anything outside it, never the root itself)."""
    root = Path(settings.MEDIA_ROOT).resolve()
    target = path.resolve()
    if target == root or root not in target.parents:
        raise DeleteBlocked(f"Papka ish papkalari ichida emas, o'chirilmadi: {target}")
    if target.exists():
        shutil.rmtree(target)


def block_reason(run: Run) -> str:
    """Why this run must not be deleted now ('' when it may be)."""
    if run.status in ACTIVE_STATUSES:
        return "Ish hali ishlayapti: avval uni bekor qiling."
    from yoriqnoma_core.provision.base import Ledger

    ledger = Path(run.run_dir) / "provision.json"
    if ledger.is_file() and Ledger(ledger).pending():
        return (
            "Saytda vosita yaratgan test foydalanuvchilar hali o'chirilmagan: avval "
            "«Tozalashni qayta urinish» tugmasini bosing."
        )
    return ""


def delete_run(run: Run) -> None:
    """Remove the run, its folder (HTML, PDF, DOCX, capture) and its log."""
    reason = block_reason(run)
    if reason:
        raise DeleteBlocked(reason)
    folder = Path(run.run_dir)
    run.delete()
    remove_run_folder(folder)


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
    previous: Run | None = None,
) -> Run:
    """Create a run (one per role) and queue it. ``blueprint`` output finishes at once."""
    version = project.current_blueprint()
    if version is None:
        raise RunError("Avval loyihani skanerlang yoki blueprint yuklang")
    bp, _ = effective_blueprint(version)
    if output == "blueprint" and project.discovers_site:
        raise RunError(
            "Kodsiz rejimda sahifa va vazifalar faqat ish davomida saytdan o'rganiladi. "
            "«To'liq yo'riqnoma» yoki «Bundle» ni tanlang; blueprint.json ish natijalarida bo'ladi."
        )
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
        formats=[f for f in (formats or list(DEFAULT_FORMATS)) if f in FORMATS] or ["html"],
        run_dir=str(run_dir),
        previous=previous,
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
    text = message[:2000]
    event = RunEvent.objects.create(run=run, level=level, stage=stage or run.stage, message=text)
    # the same line goes to logs/run.jsonl in the run folder (NFR-6; no secrets are logged)
    try:
        path = Path(run.run_dir) / "logs" / "run.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        line = {"at": event.at.isoformat(timespec="seconds"), "level": level}
        line.update({"stage": event.stage, "message": text})
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(line, ensure_ascii=False) + "\n")
    except OSError:  # the DB copy is the source of truth; a full disk must not stop a run
        pass


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


def explore_options(
    run: Run,
    mailbox_target: str | None = None,
    created: dict[str, dict[str, AccountCredentials]] | None = None,
) -> ExploreOptions:
    project = run.project
    accounts = {
        role: {
            alias: AccountCredentials(login=login, password=SecretStr(password))
            for alias, (login, password) in aliases.items()
        }
        for role, aliases in accounts_for(project).items()
    }
    for role, aliases in (created or {}).items():  # test users made through the admin
        accounts.setdefault(role, {}).update(aliases)
    return ExploreOptions(
        base_url=project.base_url,
        role=run.role,
        environment=project.environment,  # type: ignore[arg-type]
        accounts=accounts,
        mailbox_kind="mailpit" if project.mailbox_kind == "mailpit" else "dir",
        mailbox_target=mailbox_target or project.mailbox_target,
        allow_private=True,  # the local app may study a site on 127.0.0.1 (TZ SEC-10)
        headless=True,
        device_scale_factor=2.0,  # sharp images in the manual (2x)
        pseudonym_key=SecretBytes(pseudonym_key()),
        run_id=Path(run.run_dir).name,
        pseudonym_scope=previous_scope(run),
        trusted_hosts=list(parse_hosts(project.sso_hosts)),
    )


def previous_scope(run: Run) -> str:
    """An update keeps the fakes of the run it updates, so unchanged screens match."""
    if run.previous is None:
        return ""
    path = Path(run.previous.run_dir) / "capture" / "capture.json"
    if not path.is_file():
        return ""
    old = load_json(path, CaptureRun)
    return old.pseudonym_scope or old.run_id


def update_run(run: Run) -> Run:
    """A new full run of the same role that compares itself with ``run`` (T30)."""
    if run.output != "full" or run.status != "done":
        raise RunError("Faqat tayyor «To'liq yo'riqnoma» natijasini yangilash mumkin")
    return start_run(run.project, "full", run.role, run.model, list(run.formats), previous=run)


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


def needed_roles(run: Run, bp: Blueprint) -> dict[str, tuple[str, str]]:
    """Roles that get admin-made test users: the target role (A and B) and, in mode 2,
    the helper roles its tasks need (A). Roles the admin does not have are left to the
    owner's accounts or to sign-up."""
    project = run.project
    matched: dict[str, str] = dict((run.blueprint.stats or {}).get("admin_roles", {}))
    label = {r.id: r.label for r in bp.roles}
    out: dict[str, tuple[str, str]] = {run.role: (label.get(run.role, run.role), "AB")}
    if project.mode == "code_admin":
        target = [f.id for f in bp.flows_for_role(run.role)]
        for flow in bp.requirement_closure(target):
            if flow.role not in {"guest", run.role} and matched.get(flow.role):
                out.setdefault(flow.role, (label.get(flow.role, flow.role), "A"))
        if not matched.get(run.role):
            out.pop(run.role)
    return out


def fetch_site_file(url: str) -> str | None:
    """A JS file or source map of the studied site (mode 3 discovery)."""
    import httpx

    from yoriqnoma_core.safety.url_guard import UrlBlocked, check_url

    try:
        check_url(url, allow_private=True)
        answer = httpx.get(url, timeout=10, follow_redirects=False)
    except (UrlBlocked, httpx.HTTPError):
        return None
    if answer.status_code != 200 or len(answer.content) > 16 * 1024 * 1024:
        return None
    return answer.text


def discover_blueprint(
    run: Run,
    roles_bp: Blueprint,
    created: dict[str, dict[str, AccountCredentials]],
    human: DbHumanInput,
    progress: DbProgressSink,
    cancel: DbCancelToken,
) -> Blueprint:
    """Mode 3: pages, forms and tasks of the role, learned from the site itself."""
    from yoriqnoma_core.discovery.kit import ScoutKit
    from yoriqnoma_core.discovery.run import DiscoveryFailed, DiscoveryInput, discover_site
    from yoriqnoma_schemas import Policy

    role = roles_bp.role(run.role)
    opts = explore_options(run, created=created)
    kit = ScoutKit.create(opts, Path(run.run_dir), Policy(target_role=run.role))
    given = created.get(run.role) or opts.accounts.get(run.role, {})  # test users or the owner's
    inp = DiscoveryInput(
        base_url=run.project.base_url,
        role=run.role,
        role_label=role.label if role else run.role,
        project=run.project.name,
        accounts=given,
        start_urls=run.project.start_urls,
        allow_signup=False,
        fetch_text=fetch_site_file,
        classify=provider_for(run),
        agent=provider_for(run),
        max_pages=DISCOVERY_MAX_PAGES,
        agent_steps=DISCOVERY_AGENT_STEPS,
        generator="yoriqnoma-local discovery",
    )
    progress.stage("explore", 80)
    try:
        bp = asyncio.run(discover_site(kit, inp, human, progress, cancel))
    except DiscoveryFailed as exc:
        raise RunAborted(str(exc)) from exc
    known = {r.id for r in bp.roles}
    kept = [r for r in roles_bp.roles if r.id not in known]  # roles read from the admin panel
    if kept:
        bp = bp.model_copy(update={"roles": [*bp.roles, *kept]})
    version = _discovered_version(run, bp)
    Run.objects.filter(pk=run.pk).update(blueprint=version)
    return bp


def _discovered_version(run: Run, bp: Blueprint) -> BlueprintVersion:
    from projects.services import _new_version

    stats = dict(run.blueprint.stats or {})
    stats.update({"flows": len(bp.flows), "pages": len(bp.pages)})
    return _new_version(run.project, bp, "discovered", stats=stats)


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
        capture = explore_with_test_users(run, bp, run_dir, human, progress, cancel)
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
                    previous=Path(run.previous.run_dir) if run.previous else None,
                )
            )
            stats["coverage"] = manual.coverage.percent.get("total", 0)
            stats["needs_review"] = sum(a.needs_review for s in manual.sections for a in s.articles)
            Run.objects.filter(pk=run.pk).update(stage="render")
            run_render(run_dir, set(run.formats))
        run.refresh_from_db()
        run.stats = {**(run.stats or {}), **stats}
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


def explore_with_test_users(
    run: Run,
    bp: Blueprint,
    run_dir: Path,
    human: DbHumanInput,
    progress: DbProgressSink,
    cancel: DbCancelToken,
) -> CaptureRun:
    """Explore; in admin modes with test users made before and removed right after."""
    if run.project.mode == "account":
        # mode 4: the owner's account of one role; nothing is created, nothing to clean up
        log(run, "info", "Berilgan akkaunt bilan sayt o'rganilmoqda", "explore")
        bp = discover_blueprint(run, bp, {}, human, progress, cancel)
        return asyncio.run(run_explore(bp, run_dir, explore_options(run), human, progress, cancel))
    if not run.project.uses_admin:
        return asyncio.run(run_explore(bp, run_dir, explore_options(run), human, progress, cancel))
    from projects.admin_access import ProvisionSession, report_dict

    db = _DbThread()  # the admin session logs from its event loop: ORM on its own thread
    session = ProvisionSession(
        run.project,
        run_dir,
        run_dir.name,
        lambda level, msg: db(lambda: log(run, level, msg, "explore")),
    )
    try:
        log(run, "info", "Admin orqali test foydalanuvchilar yaratilmoqda", "explore")
        if run.project.environment == "production":
            log(
                run,
                "warning",
                "Ishchi (production) sayt: test foydalanuvchilar haqiqiy saytda yaratiladi va "
                "ish oxirida o'chiriladi. Iloji bo'lsa staging nusxadan foydalaning.",
                "explore",
            )
        created = asyncio.run(session.create(needed_roles(run, bp)))
        if run.project.mode == "admin":
            bp = discover_blueprint(run, bp, created, human, progress, cancel)
        opts = explore_options(run, created=created)
        return asyncio.run(run_explore(bp, run_dir, opts, human, progress, cancel))
    finally:
        own = own_objects_of(run_dir)
        try:
            report = asyncio.run(session.cleanup(own))
            result = report_dict(report)
        except Exception as exc:  # noqa: BLE001 - reported on the run page, never silent
            result = {"clean": False, "left": [f"tozalash ishlamadi: {exc}"[:300]]}
            log(run, "error", f"Tozalash ishlamadi: {exc}", "explore")
        stats = dict(Run.objects.get(pk=run.pk).stats or {})
        stats["cleanup"] = result
        Run.objects.filter(pk=run.pk).update(stats=stats)
        db.close()


def own_objects_of(run_dir: Path) -> dict[str, list[str]]:
    """Objects the test users made (capture.json, or progress.json if it stopped early)."""
    import json

    for name in ("capture.json", "progress.json"):
        path = run_dir / "capture" / name
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            own = data.get("own_objects") or {}
            return {str(k): [str(i) for i in v] for k, v in own.items()}
    return {}


def retry_cleanup(run_id: int) -> Run:
    """«Tozalashni qayta urinish»: remove what is still on the site from provision.json."""
    from projects.admin_access import ProvisionSession, report_dict

    run = Run.objects.select_related("project").get(pk=run_id)
    run_dir = Path(run.run_dir)
    db = _DbThread()
    session = ProvisionSession(
        run.project,
        run_dir,
        run_dir.name,
        lambda level, msg: db(lambda: log(run, level, msg, "explore")),
    )
    try:
        result = report_dict(asyncio.run(session.cleanup(own_objects_of(run_dir))))
    except Exception as exc:  # noqa: BLE001 - shown on the run page
        result = {"clean": False, "left": [f"tozalash ishlamadi: {exc}"[:300]]}
    finally:
        db.close()
    run.refresh_from_db()
    stats = dict(run.stats or {})
    stats["cleanup"] = result
    run.stats = stats
    run.save(update_fields=["stats"])
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
        ("dist/changelog.md", "O'zgarishlar ro'yxati (oldingi natijaga nisbatan)"),
        ("dist/tour/tour.js", "Interaktiv tur: tour.js (Driver.js)"),
        ("dist/tour/tours.json", "Interaktiv tur: tours.json"),
        ("dist/tour/README.md", "Interaktiv tur: qo'llanma"),
        ("blueprint.json", "blueprint.json"),
        ("bundle.zip", "bundle.zip"),
        ("scan_report.md", "Skan hisoboti"),
        ("manual.json", "manual.json"),
    ]
    gifs = sorted((base / "dist" / "gif").glob("*.gif"))
    names += [(f"dist/gif/{g.name}", f"GIF: {g.stem}") for g in gifs]
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
