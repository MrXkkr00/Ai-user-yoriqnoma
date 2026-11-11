"""Projects: scan the code, upload a blueprint, review overrides, role options (FR-L3..L5)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils.text import slugify
from pydantic import ValidationError

from projects.models import BlueprintVersion, Project, ProjectAccount
from yoriqnoma_local.keys import decrypt, encrypt
from yoriqnoma_scanner import __version__ as scanner_version
from yoriqnoma_scanner import overrides as scanner_overrides
from yoriqnoma_scanner.api import scan
from yoriqnoma_schemas import Blueprint, load_json, save_json


class BlueprintError(ValueError):
    pass


def project_dir(project: Project) -> Path:
    path = Path(settings.MEDIA_ROOT) / project.slug
    path.mkdir(parents=True, exist_ok=True)
    return path


def delete_project(project: Project) -> None:
    """Remove the project with its runs, blueprints, accounts and every file it made."""
    from runs.services import DeleteBlocked, block_reason, remove_run_folder

    runs = list(project.runs.all())
    for run in runs:
        reason = block_reason(run)
        if reason:
            raise DeleteBlocked(f"Ish {run.pk}: {reason}")
    folders = [Path(run.run_dir) for run in runs]
    folders.append(Path(settings.MEDIA_ROOT) / project.slug)
    with transaction.atomic():
        for run in runs:  # runs first: a run protects its blueprint version
            run.delete()
        project.delete()  # blueprints and accounts go with it
    for folder in folders:
        remove_run_folder(folder)


def unique_slug(name: str) -> str:
    base = slugify(name) or "loyiha"
    slug, n = base, 2
    while Project.objects.filter(slug=slug).exists():
        slug, n = f"{base}-{n}", n + 1
    return slug


def create_project(**fields: Any) -> Project:
    fields.setdefault("slug", unique_slug(str(fields.get("name", "loyiha"))))
    return Project.objects.create(**fields)


def set_account(project: Project, role: str, alias: str, login: str, password: str) -> None:
    ProjectAccount.objects.update_or_create(
        project=project,
        role=role,
        alias=alias,
        defaults={"login": login, "password_enc": encrypt(password)},
    )


def accounts_for(project: Project) -> dict[str, dict[str, tuple[str, str]]]:
    """role -> alias -> (login, password). Passwords are decrypted only in memory."""
    out: dict[str, dict[str, tuple[str, str]]] = {}
    for acc in project.accounts.all():
        out.setdefault(acc.role, {})[acc.alias] = (acc.login, decrypt(acc.password_enc))
    return out


def _new_version(
    project: Project,
    bp: Blueprint,
    source: str,
    report: str = "",
    stats: dict[str, Any] | None = None,
) -> BlueprintVersion:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    folder = project_dir(project) / "blueprints" / stamp
    path = save_json(folder / "blueprint.json", bp)
    report_path = ""
    if report:
        report_file = folder / "scan_report.md"
        report_file.write_text(report, encoding="utf-8")
        report_path = str(report_file)
    with transaction.atomic():
        project.blueprints.update(is_current=False)
        return BlueprintVersion.objects.create(
            project=project,
            scanner_version=scanner_version if source == "scan" else "",
            source=source,
            path=str(path),
            report_path=report_path,
            stats=stats or {},
            is_current=True,
        )


def scan_project(project: Project) -> BlueprintVersion:
    """Scan the project's code folder (only through SafeFS) into a new blueprint version."""
    if not project.source_dir:
        raise BlueprintError("Loyihada kod papkasi ko'rsatilmagan")
    result = scan(
        Path(project.source_dir), project.base_url, project=project.name, language=project.language
    )
    return _new_version(project, result.blueprint, "scan", result.report_md, result.stats)


def upload_blueprint(project: Project, raw: bytes) -> BlueprintVersion:
    try:
        bp = Blueprint.model_validate_json(raw)
    except ValidationError as exc:
        raise BlueprintError(f"blueprint.json sxemaga mos emas: {exc.errors()[0]['msg']}") from exc
    return _new_version(project, bp, "upload", stats={"flows": len(bp.flows)})


def raw_blueprint(version: BlueprintVersion) -> Blueprint:
    return load_json(version.path, Blueprint)


def effective_blueprint(version: BlueprintVersion) -> tuple[Blueprint, list[str]]:
    """The blueprint with review overrides applied (they can only reduce it)."""
    return scanner_overrides.apply(raw_blueprint(version), version.overrides or {})


