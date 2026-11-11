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
import re
import tempfile
from pathlib import Path
from typing import Literal
from urllib.parse import urljoin, urlsplit

from PIL import Image
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page
from pydantic import BaseModel, ConfigDict, Field

from yoriqnoma_core.explorer import js
from yoriqnoma_core.explorer.capture import Capturer
from yoriqnoma_core.explorer.datagen import Identity
from yoriqnoma_core.explorer.som import draw_som
from yoriqnoma_core.explorer.steps import StepFailed, locate
from yoriqnoma_core.provision.base import (
    AdminCredentials,
    CreatedUser,
    ProvisionError,
    RoleCandidate,
    classify_role,
    settle,
)
from yoriqnoma_core.provision.form_admin import LINKS_JS
from yoriqnoma_core.provision.guard import ProvisionGuard
from yoriqnoma_core.writer.providers.base import LLMProvider, LLMRequest
from yoriqnoma_schemas import Element

SYSTEM = (
    "Siz veb-saytning admin panelida ishlaydigan ehtiyotkor yordamchisiz. Faqat berilgan "
    "vazifani bajaring. Vazifalar uch xil: (1) foydalanuvchi yaratish formasidagi rol "
    "variantlarini O'QIB, roles ro'yxatida qaytarish (hech narsa saqlanmaydi); (2) test "
    "foydalanuvchi yaratish; (3) vosita yaratgan test foydalanuvchini o'chirish. Rol "
    "variantlarini o'qish ruxsat etilgan va kerak. Sozlamalarni, rollarni va huquqlarni "
    "O'ZGARTIRMANG, boshqa odamlarning yozuvlariga tegmang. Formaga qiymat yozmang: faqat "
    "value_kind tanlang (username, email, password, full_name, first_name, last_name, "
    "phone). Har javobda bitta amal. done faqat vazifa TO'LIQ bajarilgach yoziladi; "
    "bajarilmagan bo'lsa, menyudagi mos elementni click qiling yoki goto bilan o'ting."
)
# Menu items about people come first in the list the model sees (a big menu is cut).
PEOPLE_WORDS = re.compile(
    r"(foydalanuvchi|user|xodim|hodim|employee|staff|(?<![a-z])rol(?![a-z])|role|akkaunt|account|lavozim|"
    r"mijoz|polzovat|пользоват|сотрудник|роль|ro'yxat|registratsiya)",
    re.I,
)
MAX_LISTED = 200
MAX_LINKS = 80
Kind = Literal["username", "email", "password", "full_name", "first_name", "last_name", "phone"]


class AdminAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # first, so the model thinks before it picks the tool (a small model answers "done" at once)
    plan: str | None = Field(
        default=None, description="1 gap: sahifada nima bor va vazifa uchun keyingi qadam nima"
    )
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
        start_url: str = "",
    ) -> None:
        self.base_url = base_url
        self.admin_path = admin_path or "/admin"
        # where the agent starts: the panel the owner named, else the site's own start page
        self.start_url = start_url or urljoin(base_url, self.admin_path)
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
        # single-page apps draw their menu after the page "loads": wait until the number of
        # elements stops changing (at most ~10 s), or the model sees an empty page
        await settle(page)
        previous = -1
        for _ in range(20):
            raw = await page.evaluate(js.COLLECT_ELEMENTS, 2400)
            if len(raw) > 2 and len(raw) == previous:
                break
            previous = len(raw)
            await page.wait_for_timeout(500)
        elements = Capturer._elements(raw, [])
        shot = self._tmp / "admin.png"
        await page.screenshot(path=str(shot))
        image = draw_som(Image.open(shot), elements, 1.0)
        image.save(shot)
        return elements, shot

    async def _act(
        self,
        page: Page,
        task: str,
        identity: Identity | None,
        role: str = "",
        needs_roles: bool = False,
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
        history: list[str] = []
        for _ in range(self.max_steps):
            elements, shot = await self._look(page)
            ranked = sorted(elements, key=lambda e: 0 if PEOPLE_WORDS.search(e.name) else 1)
            listing = [
                {"marker": e.marker, "role": e.role, "name": e.name[:60], "kind": e.kind}
                for e in ranked
            ][:MAX_LISTED]
            # every link of the page (collapsed menus included), people-related ones first:
            # the model may only go to a path that really exists, never to a guessed one
            raw_links: list[list[str]] = await page.evaluate(LINKS_JS)
            links = {urlsplit(urljoin(page.url, h)).path: t for h, t in raw_links if h}
            known = sorted(links.items(), key=lambda kv: 0 if PEOPLE_WORDS.search(kv[1]) else 1)
            link_list = [{"path": k, "name": v[:50]} for k, v in known[:MAX_LINKS]]
            seen = f"\nOldingi qadamlar: {'; '.join(history[-6:])}" if history else ""
            answer = await self.provider.generate(
                LLMRequest(
                    task="admin_step",
                    system=SYSTEM,
                    prompt=(
                        f"Vazifa: {task}\nSahifa: {page.url}{seen}\n"
                        f"Elementlar: {json.dumps(listing, ensure_ascii=False)}\n"
                        f"Mavjud havolalar (goto faqat shulardan): "
                        f"{json.dumps(link_list, ensure_ascii=False)}"
                    ),
                    images=[shot],
                    max_tokens=300,
                ),
                AdminAction,
            )
            act = answer.data
            if act.tool == "fail" or (act.tool == "done" and (act.roles or not needs_roles)):
                return act
            history.append(
                f"{act.tool} {act.path or act.marker or ''}".strip()
                if act.tool != "done"
                else "done (roles bo'sh: avval rol variantlarini toping)"
            )
            if len(history) >= 4 and len(set(history[-4:])) == 1:
                return AdminAction(tool="fail", reason="agent bir xil amalni takrorlayapti")
            try:
                if act.tool == "goto" and act.path:
                    target = urlsplit(urljoin(self.base_url, act.path)).path
                    if target not in links:
                        history[-1] += " (bunday havola yo'q)"
                        continue
                    await page.goto(urljoin(self.base_url, act.path))
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
                await settle(page)
            except (PlaywrightError, StepFailed):
                continue
        return AdminAction(tool="fail", reason="qadamlar limiti tugadi")

    async def login(self, page: Page, creds: AdminCredentials) -> None:
        await page.goto(self.start_url)
        password = page.locator("input[type=password]")
        if await password.count():
            login = page.locator("input[type=email], input[name*=user], input[name*=login]")
            await login.first.fill(creds.login)
            await password.first.fill(creds.password.get_secret_value())
            await password.first.press("Enter")
            await settle(page)
            if await page.locator("input[type=password]:visible").count():
                raise ProvisionError(
                    "Admin login yoki paroli noto'g'ri (kirish sahifasi qayta ochildi)"
                )
        self.guard.signed_in = True

    async def roles(self, page: Page) -> list[RoleCandidate]:
        act = await self._act(
            page,
            "Yangi foydalanuvchi yaratish formasini toping: menyudan «Foydalanuvchilar» (Users) "
            "bo'limini oching, «Qo'shish» / «Yaratish» / «Add» / «Create» tugmasini bosing. "
            "Forma ochilgach, undagi rol (role, lavozim, guruh) tanlovining barcha variantlarini "
            "roles ro'yxatiga yozib, tool=done bilan qaytaring. Bu faqat o'qish: hech narsani "
            "saqlamang va yubormang.",
            None,
            needs_roles=True,
        )
        names = act.roles or []
        if act.tool != "done" or not names:
            raise ProvisionError(
                "admin panelida foydalanuvchi yaratish formasi va undagi rollar topilmadi"
                + (f" (agent: {act.reason})" if act.reason else "")
                + ". Bu panelda test foydalanuvchi yaratib bo'lmasa, «Admin panel manzili» "
                "maydoniga foydalanuvchi qo'shiladigan sahifa manzilini yozing"
            )
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
