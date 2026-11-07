"""Step executor (ARCHITECTURE §4.3): every StepAction, the locator strategy, data values.

Locator order: role + exact name, label, test id, css (first match wins). A failed step
raises ``StepFailed`` with a clear reason; the flow is then marked ``failed``.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Locator, Page

from yoriqnoma_core.explorer.datagen import DataGen, Identity
from yoriqnoma_core.explorer.mailbox import Mailbox, MailTimeout
from yoriqnoma_core.explorer.options import HumanInput
from yoriqnoma_schemas import Step, Target

OWN_RE = re.compile(r"\{own:([a-z_]+)_id\}")


class StepFailed(Exception):
    pass


class StoppedAtConfirm(Exception):
    """Production: stop before the confirmation click (TZ SEC-5)."""


@dataclass
class StepContext:
    identity: Identity | None
    peer: Identity | None
    current_objects: dict[str, str]  # entity -> object id for {own:<entity>_id}
    datagen: DataGen
    mailbox: Mailbox | None
    human: HumanInput
    environment: Literal["staging", "production"]
    base_url: str
    timeout_ms: int
    sample_file: str | None = None
    api_errors: list[str] = field(default_factory=list)


def resolve_path(path: str, objects: dict[str, str]) -> str:
    def repl(match: re.Match[str]) -> str:
        entity = match.group(1)
        if entity not in objects:
            raise StepFailed(f"«{entity}» obyekti hali yaratilmagan (own:{entity}_id)")
        return objects[entity]

    return OWN_RE.sub(repl, path)


async def locate(page: Page, target: Target, timeout_ms: int) -> Locator:
    """First matching strategy whose element becomes visible."""
    candidates: list[Locator] = []
    if target.role and target.name:
        candidates.append(page.get_by_role(target.role, name=target.name, exact=True))  # type: ignore[arg-type]
    if target.label:
        candidates.append(page.get_by_label(target.label, exact=True))
    if target.testid:
        candidates.append(page.get_by_test_id(target.testid))
    if target.css:
        candidates.append(page.locator(target.css))
    if target.name and not target.role:
        candidates.append(page.get_by_text(target.name, exact=True))
    if target.role and target.name:
        candidates.append(page.get_by_role(target.role, name=target.name))  # type: ignore[arg-type]
    if target.label:
        candidates.append(page.get_by_label(target.label))
    deadline = asyncio.get_running_loop().time() + timeout_ms / 1000
    while True:
        for loc in candidates:
            try:
                if await loc.count() > 0 and await loc.first.is_visible():
                    return loc.first
            except PlaywrightError:
                continue
        if asyncio.get_running_loop().time() > deadline:
            raise StepFailed(f"element topilmadi: {target.describe()}")
        await asyncio.sleep(0.2)


def value_for(data: str, ctx: StepContext, rules: str | None, label: str) -> str:
    kind, _, rest = data.partition(":")
    ident = ctx.identity
    if kind == "literal":
        return rest
    if kind == "peer":
        if ctx.peer is None:
            raise StepFailed("ikkinchi akkaunt (B) kerak, lekin u yo'q")
        return ctx.peer.email
    if kind == "fake":
        if ident is not None:
            mapping = {
                "email": ident.email,
                "password": ident.password,
                "full_name": ident.full_name,
                "phone_uz": ident.phone,
            }
            if rest in mapping and mapping[rest]:
                if rest == "phone_uz" and rules and "regex" in rules:
                    return _fit_phone(ident.phone, rules)
                return mapping[rest]
        if rest == "phone_uz":
            return _fit_phone(ctx.datagen.value("phone_uz", None, label), rules)
        return ctx.datagen.value(rest, rules, label)
    raise StepFailed(f"noma'lum ma'lumot turi: {data}")


def _fit_phone(phone: str, rules: str | None) -> str:
    """Use the format the form's pattern expects (+998XXXXXXXXX or with spaces)."""
    match = re.search(r"regex:([^|]+)", rules or "")
    if not match:
        return phone
    try:
        if re.fullmatch(match.group(1), phone):
            return phone
    except re.error:
        return phone
    digits = re.sub(r"\D", "", phone)[-9:]
    for candidate in (
        f"+998{digits}",
        f"998{digits}",
        digits,
        f"+998 {digits[:2]} {digits[2:5]} {digits[5:7]} {digits[7:]}",
    ):
        try:
            if re.fullmatch(match.group(1), candidate):
                return candidate
        except re.error:
            break
    return phone


