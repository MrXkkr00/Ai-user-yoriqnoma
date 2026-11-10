"""An LLM agent for admin panels no adapter knows (local: Ollama).

Used only when the Django adapter and the plain-form adapter do not fit. It works in the
same guarded admin session (``ProvisionGuard``), so whatever it decides, it can only
create users and change or delete what the tool created; settings, roles, permissions
and other people's records stay closed. Values typed into forms are always the tool's
own test identity, never text from the model. Screenshots of the admin pages go only to
the local model and live in a temporary folder that is removed at once.

Tasks: "create a user with role X" (done when the guard sees a new user id) and "delete
the user with email Y" (done when a delete of that id went through).
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Literal

from PIL import Image
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page
from pydantic import BaseModel, ConfigDict

from yoriqnoma_core.explorer import js
from yoriqnoma_core.explorer.capture import Capturer
from yoriqnoma_core.explorer.datagen import Identity
from yoriqnoma_core.explorer.som import draw_som
from yoriqnoma_core.explorer.steps import locate
from yoriqnoma_core.provision.base import (
    AdminCredentials,
    CreatedUser,
    ProvisionError,
    RoleCandidate,
    classify_role,
)
from yoriqnoma_core.provision.guard import ProvisionGuard
from yoriqnoma_core.writer.providers.base import LLMProvider, LLMRequest
from yoriqnoma_schemas import Element

SYSTEM = (
    "Siz veb-saytning admin panelida ishlaydigan ehtiyotkor yordamchisiz. Faqat berilgan "
    "vazifani bajaring: test foydalanuvchi yaratish yoki vosita yaratgan test "
    "foydalanuvchini o'chirish. Sozlamalar, rollar, huquqlar va boshqa odamlarning "
    "yozuvlariga tegmang. Formaga qiymat yozmang: faqat value_kind tanlang (username, "
    "email, password, full_name, first_name, last_name, phone). Har javobda bitta amal."
)
Kind = Literal["username", "email", "password", "full_name", "first_name", "last_name", "phone"]


class AdminAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool: Literal["goto", "click", "fill", "select", "done", "fail"]
    path: str | None = None
    marker: int | None = None
    value_kind: Kind | None = None
    option: str | None = None
    roles: list[str] | None = None  # for the "list roles" task: role names seen
    reason: str | None = None


class AgentAdminAdapter:
    name = "agent-admin"

    def __init__(
        self,
        base_url: str,
        admin_path: str,
        guard: ProvisionGuard,
        provider: LLMProvider,
        max_steps: int = 25,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.admin_path = admin_path or "/admin"
        self.guard = guard
        self.provider = provider
        self.max_steps = max_steps
        self._tmp = Path(tempfile.mkdtemp(prefix="yq-admin-"))

    def close(self) -> None:
        for item in self._tmp.glob("*"):
            item.unlink(missing_ok=True)
        self._tmp.rmdir()

    async def detect(self, page: Page) -> bool:
        return True

    async def _look(self, page: Page) -> tuple[list[Element], Path]:
        raw = await page.evaluate(js.COLLECT_ELEMENTS, 2400)
        elements = Capturer._elements(raw, [])
        shot = self._tmp / "admin.png"
        await page.screenshot(path=str(shot))
        image = draw_som(Image.open(shot), elements, 1.0)
        image.save(shot)
        return elements, shot

    async def _act(
        self, page: Page, task: str, identity: Identity | None, role: str = ""
    ) -> AdminAction:
        values = {}
        if identity is not None:
            values = {
                "username": identity.username or identity.email,
                "email": identity.email,
                "password": identity.password,
                "full_name": identity.full_name,
                "first_name": identity.first_name,
                "last_name": identity.last_name,
                "phone": identity.phone,
            }
        for _ in range(self.max_steps):
            elements, shot = await self._look(page)
            listing = [
                {"marker": e.marker, "role": e.role, "name": e.name[:60], "kind": e.kind}
                for e in elements
            ][:120]
            answer = await self.provider.generate(
                LLMRequest(
                    task="admin_step",
                    system=SYSTEM,
                    prompt=(
                        f"Vazifa: {task}\nSahifa: {page.url}\n"
                        f"Elementlar: {json.dumps(listing, ensure_ascii=False)}"
                    ),
                    images=[shot],
                    max_tokens=300,
                ),
                AdminAction,
            )
            act = answer.data
            if act.tool in {"done", "fail"}:
                return act
            try:
                if act.tool == "goto" and act.path:
                    await page.goto(self.base_url + "/" + act.path.lstrip("/"))
                    continue
                element = next((e for e in elements if e.marker == act.marker), None)
                if element is None:
                    continue
                locator = await locate(page, element.selector, 5000)
                if act.tool == "click":
                    await locator.click()
                elif act.tool == "fill" and act.value_kind in values:
                    await locator.fill(values[act.value_kind])
                elif act.tool == "select":
                    await locator.select_option(label=act.option or role)
                await page.wait_for_load_state("networkidle")
            except PlaywrightError:
                continue
        return AdminAction(tool="fail", reason="qadamlar limiti tugadi")

    async def login(self, page: Page, creds: AdminCredentials) -> None:
        await page.goto(self.base_url + "/" + self.admin_path.lstrip("/"))
        password = page.locator("input[type=password]")
        if await password.count():
            login = page.locator("input[type=email], input[name*=user], input[name*=login]")
            await login.first.fill(creds.login)
            await password.first.fill(creds.password.get_secret_value())
            await password.first.press("Enter")
            await page.wait_for_load_state("networkidle")
        self.guard.signed_in = True

    async def roles(self, page: Page) -> list[RoleCandidate]:
        act = await self._act(
            page,
            "Foydalanuvchi yaratish formasini toping va undagi rol tanlovlarini roles "
            "ro'yxatida done bilan qaytaring. Hech narsani saqlamang.",
            None,
        )
        names = act.roles or []
        if act.tool != "done" or not names:
            raise ProvisionError(f"admin panelida rollar topilmadi: {act.reason or '-'}")
        return [classify_role(n, n, "admin agent", "role") for n in names]

    async def create_user(
        self, page: Page, role: RoleCandidate, identity: Identity, alias: str
    ) -> CreatedUser:
        before = len(self.guard.created)
        act = await self._act(
            page,
            f"«{role.label}» rolida yangi foydalanuvchi yarating va saqlang. Tugagach done.",
            identity,
            role.label,
        )
        if len(self.guard.created) == before:
            raise ProvisionError(f"agent foydalanuvchi yarata olmadi: {act.reason or '-'}")
        model, remote_id = self.guard.created[-1]
        return CreatedUser(
            role=role.id,
            alias=alias,
            login=identity.email,
            email=identity.email,
            remote_id=remote_id,
            model=model,
        )

    async def delete_object(self, page: Page, entity: str, object_id: str) -> bool:
        return False

    async def delete_user(self, page: Page, user: CreatedUser) -> None:
        blocked = len(self.guard.log)
        act = await self._act(
            page,
            f"{user.email} emailli test foydalanuvchini o'chiring (tasdiqlash bilan). "
            "Boshqa hech kimni o'chirmang. Tugagach done.",
            None,
        )
        if act.tool != "done":
            raise ProvisionError(f"{user.email}: agent o'chira olmadi ({act.reason or '-'})")
        if len(self.guard.log) > blocked:
            raise ProvisionError(f"{user.email}: agent taqiqlangan amalga urindi")
