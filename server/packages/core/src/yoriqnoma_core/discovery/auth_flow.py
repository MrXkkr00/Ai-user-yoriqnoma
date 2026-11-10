"""Sign-up and sign-in of mode B (ARCHITECTURE §7.6, TZ SEC-6, SEC-8).

Login and sign-up forms are found on the crawled pages (password fields, button words;
Claude Haiku is asked only when the heuristics cannot tell). From them the ``<role>.login``
and ``<role>.register`` flows are written in the blueprint's own step language, so the
explorer later runs them exactly like flows from code.

The scout itself signs in once to see the role's pages: with the account the site owner
gave, or — for a role anyone can sign up for — with a new test account on the job's test
mailbox (``job-<id>@inbox.<server domain>``). A captcha is never solved: the person is
asked, or the job stops with "give a ready account".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict

from yoriqnoma_core.discovery.crawler import CrawlResult, PageSeen
from yoriqnoma_core.discovery.forms import classify, fill_steps, to_form
from yoriqnoma_core.writer.providers.base import LLMProvider, LLMRequest, ProviderError
from yoriqnoma_schemas import Flow, Form, Step, Target

CAPTCHA_HINTS = ("captcha", "recaptcha", "hcaptcha", "turnstile", "g-recaptcha")


@dataclass
class AuthForms:
    login: tuple[str, Form] | None = None  # (page path, form)
    register: tuple[str, Form] | None = None
    register_raw: dict[str, Any] = field(default_factory=dict)
    # how the site confirms an email: filled in when the scout signs up (code form or link)
    verify_steps: list[Step] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


class FormKind(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str  # login | register | search | other


def _form_hint(raw: dict[str, Any]) -> str:
    fields = ", ".join(f"{f.get('type')}:{f.get('label') or f.get('name')}" for f in raw["fields"])
    return f"submit «{raw.get('submit', '')}»; fields: {fields}"


async def find_auth_forms(crawl: CrawlResult, provider: LLMProvider | None = None) -> AuthForms:
    found = AuthForms()
    pages: list[PageSeen] = sorted(crawl.pages.values(), key=lambda p: p.template)
    for page in pages:
        for raw in page.forms:
            kind = classify(raw, page.template)
            if (
                kind == "other"
                and provider is not None
                and any(f.get("type") == "password" for f in raw.get("fields", []))
            ):
                kind = await _ask(provider, raw, page.template)
            form_id = f"{page.template.strip('/').replace('/', '_') or 'home'}_{raw['index']}"
            if kind == "login" and found.login is None:
                found.login = (page.template, to_form(raw, page.template, form_id))
            elif kind == "register" and found.register is None:
                found.register = (page.template, to_form(raw, page.template, form_id))
                found.register_raw = raw
    if found.login is None:
        found.notes.append("kirish formasi topilmadi")
    if found.register is None:
        found.notes.append("ro'yxatdan o'tish formasi topilmadi")
    return found


async def _ask(provider: LLMProvider, raw: dict[str, Any], path: str) -> str:
    """Claude Haiku tells the form's purpose when the words are not enough."""
    try:
        answer = await provider.generate(
            LLMRequest(
                task="classify",
                system="Veb-formaning vazifasini aniqlang: login, register, search yoki other.",
                prompt=f'Sahifa: {path}\nForma: {_form_hint(raw)}\nFaqat JSON: {{"kind": ...}}',
                max_tokens=50,
            ),
            FormKind,
        )
    except ProviderError:
        return "other"
    return answer.data.kind if answer.data.kind in {"login", "register", "search"} else "other"


def has_captcha(raw_html: str) -> bool:
    low = raw_html.lower()
    return any(h in low for h in CAPTCHA_HINTS)


def auth_flows(role: str, forms: AuthForms, *, verify_email: bool) -> list[Flow]:
    flows: list[Flow] = []
    if forms.register is not None:
        path, form = forms.register
        steps = [Step(action="goto", path=path), *fill_steps(form)]
        steps.append(Step(action="click", target=form.submit))
        if verify_email:
            steps.extend(forms.verify_steps or [Step(action="verify_email")])
        flows.append(
            Flow(
                id=f"{role}.register",
                title="Ro'yxatdan o'tish",
                stage="start",
                role=role,
                action="register",
                source=f"discovered: {path}",
                confidence=0.7,
                steps=steps,
            )
        )
    if forms.login is not None:
        path, form = forms.login
        steps = [Step(action="goto", path=path), *fill_steps(form, login=True)]
        steps.append(Step(action="click", target=form.submit))
        steps.append(Step(action="expect_url", path=f"re:^(?!.*{path.rstrip('/')}/?$).*"))
        flows.append(
            Flow(
                id=f"{role}.login",
                title="Tizimga kirish",
                stage="start",
                role=role,
                action="login",
                requires=[f"{role}.register"] if forms.register is not None else [],
                source=f"discovered: {path}",
                confidence=0.7,
                steps=steps,
            )
        )
    return flows


CODE_FIELD = ("code", "kod", "код", "otp", "token")


def verify_steps_for(forms_after_signup: list[dict[str, Any]]) -> list[Step]:
    """The confirmation page after sign-up: a code field and a button, or just a link."""
    for raw in forms_after_signup:
        for f in raw.get("fields", []):
            words = f"{f.get('name', '')} {f.get('label', '')}".lower()
            if f.get("type") in {"text", "number", "tel"} and any(w in words for w in CODE_FIELD):
                target = (
                    Target(label=f["label"])
                    if f.get("label")
                    else Target(css=f'[name="{f.get("name")}"]')
                )
                steps = [Step(action="verify_email", target=target)]
                if raw.get("submit"):
                    steps.append(
                        Step(action="click", target=Target(role="button", name=raw["submit"]))
                    )
                return steps
    return [Step(action="verify_email")]


def logout_target(crawl: CrawlResult) -> Target | None:
    for page in crawl.pages.values():
        for link in page.links:
            text = str(link.get("text") or "").lower()
            if text in {"chiqish", "logout", "log out", "sign out", "выйти"}:
                return Target(role="link", name=str(link["text"]))
    return None
