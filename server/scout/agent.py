"""Claude agent of mode B (ARCHITECTURE §7.6): finds the role's tasks by using the site.

Tool use through the ``LLMProvider`` interface (CLAUDE.md rule 7): every turn the model
gets the page's Set-of-Mark screenshot, its element list and the flows found so far, and
answers with exactly one tool call as structured output:

    goto(path) · click(marker) · fill(marker, value_kind) · select(marker, option) ·
    back() · finish_flow(title, stage, entity, action) · give_up(reason)

Every call passes the ``PolicyEngine`` first (deny_paths, forbidden words such as delete,
pay, logout); values typed into forms are always the tool's own fake data, never text
from the model. The screenshot and element names went through the replacement of other
people's data before the model sees them (TZ SEC-7). Limits: pages, steps and dollars.
What the agent really did becomes a ``Flow`` with ``source="agent"``.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Literal

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page
from pydantic import BaseModel, ConfigDict

from scout.kit import ScoutKit
from scout.urls import clean_url, path_of
from security.ratelimit import wait_turn
from yoriqnoma_core.explorer.options import CancelToken, ProgressSink
from yoriqnoma_core.explorer.steps import locate
from yoriqnoma_core.safety.policy_engine import ClickContext
from yoriqnoma_core.writer.providers.base import LLMProvider, LLMRequest, ProviderError
from yoriqnoma_schemas import Element, Flow, Stage, State, Step, Target

ValueKind = Literal[
    "email",
    "password",
    "full_name",
    "first_name",
    "last_name",
    "phone_uz",
    "text",
    "number",
    "date",
    "address",
    "option",
]

SYSTEM = (
    "Siz veb-saytni o'rganuvchi agentsiz. Maqsad: berilgan rol foydalanuvchisi saytda "
    "bajara oladigan vazifalarni (masalan, buyurtma yaratish, profilni tahrirlash) topib, "
    "har birini haqiqatda bajarib ko'rish. Har javobda faqat bitta amal tanlang. "
    "Admin, foydalanuvchilar yoki rollarni boshqarish bo'limlariga kirmang. O'chirish, "
    "to'lash, chiqish (logout) tugmalarini bosmang. Formaga qiymat yozmang: faqat "
    "value_kind (email, password, full_name, phone_uz, text, number, date, address, option) "
    "tanlang, qiymatni vosita o'zi qo'yadi. Vazifa tugagach finish_flow bilan nomlang; "
    "sahifada yangi vazifa qolmasa give_up."
)


class AgentAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool: Literal["goto", "click", "fill", "select", "back", "finish_flow", "give_up"]
    path: str | None = None
    marker: int | None = None
    value_kind: ValueKind | None = None
    option: str | None = None
    title: str | None = None
    stage: Stage | None = None
    entity: str | None = None
    action: str | None = None
    reason: str | None = None


@dataclass
class AgentLimits:
    pages: int = 6
    steps: int = 40
    steps_per_flow: int = 12


@dataclass
class AgentResult:
    flows: list[Flow] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    steps_used: int = 0


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return slug[:40] or "task"


def _prompt(role_label: str, state: State, known: list[str], current: list[Step]) -> str:
    elements = [
        {"marker": e.marker, "role": e.role, "name": e.name[:80], "kind": e.kind}
        for e in state.elements
        if e.enabled
    ][:120]
    return (
        f"Rol: {role_label}\nSahifa: {path_of(state.url)} — {state.title}\n"
        f"Allaqachon topilgan vazifalar: {', '.join(known) or 'yo`q'}\n"
        f"Hozirgi vazifadagi qadamlar soni: {len(current)}\n"
        f"Elementlar (marker, role, name):\n{json.dumps(elements, ensure_ascii=False)}"
    )


class Agent:
    def __init__(
        self,
        kit: ScoutKit,
        provider: LLMProvider,
        role: str,
        role_label: str,
        progress: ProgressSink,
        cancel: CancelToken,
        limits: AgentLimits | None = None,
    ) -> None:
        self.kit = kit
        self.provider = provider
        self.role = role
        self.role_label = role_label
        self.progress = progress
        self.cancel = cancel
        self.limits = limits or AgentLimits()
        self.result = AgentResult()
        self.production = kit.opts.environment == "production"

    def _known(self, existing: list[Flow]) -> list[str]:
        return [f.title for f in existing + self.result.flows][:40]

    async def explore(self, page: Page, paths: list[str], existing: list[Flow]) -> AgentResult:
        for path in paths[: self.limits.pages]:
            if self.result.steps_used >= self.limits.steps or self.cancel.is_cancelled():
                break
            try:
                await self._page(page, path, existing)
            except ProviderError as exc:
                self.result.notes.append(f"agent to'xtadi: {exc}")
                break
        return self.result

    async def _snap(self, page: Page) -> State:
        return await self.kit.capturer.snapshot(page, account="A", network=[])

    async def _page(self, page: Page, path: str, existing: list[Flow]) -> None:
        url = clean_url(path, self.kit.opts.base_url)
        if url is None or not self.kit.engine.allows_path(path):
            return
        await wait_turn(self._host())
        await page.goto(url)
        steps: list[Step] = [Step(action="goto", path=path)]
        while self.result.steps_used < self.limits.steps and not self.cancel.is_cancelled():
            state = await self._snap(page)
            som = self.kit.capturer.run_dir / "capture" / state.images["som"]
            answer = await self.provider.generate(
                LLMRequest(
                    task="agent_step",
                    system=SYSTEM,
                    prompt=_prompt(self.role_label, state, self._known(existing), steps),
                    images=[som],
                    max_tokens=400,
                ),
                AgentAction,
            )
            self.result.steps_used += 1
            act = answer.data
            if act.tool == "give_up":
                if act.reason:
                    self.result.notes.append(f"{path}: {act.reason[:200]}")
                return
            if act.tool == "finish_flow":
                self._finish(act, steps)
                steps = [Step(action="goto", path=path_of(page.url))]
                continue
            if len(steps) >= self.limits.steps_per_flow:
                self.result.notes.append(f"{path}: vazifa juda uzun, to'xtatildi")
                return
            step = await self._do(page, act, state)
            if step is not None:
                steps.append(step)

    def _host(self) -> str:
        from urllib.parse import urlsplit

        return (urlsplit(self.kit.opts.base_url).hostname or "").lower()

    def _element(self, state: State, marker: int | None) -> Element | None:
        return next((e for e in state.elements if e.marker == marker), None)

    async def _do(self, page: Page, act: AgentAction, state: State) -> Step | None:
        """Run one tool call if the policy allows it; return the step it adds."""
        timeout = self.kit.opts.step_timeout_ms
        try:
            if act.tool == "goto":
                url = clean_url(act.path or "", page.url)
                if url is None or not self.kit.engine.allows_path(path_of(url)):
                    self.result.notes.append(f"agent: taqiqlangan yo'l {act.path}")
                    return None
                await wait_turn(self._host())
                await page.goto(url)
                return Step(action="goto", path=path_of(url))
            if act.tool == "back":
                await page.go_back()
                return None
            element = self._element(state, act.marker)
            if element is None:
                self.result.notes.append(f"agent: {act.marker}-marker yo'q")
                return None
            target = _target(element)
            if act.tool == "click":
                allowed, why = self.kit.engine.allows_click(element.name, ClickContext())
                if not allowed or (self.production and element.kind not in {"link", "tab", "menu"}):
                    self.result.notes.append(f"agent: «{element.name}» bosilmadi ({why})")
                    return None
                await (await locate(page, target, timeout)).click()
                return Step(action="click", target=target)
            if self.production or self.kit.opts.passive:
                self.result.notes.append("agent: production/passiv rejimda forma to'ldirilmaydi")
                return None
            if act.tool == "fill":
                kind = act.value_kind or "text"
                value = self.kit.datagen.value(kind, None, element.name)
                await (await locate(page, target, timeout)).fill(value)
                return Step(action="fill", target=target, data=f"fake:{kind}")
            if act.tool == "select":
                locator = await locate(page, target, timeout)
                options = await locator.evaluate(
                    "el => Array.from(el.options || []).map(o => o.text.trim())"
                )
                choice = (
                    act.option if act.option in options else (options[1:] or options or [""])[0]
                )
                await locator.select_option(label=choice)
                return Step(action="select", target=target, data="fake:option")
        except PlaywrightError as exc:
            self.result.notes.append(
                f"agent: {act.tool} bajarilmadi: {str(exc).splitlines()[0][:120]}"
            )
        return None

    def _finish(self, act: AgentAction, steps: list[Step]) -> None:
        if len(steps) < 2 or not act.title:
            return
        title = act.title.strip()[:120]
        flow_id = f"{self.role}.agent.{_slug(act.action or title)}"
        taken = {f.id for f in self.result.flows}
        n = 2
        base = flow_id
        while flow_id in taken:
            flow_id = f"{base}_{n}"
            n += 1
        self.result.flows.append(
            Flow(
                id=flow_id,
                title=title,
                stage=act.stage or "core",
                role=self.role,
                entity=(act.entity or None),
                action=(act.action or None),
                source="agent",
                confidence=0.6,
                steps=list(steps),
            )
        )
        self.progress.log("info", f"agent vazifa topdi: {title}")


def _target(element: Element) -> Target:
    sel = element.selector
    if sel.role and sel.name:
        return Target(role=sel.role, name=sel.name)
    if sel.label:
        return Target(label=sel.label)
    if element.name:
        return Target(role=element.role, name=element.name)
    if sel.testid:
        return Target(testid=sel.testid)
    return Target(css=sel.css or element.css or "body")
