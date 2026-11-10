"""Test users through the admin panel, and cleaning up after the job (local modes 2, 3).

    start()            separate browser, guarded admin context, adapter chosen, signed in
    list_roles()       roles offered by the admin's "new user" form (admin-like excluded)
    create_accounts()  A and B test users of the chosen role -> explorer accounts
    cleanup()          the test users' own objects, then the test users, removed

Adapters are tried in order: Django admin, a plain form panel, the LLM agent (only if a
provider is given). Every created user goes to the ledger (``provision.json``) at once,
so ``cleanup()`` can be repeated later, even after a crash.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright
from pydantic import SecretStr

from yoriqnoma_core.explorer.datagen import DataGen
from yoriqnoma_core.explorer.options import AccountCredentials, ExploreOptions
from yoriqnoma_core.provision.agent_admin import AgentAdminAdapter
from yoriqnoma_core.provision.base import (
    AdminAdapter,
    AdminCredentials,
    CleanupReport,
    CreatedUser,
    Ledger,
    ProvisionError,
    RoleCandidate,
    role_id,
)
from yoriqnoma_core.provision.django_admin import DjangoAdminAdapter
from yoriqnoma_core.provision.form_admin import FormAdminAdapter
from yoriqnoma_core.provision.guard import ProvisionGuard
from yoriqnoma_core.safety.url_guard import HostGuard, check_url
from yoriqnoma_core.text_uz import normalize_uz
from yoriqnoma_core.writer.providers.base import LLMProvider

Log = Callable[[str, str], None]


# Where admin panels usually are; "/" last: sign in on the site and follow its links.
ADMIN_PATHS = (
    "/admin/",
    "/dashboard",
    "/panel",
    "/administrator",
    "/backend",
    "/manage",
    "/cabinet",
    "/",
)


def admin_paths(creds: AdminCredentials) -> list[str]:
    """The panel the owner named, or (empty field) the usual places and the site itself."""
    raw = creds.admin_url.strip()
    if raw:
        return [urlsplit(raw).path or "/"]
    return list(ADMIN_PATHS)


class Provisioner:
    def __init__(
        self,
        opts: ExploreOptions,
        creds: AdminCredentials,
        ledger_path: Path,
        agent: LLMProvider | None = None,
        log: Log | None = None,
    ) -> None:
        check_url(opts.base_url, allow_private=opts.allow_private)
        self.opts = opts
        self.creds = creds
        self.ledger = Ledger(ledger_path)
        self.agent = agent
        self._log = log
        self.guard = ProvisionGuard(
            opts.base_url,
            HostGuard(allow_private=opts.allow_private),
            on_block=lambda entry: self.log("warning", f"admin sessiyasi bloklandi: {entry}"),
        )
        for user in self.ledger.pending():
            self.guard.allow(user.model, user.remote_id)
        self.datagen = DataGen(
            opts.seed, f"{opts.run_id}-admin", opts.pseudonym_key.get_secret_value()
        )
        self.adapter: AdminAdapter | None = None
        self._pw: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self.page: Page | None = None
        self._roles: list[RoleCandidate] = []

    def log(self, level: str, message: str) -> None:
        if self._log is not None:
            self._log(level, message)

    async def start(self) -> None:
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(headless=self.opts.headless)
        self._context = await self._browser.new_context(
            locale=self.opts.locale, timezone_id=self.opts.timezone, base_url=self.opts.base_url
        )
        self._context.set_default_timeout(self.opts.step_timeout_ms * 2)
        await self._context.route("**/*", self.guard.handle)
        self.page = await self._context.new_page()
        self.page.on("response", self.guard.on_response)
        paths = admin_paths(self.creds)
        # Django admin: the named path, or its default /admin/; then plain panels on every
        # candidate path (the last one, "/", follows the site's own links after signing in)
        django_path = paths[0] if self.creds.admin_url.strip() else "/admin/"
        candidates: list[Any] = [DjangoAdminAdapter(self.opts.base_url, django_path)]
        candidates += [FormAdminAdapter(self.opts.base_url, p, self.guard) for p in paths]
        if self.agent is not None:
            candidates.append(
                AgentAdminAdapter(self.opts.base_url, paths[0], self.guard, self.agent)
            )
        reasons = []
        seen: set[tuple[str, str]] = set()
        for adapter in candidates:
            key = (adapter.name, getattr(adapter, "admin_path", getattr(adapter, "admin", "")))
            if key in seen:
                continue
            seen.add(key)
            if not await adapter.detect(self.page):
                continue
            try:
                await adapter.login(self.page, self.creds)
            except ProvisionError as exc:
                reasons.append(f"{adapter.name}: {exc}")
                continue
            self.guard.signed_in = True
            self.adapter = adapter
            self.log("info", f"admin paneli: {adapter.name}")
            return
        raise ProvisionError(
            "Admin paneli bilan ishlab bo'lmadi: " + ("; ".join(reasons) or "panel topilmadi")
        )

    async def close(self) -> None:
        if isinstance(self.adapter, AgentAdminAdapter):
            self.adapter.close()
        if self._context is not None:
            await self._context.close()
        if self._browser is not None:
            await self._browser.close()
        if self._pw is not None:
            await self._pw.stop()

    def _ready(self) -> tuple[AdminAdapter, Page]:
        if self.adapter is None or self.page is None:
            raise ProvisionError("admin sessiyasi boshlanmagan")
        return self.adapter, self.page

    async def list_roles(self) -> list[RoleCandidate]:
        adapter, page = self._ready()
        if not self._roles:
            seen: dict[str, RoleCandidate] = {}
            for role in await adapter.roles(page):
                seen.setdefault(role.id, role)
            self._roles = list(seen.values())
        return self._roles

    async def find_role(self, wanted: str, label: str = "") -> RoleCandidate:
        """The admin's role for a role id of the blueprint (by id, value or label)."""
        keys = {role_id(wanted), role_id(label)} - {""}
        for role in await self.list_roles():
            names = {role.id, role_id(role.value), role_id(role.label)}
            if names & keys or normalize_uz(role.label) == normalize_uz(label):
                if role.kind != "role":
                    raise ProvisionError(f"«{role.label}» adminga o'xshash rol: tanlab bo'lmaydi")
                return role
        raise ProvisionError(f"admin panelida «{label or wanted}» roli topilmadi")

    async def create_accounts(
        self, role: RoleCandidate, aliases: tuple[str, ...] = ("A", "B")
    ) -> dict[str, AccountCredentials]:
        adapter, page = self._ready()
        if role.kind != "role":
            raise ProvisionError(f"«{role.label}» rol uchun test foydalanuvchi yaratilmaydi")
        out: dict[str, AccountCredentials] = {}
        for alias in aliases:
            identity = self.datagen.identity(role.id, alias, self.opts.mail_domain)
            user = await adapter.create_user(page, role, identity, alias)
            self.guard.allow(user.model, user.remote_id)
            self.ledger.add(user)
            if user.error:
                self.log("warning", f"{user.login}: {user.error}")
            self.log("info", f"test foydalanuvchi yaratildi: {user.login} («{role.label}»)")
            out[alias] = AccountCredentials(login=user.login, password=SecretStr(identity.password))
        return out

    async def cleanup(self, own_objects: dict[str, list[str]] | None = None) -> CleanupReport:
        """Remove the test users' own objects, then the test users themselves."""
        adapter, page = self._ready()
        report = CleanupReport()
        for entity, ids in (own_objects or {}).items():
            for object_id in ids:
                self.guard.allow(entity, object_id)
                try:
                    removed = await adapter.delete_object(page, entity, object_id)
                except Exception as exc:  # noqa: BLE001 - reported, never silent
                    report.left.append(f"{entity}#{object_id}: {str(exc)[:120]}")
                    continue
                if removed:
                    report.objects_removed += 1
        for user in self.ledger.pending():
            try:
                await adapter.delete_user(page, user)
            except Exception as exc:  # noqa: BLE001 - reported, never silent
                user.error = str(exc)[:200]
                report.left.append(f"{user.login}: {user.error}")
                self.ledger.save()
                continue
            user.cleaned = True
            user.error = ""
            report.users_removed += 1
            self.ledger.save()
        self.log(
            "info" if report.clean else "warning",
            f"tozalash: {report.users_removed} ta foydalanuvchi, "
            f"{report.objects_removed} ta obyekt o'chirildi"
            + (f"; qoldi: {'; '.join(report.left[:5])}" if report.left else ""),
        )
        return report

    @property
    def users(self) -> list[CreatedUser]:
        return list(self.ledger.users)