def set_override(version: BlueprintVersion, kind: str, key: str, value: Any) -> list[str]:
    """Toggle an exclusion or rename a flow; validated by applying the overrides."""
    data: dict[str, Any] = dict(version.overrides or {})
    if kind in {"exclude_pages", "exclude_flows"}:
        items = set(data.get(kind, []))
        if value:
            items.add(key)
        else:
            items.discard(key)
        data[kind] = sorted(items)
    elif kind == "rename_flows":
        renames = dict(data.get("rename_flows", {}))
        if value:
            renames[key] = str(value)[:200]
        else:
            renames.pop(key, None)
        data["rename_flows"] = renames
    else:
        raise BlueprintError(f"noma'lum o'zgartirish: {kind}")
    _, notes = scanner_overrides.apply(raw_blueprint(version), data)
    version.overrides = data
    version.save(update_fields=["overrides"])
    return notes


@dataclass
class RoleOption:
    """One role card on the "new run" page (TZ FR-RL3)."""

    id: str
    label: str
    kind: str
    reason: str
    description: str
    pages: int
    flows: int
    self_signup: bool
    has_account: bool
    admin_made: bool = False  # modes 2 and 3: a test user is made through the admin

    @property
    def selectable(self) -> bool:
        return self.kind == "role"

    @property
    def account_note(self) -> str:
        if self.admin_made:
            return "Test foydalanuvchi admin orqali yaratiladi va ish oxirida o'chiriladi"
        if self.self_signup:
            return "Akkaunt shart emas: vosita o'zi ro'yxatdan o'tadi"
        if self.has_account:
            return "Test akkaunt berilgan"
        return "Sayt egasi test akkaunt berishi kerak"


def role_options(project: Project, bp: Blueprint) -> list[RoleOption]:
    given = accounts_for(project)
    version = project.current_blueprint()
    admin_roles = (version.stats or {}).get("admin_roles", {}) if version else {}
    options: list[RoleOption] = []
    for role in bp.roles:
        if role.kind == "guest":
            continue
        pages = sum(1 for p in bp.pages if p.kind == "page" and role.id in p.roles)
        flows = sum(1 for f in bp.flows if f.role == role.id)
        options.append(
            RoleOption(
                id=role.id,
                label=role.label,
                kind=role.kind,
                reason=role.reason,
                description=role.description or "",
                pages=pages,
                flows=flows,
                self_signup=role.self_signup,
                has_account="A" in given.get(role.id, {}),
                admin_made=project.uses_admin and bool(admin_roles.get(role.id)),
            )
        )
    return sorted(options, key=lambda o: (not o.selectable, not o.self_signup, o.label))


ADMIN_HINT = (
    "Nima qilish mumkin: (1) admin login va parolni tekshiring; (2) «Admin panel manzili» "
    "maydoniga foydalanuvchilar ro'yxati manzilini yozing (masalan, /admin/users); (3) sayt "
    "kirish uchun boshqa domenga o'tsa, «Kirish (SSO) domeni» maydonini to'ldiring; (4) bu "
    "hisob foydalanuvchi yarata oladigan panelga kira olmasligi mumkin (masalan, faqat kirish "
    "serverining profil sahifasi bor): shunda saytning haqiqiy admin panelini ko'rsating."
)


def check_error_message(exc: Exception) -> str:
    """What the user reads under «Tekshirish»: the reason in words, not a class name."""
    from playwright.async_api import TimeoutError as PlaywrightTimeout

    from yoriqnoma_core.provision.base import ProvisionError

    text = " ".join(str(exc).split())
    if isinstance(exc, ProvisionError):
        return f"{text}\n{ADMIN_HINT}"[:2000]
    if isinstance(exc, PlaywrightTimeout):
        return (
            "Sayt belgilangan vaqtda javob bermadi. Manzil to'g'riligini va saytga shu "
            "kompyuterdan kirish mumkinligini tekshiring. " + text.split("Call log")[0].strip()
        )[:2000]
    return f"{type(exc).__name__}: {text}"[:2000]


def check_project(project: Project) -> BlueprintVersion | None:
    """«Tekshirish»: scan the code (modes 1, 2) and sign in to the admin (modes 2, 3).

    Mode 3 gets a first blueprint with the admin's roles only; the role is chosen next.
    Runs in a Huey worker (a browser is opened for the admin), never in a view.
    """
    from projects.admin_access import check_admin, roles_blueprint, store_admin_roles

    Project.objects.filter(pk=project.pk).update(check_state="running", check_error="")
    try:
        version = scan_project(project) if project.has_code else None
        if project.uses_admin:
            roles = check_admin(project, project_dir(project))
            if version is not None:
                store_admin_roles(version, roles, raw_blueprint(version))
            else:
                version = _new_version(
                    project,
                    roles_blueprint(project, roles),
                    "admin",
                    stats={"admin_roles": {r.id: r.id for r in roles if r.kind == "role"}},
                )
    except Exception as exc:  # noqa: BLE001 - shown on the project page, never silent
        Project.objects.filter(pk=project.pk).update(
            check_state="failed", check_error=check_error_message(exc)
        )
        raise
    Project.objects.filter(pk=project.pk).update(check_state="done", check_error="")
    return version
