"""Admin login of a project (modes 2 and 3): check it, make test users, clean up after.

The admin password is decrypted only in memory, only here. The admin session never
captures anything: the core ``Provisioner`` works in its own browser with its own
firewall (create users; change or delete only what it created).

* ``check_admin`` — sign in, read the roles of the "new user" form (admin-like ones
  are excluded). Mode 3 gets a first blueprint from them (roles only); mode 2 records
  which code role is which admin role.
* ``provision`` / ``cleanup`` — used by ``runs.services.execute_run``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import SecretBytes, SecretStr

from projects.models import BlueprintVersion, Project
from settings_app.models import AppSettings
from yoriqnoma_core.explorer.options import AccountCredentials, ExploreOptions
from yoriqnoma_core.provision.base import (
    AdminCredentials,
    CleanupReport,
    ProvisionError,
    RoleCandidate,
)
from yoriqnoma_core.provision.provisioner import Provisioner
from yoriqnoma_core.safety.sso import parse_hosts
from yoriqnoma_core.writer.providers import OllamaProvider
from yoriqnoma_local.keys import decrypt, pseudonym_key
from yoriqnoma_schemas import Blueprint, Policy, RoleInfo

Log = Callable[[str, str], None]


def credentials(project: Project) -> AdminCredentials:
    if not project.uses_admin or not project.admin_login or not project.admin_password_enc:
        raise ProvisionError("Loyihada admin login va paroli berilmagan")
    return AdminCredentials(
        login=project.admin_login,
        password=SecretStr(decrypt(project.admin_password_enc)),
        admin_url=project.admin_path,
    )


def admin_options(project: Project, run_id: str) -> ExploreOptions:
    return ExploreOptions(
        base_url=project.base_url,
        role="guest",
        environment=project.environment,  # type: ignore[arg-type]
        allow_private=True,  # the local app may study a site on 127.0.0.1 (TZ SEC-10)
        pseudonym_key=SecretBytes(pseudonym_key()),
        run_id=run_id,
        mail_domain="yoriqnoma.test",
        trusted_hosts=list(parse_hosts(project.sso_hosts)),
    )


def agent_provider() -> OllamaProvider | None:
    """Ollama drives an admin panel no adapter knows (only then is it used)."""
    cfg = AppSettings.load()
    return OllamaProvider(host=cfg.ollama_host, model=cfg.ollama_model, num_ctx=cfg.num_ctx)


async def _roles(prov: Provisioner) -> list[RoleCandidate]:
    await prov.start()
    try:
        return await prov.list_roles()
    finally:
        await prov.close()


def roles_blueprint(project: Project, roles: list[RoleCandidate]) -> Blueprint:
    """Mode 3 before discovery: only the roles (pages and flows come from the site later)."""
    infos = [
        RoleInfo(
            id="guest",
            label="Mehmon",
            kind="guest",
            reason="kirmagan foydalanuvchi",
            source="discovered",
        )
    ]
    for role in roles:
        if role.id in {r.id for r in infos}:
            continue
        infos.append(
            RoleInfo(
                id=role.id,
                label=role.label,
                kind=role.kind,
                reason=role.reason,
                source=role.source,
                description="Test foydalanuvchi admin orqali yaratiladi; sahifalar va "
                "vazifalar ishga tushirilganda saytdan o'rganiladi",
            )
        )
    return Blueprint(
        project=project.name,
        base_url=project.base_url,  # type: ignore[arg-type]
        source="discovered",
        generated_at=datetime.now(UTC),
        generator="yoriqnoma-local admin",
        language=project.language,
        policy=Policy(target_role="guest"),
        roles=infos,
    )


def check_admin(project: Project, ledger_dir: Path) -> list[RoleCandidate]:
    """Sign in with the admin login and read the roles (in a worker, never in a view)."""
    # settings and the password are read here, outside the event loop (Django ORM)
    prov = Provisioner(
        admin_options(project, "check"),
        credentials(project),
        ledger_dir / "check-provision.json",
        agent_provider(),
    )
    return asyncio.run(_roles(prov))


def match_roles(code: Blueprint, admin: list[RoleCandidate]) -> dict[str, str]:
    """Code role id -> admin role id (mode 2); a code role missing in the admin -> ''."""
    from yoriqnoma_core.provision.base import role_id

    out: dict[str, str] = {}
    for info in code.roles:
        if info.kind != "role":
            continue
        keys = {info.id, role_id(info.id), role_id(info.label)}
        found = next(
            (
                a.id
                for a in admin
                if a.kind == "role" and {a.id, role_id(a.value), role_id(a.label)} & keys
            ),
            "",
        )
        out[info.id] = found
    return out


def store_admin_roles(
    version: BlueprintVersion, roles: list[RoleCandidate], code: Blueprint
) -> None:
    stats = dict(version.stats or {})
    stats["admin_roles"] = match_roles(code, roles)
    version.stats = stats
    version.save(update_fields=["stats"])


class ProvisionSession:
    """Test users for one run: created before exploring, removed after (even on failure)."""

    def __init__(self, project: Project, run_dir: Path, run_id: str, log: Log) -> None:
        self.project = project
        self.ledger = run_dir / "provision.json"
        self.run_id = run_id
        self.log = log
        # read before any event loop starts (Django ORM is synchronous)
        self.opts = admin_options(project, run_id)
        self.creds = credentials(project)
        self.agent = agent_provider()

    def _provisioner(self) -> Provisioner:
        return Provisioner(self.opts, self.creds, self.ledger, self.agent, log=self.log)

    async def create(
        self, roles: dict[str, tuple[str, str]]
    ) -> dict[str, dict[str, AccountCredentials]]:
        """roles: blueprint role id -> (label, aliases "AB" or "A")."""
        prov = self._provisioner()
        await prov.start()
        out: dict[str, dict[str, AccountCredentials]] = {}
        try:
            for role, (label, aliases) in roles.items():
                candidate = await prov.find_role(role, label)
                made = await prov.create_accounts(candidate, tuple(aliases))
                out[role] = made
        finally:
            await prov.close()
        return out

    async def cleanup(self, own_objects: dict[str, list[str]]) -> CleanupReport:
        prov = self._provisioner()
        await prov.start()
        try:
            return await prov.cleanup(own_objects)
        finally:
            await prov.close()


def report_dict(report: CleanupReport) -> dict[str, Any]:
    return {
        "users_removed": report.users_removed,
        "objects_removed": report.objects_removed,
        "left": report.left,
        "clean": report.clean,
    }