class StepExecutor:
    def __init__(
        self, page: Page, ctx: StepContext, on_response_error: Callable[[], list[str]] | None = None
    ) -> None:
        self.page = page
        self.ctx = ctx
        self._errors = on_response_error

    async def run(self, step: Step) -> None:
        handler = getattr(self, f"_{step.action}", None)
        if handler is None:
            raise StepFailed(f"qo'llab-quvvatlanmaydigan amal: {step.action}")
        try:
            await handler(step)
        except PlaywrightError as exc:
            raise StepFailed(f"{step.action}: {str(exc).splitlines()[0][:200]}") from exc

    async def _wait(self) -> None:
        try:
            await self.page.wait_for_load_state("networkidle", timeout=5000)
        except PlaywrightError:
            pass

    async def _goto(self, step: Step) -> None:
        path = resolve_path(step.path or "/", self.ctx.current_objects)
        response = await self.page.goto(self.ctx.base_url.rstrip("/") + path)
        if response is not None and response.status >= 400:
            raise StepFailed(f"sahifa ochilmadi: {path} ({response.status})")
        await self._wait()

    async def _click(self, step: Step) -> None:
        assert step.target is not None
        if step.confirm and self.ctx.environment == "production":
            raise StoppedAtConfirm(step.target.describe())
        loc = await locate(self.page, step.target, self.ctx.timeout_ms)
        before = len(self._errors()) if self._errors else 0
        await loc.click()
        await self._wait()
        if self._errors:
            errors = self._errors()[before:]
            if errors:
                raise StepFailed("server xato qaytardi: " + "; ".join(errors[:3]))

    async def _fill(self, step: Step) -> None:
        assert step.target is not None and step.data is not None
        loc = await locate(self.page, step.target, self.ctx.timeout_ms)
        label = step.target.label or step.target.name or ""
        await loc.fill(value_for(step.data, self.ctx, step.rules, label))

    async def _select(self, step: Step) -> None:
        assert step.target is not None and step.data is not None
        loc = await locate(self.page, step.target, self.ctx.timeout_ms)
        if step.data in {"fake:option", "literal:"}:
            values: list[str] = await loc.evaluate(
                "el => [...el.options].map(o => o.value).filter(v => v !== '')"
            )
            if not values:
                raise StepFailed(f"tanlov bo'sh: {step.target.describe()}")
            await loc.select_option(values[0])
        else:
            value = value_for(step.data, self.ctx, step.rules, "")
            try:
                await loc.select_option(value)
            except PlaywrightError:
                await loc.select_option(label=value)
        await self._wait()

    async def _check(self, step: Step) -> None:
        assert step.target is not None
        loc = await locate(self.page, step.target, self.ctx.timeout_ms)
        if step.data == "literal:false":
            await loc.uncheck()
        else:
            await loc.check()

    async def _upload(self, step: Step) -> None:
        assert step.target is not None
        if not self.ctx.sample_file:
            raise StepFailed("yuklash uchun namuna fayl yo'q")
        loc = await locate(self.page, step.target, self.ctx.timeout_ms)
        await loc.set_input_files(self.ctx.sample_file)

    async def _expect_url(self, step: Step) -> None:
        pattern = step.path or ""
        deadline = asyncio.get_running_loop().time() + self.ctx.timeout_ms / 1000
        while True:
            url = self.page.url
            if pattern.startswith("re:"):
                if re.search(pattern[3:], url):
                    return
            else:
                try:
                    want = resolve_path(pattern, self.ctx.current_objects)
                except StepFailed:
                    want = OWN_RE.sub(r"[^/]+", pattern)
                    if re.search(want + r"(\?|#|$)", url):
                        return
                else:
                    if url.split("?")[0].rstrip("/").endswith(want.rstrip("/")):
                        return
            if asyncio.get_running_loop().time() > deadline:
                raise StepFailed(f"kutilgan sahifa ochilmadi: {pattern} (hozir: {url})")
            await asyncio.sleep(0.2)

    async def _expect_text(self, step: Step) -> None:
        text = step.text or ""
        try:
            await self.page.get_by_text(text).first.wait_for(timeout=self.ctx.timeout_ms)
        except PlaywrightError as exc:
            raise StepFailed(f"matn ko'rinmadi: «{text}»") from exc

    async def _expect_visible(self, step: Step) -> None:
        assert step.target is not None
        await locate(self.page, step.target, self.ctx.timeout_ms)

    async def _wait_for(self, step: Step) -> None:
        if step.target is not None:
            await locate(self.page, step.target, self.ctx.timeout_ms)
        else:
            await self._wait()

    async def _verify_email(self, step: Step) -> None:
        if self.ctx.mailbox is None or self.ctx.identity is None:
            raise StepFailed("pochta adapteri yoki akkaunt yo'q")
        try:
            message = await self.ctx.mailbox.wait_for(self.ctx.identity.email, timeout_s=60)
        except MailTimeout as exc:
            raise StepFailed(str(exc)) from exc
        if step.target is not None and message.code:
            loc = await locate(self.page, step.target, self.ctx.timeout_ms)
            await loc.fill(message.code)
            return
        if message.link:
            await self.page.goto(message.link)
            await self._wait()
            return
        raise StepFailed("xatda kod ham, havola ham topilmadi")

    async def _human_input(self, step: Step) -> None:
        answer = await self.ctx.human.ask("confirm", step.text or "Davom etish uchun tasdiqlang")
        if step.target is not None and answer:
            loc = await locate(self.page, step.target, self.ctx.timeout_ms)
            await loc.fill(answer)


def describe_step(step: Step) -> str:
    target = step.target.describe() if step.target else (step.path or "")
    return f"{step.action} {target}".strip()
