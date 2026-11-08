"""Jobs: create (checks, limits, uploads), cancel, answer input, events (ARCHITECTURE §7).

Business logic lives here; web views and the DRF API both call these functions.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from functools import partial
from io import BytesIO
from pathlib import Path
from typing import IO, Any

from django.conf import settings
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from domains.services import domain_for
from jobs.budget import check_budget
from jobs.models import ACTIVE, InputRequest, Job, JobEvent
from jobs.uploads import UploadError, read_blueprint, read_bundle
from security.secrets import encrypt_json, encrypt_text
from security.ssrf import check_public_url
from yoriqnoma_core.safety.url_guard import UrlBlocked
from yoriqnoma_schemas import Blueprint, RoleInfo

FORMATS = ("html", "pdf", "docx", "tour", "gif")
DEFAULT_FORMATS = ["html", "pdf", "docx"]
MODES = {"A", "A_PRIME", "B", "A_PLUS_B"}
ROLE_ID_CHARS = set("abcdefghijklmnopqrstuvwxyz0123456789_-")


class JobError(ValueError):
    """The job cannot be created; the message is shown to the user (Uzbek)."""


@dataclass
class JobRequest:
    mode: str
    url: str = ""
    environment: str = "staging"
    language: str = "uz"
    formats: list[str] = field(default_factory=lambda: list(DEFAULT_FORMATS))
    roles: list[str] = field(default_factory=list)  # one job per role (TZ FR-RL3)
    role_label: str = ""  # mode B: the name the user gave the role
    # role -> alias ("A"/"B") -> {"login", "password"} (TZ FR-RL4)
    accounts: dict[str, dict[str, dict[str, str]]] = field(default_factory=dict)
    budget_usd: Decimal | None = None
    source: str = "web"
    blueprint: IO[bytes] | None = None
    bundle: IO[bytes] | None = None


def parse_budget(raw: Any) -> Decimal | None:
    if raw in (None, ""):
        return None
    try:
        return Decimal(str(raw)).quantize(Decimal("0.01"))
    except InvalidOperation as exc:
        raise JobError("Byudjet raqam bo'lishi kerak (masalan, 3.00)") from exc


def selectable_roles(bp: Blueprint) -> list[RoleInfo]:
    """Roles a manual can be written for (never admin-like or unclear ones, TZ FR-RL2)."""
    return [r for r in bp.roles if r.kind == "role"]


def role_cards(bp: Blueprint) -> list[dict[str, Any]]:
    """Role options for the "new job" form: pages and tasks per role (TZ FR-RL3)."""
    cards = []
    for role in bp.roles:
        if role.kind == "guest":
            continue
        pages = sum(1 for p in bp.pages if role.id in p.roles)
        tasks = sum(1 for f in bp.flows if f.role == role.id)
        cards.append(
            {
                "id": role.id,
                "label": role.label,
                "description": role.description or "",
                "selectable": role.kind == "role",
                "reason": role.reason,
                "pages": pages,
                "tasks": tasks,
                "self_signup": role.self_signup,
            }
        )
    return cards


def _check_formats(formats: list[str]) -> list[str]:
    chosen = [f for f in formats if f in FORMATS]
    unknown = sorted(set(formats) - set(FORMATS))
    if unknown:
        raise JobError(f"Noma'lum format: {', '.join(unknown)}")
    return chosen or ["html"]


def _check_accounts(accounts: dict[str, Any]) -> dict[str, dict[str, dict[str, str]]]:
    clean: dict[str, dict[str, dict[str, str]]] = {}
    for role, aliases in (accounts or {}).items():
        if not isinstance(aliases, dict):
            raise JobError("Akkauntlar formati noto'g'ri")
        for alias, cred in aliases.items():
            if alias not in {"A", "B"} or not isinstance(cred, dict):
                raise JobError("Akkaunt nomi faqat A yoki B bo'ladi")
            login = str(cred.get("login", "")).strip()
            password = str(cred.get("password", ""))
            if not login and not password:
                continue
            if not login or not password:
                raise JobError(f"«{role}» {alias} akkaunti uchun login va parol kerak")
            clean.setdefault(str(role), {})[alias] = {"login": login, "password": password}
    return clean


def _check_url(url: str) -> str:
    if not url:
        raise JobError("Sayt manzili (URL) kiritilmagan")
    try:
        return check_public_url(url)
    except UrlBlocked as exc:
        raise JobError(f"Bu manzilga kirib bo'lmaydi: {exc}") from exc


def _role_id(raw: str) -> str:
    role = raw.strip().lower()
    if not role or not set(role) <= ROLE_ID_CHARS or len(role) > 64:
        raise JobError("Rol nomi lotin harflari, raqam va _ dan iborat bo'lsin (masalan, manager)")
    if role in {"admin", "administrator", "superadmin", "root", "superuser", "staff"}:
        raise JobError("Administrator va adminga o'xshash rollar uchun yo'riqnoma yozilmaydi")
    return role


@transaction.atomic
def create_jobs(owner: User, req: JobRequest) -> list[Job]:
    """Check everything, then create one job per chosen role and queue them."""
    if req.mode not in MODES:
        raise JobError("Rejim noto'g'ri")
    if req.environment not in {"staging", "production"}:
        raise JobError("Muhit faqat staging yoki production")
    formats = _check_formats(req.formats)
    accounts = _check_accounts(req.accounts)
    budget = req.budget_usd or Decimal(str(settings.YORIQNOMA_DEFAULT_JOB_BUDGET_USD))

    blueprint: Blueprint | None = None
    blueprint_raw: bytes | None = None
    bundle_name = ""
    url = req.url.strip()
    roles: list[tuple[str, str]] = []

    if req.mode in {"A", "A_PLUS_B"}:
        if req.blueprint is None:
            raise JobError("A rejimi uchun lokal dastur yaratgan blueprint.json faylini yuklang")
        if getattr(req.blueprint, "name", "").lower().endswith(".zip"):
            raise JobError("A rejimiga blueprint.json kerak; bundle.zip A' rejimi uchun")
        blueprint_raw = req.blueprint.read(int(settings.YORIQNOMA_BLUEPRINT_MAX_BYTES) + 1)
        try:
            blueprint = read_blueprint(BytesIO(blueprint_raw))
        except UploadError as exc:
            raise JobError(str(exc)) from exc
        url = url or str(blueprint.base_url)
        allowed = {r.id: r for r in selectable_roles(blueprint)}
        if not req.roles:
            raise JobError("Kamida bitta rolni tanlang")
        for role_id in req.roles:
            info = allowed.get(role_id)
            if info is None:
                raise JobError(
                    f"«{role_id}» rolini tanlab bo'lmaydi (yo'q yoki chiqarib tashlangan)"
                )
            roles.append((info.id, info.label))
    elif req.mode == "A_PRIME":
        if req.bundle is None:
            raise JobError("A' rejimi uchun lokal dastur yaratgan bundle.zip faylini yuklang")
        if getattr(req.bundle, "name", "").lower().endswith(".json"):
            raise JobError("A' rejimiga bundle.zip kerak; blueprint.json A rejimi uchun")
        with tempfile.TemporaryDirectory(prefix="bundle-check-") as tmp:
            try:
                bundle = read_bundle(req.bundle, Path(tmp))
            except UploadError as exc:
                raise JobError(str(exc)) from exc
        url = str(bundle.capture.base_url)
        roles.append((bundle.capture.role, bundle.capture.role_label or bundle.capture.role))
        req.bundle.seek(0)
        bundle_name = "bundle.zip"
    else:  # B
        if not req.roles:
            raise JobError("Qaysi rol uchun yo'riqnoma yozilishini kiriting (masalan, customer)")
        for raw in req.roles:
            role_id = _role_id(raw)
            roles.append((role_id, req.role_label.strip() or role_id))

    domain = None
    passive = False
    if req.mode != "A_PRIME":
        url = _check_url(url)
        domain = domain_for(owner, url)
        if domain is None:
            raise JobError(
                "Bu sayt domeni ro'yxatingizda yo'q. Avval «Domenlar» sahifasida qo'shing "
                "(tasdiqlanmagan domenda faqat passiv rejim ishlaydi)."
            )
        passive = not domain.verified

    check_budget(owner, budget * len(roles))
    jobs = []
    for role_id, label in roles:
        job = Job(
            owner=owner,
            domain=domain,
            mode=req.mode,
            url=url,
            environment=req.environment,
            language=req.language or "uz",
            formats=formats,
            role=role_id,
            role_label=label,
            budget_usd=budget,
            passive=passive,
            source=req.source,
            expires_at=timezone.now() + timedelta(days=int(settings.YORIQNOMA_RETENTION_DAYS)),
            accounts_enc=encrypt_json(accounts) if accounts else None,
        )
        if blueprint_raw is not None:
            job.blueprint.save("blueprint.json", ContentFile(blueprint_raw), save=False)
        if bundle_name and req.bundle is not None:
            req.bundle.seek(0)
            job.bundle.save(bundle_name, ContentFile(req.bundle.read()), save=False)
        job.save()
        JobEvent.objects.create(job=job, kind="status", payload={"status": "queued"})
        if passive:
            JobEvent.objects.create(
                job=job,
                kind="log",
                payload={
                    "level": "warning",
                    "message": "Domen tasdiqlanmagan: passiv rejim — faqat ochiq sahifalar, "
                    "ro'yxatdan o'tish va forma yuborish yo'q (SEC-9).",
                },
            )
        jobs.append(job)
    for job in jobs:
        transaction.on_commit(partial(enqueue, job.pk))
    return jobs


def enqueue(job_id: int) -> None:
    from jobs.tasks import run_job

    run_job.delay(job_id)


def cancel_job(job: Job) -> Job:
    if job.finished:
        return job
    job.cancel_requested = True
    fields = ["cancel_requested"]
    if job.status == "queued":
        job.status = "cancelled"
        job.finished_at = timezone.now()
        job.accounts_enc = None
        fields += ["status", "finished_at", "accounts_enc"]
    job.save(update_fields=fields)
    JobEvent.objects.create(
        job=job, kind="log", payload={"level": "warning", "message": "Bekor qilish so'raldi"}
    )
    return job


def answer_input(job: Job, request_id: int, value: str) -> InputRequest:
    request = InputRequest.objects.get(pk=request_id, job=job)
    if request.answered_at is not None:
        raise JobError("Bu so'rovga allaqachon javob berilgan")
    if not value.strip():
        raise JobError("Javob bo'sh")
    request.value_enc = encrypt_text(value.strip())
    request.answered_at = timezone.now()
    request.save(update_fields=["value_enc", "answered_at"])
    return request


def open_request(job: Job) -> InputRequest | None:
    return job.input_requests.filter(answered_at__isnull=True).last()


def events_after(job: Job, after: int = 0, limit: int = 200) -> list[JobEvent]:
    return list(job.events.filter(pk__gt=after).order_by("id")[:limit])


def active_jobs(owner: User) -> int:
    return Job.objects.filter(owner=owner, status__in=ACTIVE).count()
