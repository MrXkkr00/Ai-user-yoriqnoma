"""Learning a site without its code, end to end (server mode B, local mode 3).

    guest crawl (+ sitemap, + routes from the site's JavaScript)
    -> sign-up/sign-in forms -> sign in as the target role (not in passive mode)
    -> privilege check (SEC-6) -> crawl as the role -> validation probe
    -> LLM agent (optional) -> discovered blueprint

The app gives everything outside core: the browser kit, robots.txt rules, the rate limit,
how to fetch the site's JS files, the LLM providers and the accounts.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from yoriqnoma_core.discovery.agent import Agent, AgentLimits
from yoriqnoma_core.discovery.auth_flow import (
    AuthForms,
    auth_flows,
    find_auth_forms,
    verify_steps_for,
)
from yoriqnoma_core.discovery.blueprint_builder import ADMIN_PATH, build
from yoriqnoma_core.discovery.crawler import CrawlResult, PageSeen, crawl
from yoriqnoma_core.discovery.forms import FORMS_JS, signup_roles, to_form
from yoriqnoma_core.discovery.js_routes import (
    routes_from_js,
    routes_from_source_map,
    source_map_url,
)
from yoriqnoma_core.discovery.kit import ScoutKit
from yoriqnoma_core.discovery.urls import clean_url, path_of, template_path
from yoriqnoma_core.discovery.validation_probe import apply_messages, probe_form
from yoriqnoma_core.explorer.datagen import Identity
from yoriqnoma_core.explorer.mailbox import make_mailbox
from yoriqnoma_core.explorer.options import (
    AccountCredentials,
    CancelToken,
    HumanInput,
    ProgressSink,
)
from yoriqnoma_core.explorer.privilege import PrivilegedAccountError, privilege_check
from yoriqnoma_core.explorer.steps import StepContext, StepExecutor, StepFailed
from yoriqnoma_core.writer.providers.base import LLMProvider
from yoriqnoma_schemas import Blueprint, Form

SHOWN_ERROR = (
    "() => { const el = document.querySelector('.error, .errorlist, [role=alert]');"
    " return el ? (el.innerText || '').trim() : ''; }"
)

FetchText = Callable[[str], str | None]  # GET a file of the site (SSRF-checked by the app)


class DiscoveryFailed(Exception):
    """Discovery cannot go on; the reason is shown to the user."""


@dataclass
class DiscoveryInput:
    base_url: str
    role: str
    role_label: str
    project: str
    accounts: dict[str, AccountCredentials] = field(default_factory=dict)  # alias -> login
    passive: bool = False
    allow_signup: bool = True  # may the scout sign up itself when no account is given
    allowed: Callable[[str], bool] | None = None  # robots.txt
    sitemap_urls: list[str] = field(default_factory=list)
    fetch_text: FetchText | None = None
    wait: Callable[[str], Awaitable[None]] | None = None
    classify: LLMProvider | None = None
    agent: LLMProvider | None = None
    max_pages: int = 60
    agent_steps: int = 40
    extra_deny: list[str] = field(default_factory=list)
    generator: str = "yoriqnoma-discovery"


def js_routes(scripts: set[str], fetch_text: FetchText, limit: int = 15) -> set[str]:
    """Route strings from the site's own JS files and their public source maps."""
    found: set[str] = set()
    for url in sorted(scripts)[:limit]:
        text = fetch_text(url)
        if not text:
            continue
        found |= routes_from_js(text)
        map_url = source_map_url(text, url)
        if map_url:
            mapped = fetch_text(map_url)
            if mapped:
                found |= routes_from_source_map(mapped)[0]
    return {template_path(p.replace("*", "")) for p in found if p}


async def sign_in(
    kit: ScoutKit,
    page: Any,
    role: str,
    auth: AuthForms,
    identity: Identity,
    human: HumanInput,
    register: bool,
) -> tuple[bool, bool, list[str]]:
    """(signed in, sign-up sends a confirmation mail, notes)."""
    notes: list[str] = []
    mailbox = make_mailbox(kit.opts.mailbox_kind, kit.opts.mailbox_target)
    ctx = StepContext(
        identity=identity,
        peer=None,
        current_objects={},
        datagen=kit.datagen,
        mailbox=mailbox,
        human=human,
        environment=kit.opts.environment,
        base_url=kit.opts.base_url,
        timeout_ms=kit.opts.step_timeout_ms,
    )
    executor = StepExecutor(page, ctx)
    verify = False
    flows = {f.action: f for f in auth_flows(role, auth, verify_email=False)}
    if register and "register" in flows:
        try:
            for step in flows["register"].steps:
                await executor.run(step)
        except StepFailed as exc:
            notes.append(f"razvedka akkaunti ro'yxatdan o'tmadi: {exc}")
            return False, False, notes
        await page.wait_for_timeout(1500)
        shown = await page.evaluate(SHOWN_ERROR)
        if shown:
            notes.append(f"razvedka akkaunti ro'yxatdan o'tmadi, sayt javobi: {shown[:160]}")
            return False, False, notes
        try:
            # a separate reader: the verify step below must still find the same mail
            probe = make_mailbox(kit.opts.mailbox_kind, kit.opts.mailbox_target)
            await probe.wait_for(identity.email, timeout_s=20)
            verify = True
            auth.verify_steps = verify_steps_for(await page.evaluate(FORMS_JS))
            for step in auth.verify_steps:
                await executor.run(step)
            await page.wait_for_timeout(1000)
        except Exception as exc:  # noqa: BLE001 - no mail: the site does not confirm emails
            verify = False
            notes.append(f"tasdiqlash xati kelmadi yoki ochilmadi: {str(exc)[:160]}")
    if "login" not in flows:
        notes.append("kirish formasi topilmadi: rol sahifalari o'rganilmadi")
        return False, verify, notes
    try:
        for step in flows["login"].steps:
            await executor.run(step)
    except StepFailed as exc:
        notes.append(f"razvedka akkaunti bilan kirib bo'lmadi: {exc}")
        return False, verify, notes
    return True, verify, notes


def provisional(base_url: str, role: str, self_signup: bool, admin_paths: list[str]) -> Blueprint:
    """A minimal blueprint for the privilege check: the admin paths that must stay shut."""
    empty = CrawlResult()
    for path in admin_paths:
        empty.pages[path] = PageSeen(url=base_url.rstrip("/") + path, template=path, title="")
    return build(
        base_url=base_url,
        project="probe",
        role=role,
        role_label=role,
        self_signup=self_signup,
        guest=CrawlResult(),
        member=None,
        js_pages=set(admin_paths),
        auth=AuthForms(),
        signup_choices=[],
        agent_flows=[],
        probed_forms={},
        verify_email=False,
        extra_deny=[],
        public_values=set(),
    )


async def discover_site(
    kit: ScoutKit,
    inp: DiscoveryInput,
    human: HumanInput,
    progress: ProgressSink,
    cancel: CancelToken,
) -> Blueprint:
    """The kit's session must not be started yet; it is started and closed here."""
    await kit.session.start()
    try:
        guest_ctx = await kit.session.account("guest")
        guest = await crawl(
            guest_ctx.page,
            inp.base_url,
            kit.engine,
            inp.allowed,
            start=inp.sitemap_urls,
            max_pages=inp.max_pages,
            cancel=cancel,
            settle=kit.capturer.settle,
            wait=inp.wait,
        )
        progress.advance(len(guest.pages))
        progress.log("info", f"mehmon sifatida {len(guest.pages)} ta sahifa shabloni topildi")
        js_pages: set[str] = set()
        if inp.fetch_text is not None:
            js_pages = await asyncio.to_thread(js_routes, guest.scripts, inp.fetch_text)
        if js_pages:
            progress.log("info", f"JavaScript'dan {len(js_pages)} ta yo'l topildi")
        auth = await find_auth_forms(guest, None if inp.passive else inp.classify)
        signup_choices = signup_roles(auth.register_raw) if auth.register_raw else []
        self_signup = not inp.accounts and auth.register is not None and inp.allow_signup
        member: CrawlResult | None = None
        verify_email = False
        agent_flows = []
        probed: dict[str, Form] = {}
        notes: list[str] = list(auth.notes)

        if inp.passive:
            notes.append("passiv rejim: ro'yxatdan o'tilmadi, faqat ochiq sahifalar o'rganildi")
        elif not inp.accounts and not self_signup:
            raise DiscoveryFailed(
                f"«{inp.role_label or inp.role}» roli uchun test akkaunt kerak: saytda bu rol "
                "uchun ro'yxatdan o'tib bo'lmaydi"
            )
        else:
            role_ctx = await kit.session.account(f"{inp.role}:A")
            given = inp.accounts.get("A")
            if given is not None:
                identity = Identity(
                    inp.role,
                    "A",
                    given.login,
                    given.password.get_secret_value(),
                    "",
                    "",
                    provided=True,
                    username=given.login,
                )
            else:
                identity = kit.datagen.identity(inp.role, "S", kit.opts.mail_domain)
            ok, verify_email, sign_notes = await sign_in(
                kit, role_ctx.page, inp.role, auth, identity, human, register=self_signup
            )
            notes += sign_notes
            if ok:
                admin_paths = sorted(
                    {t for t in set(guest.pages) | js_pages if ADMIN_PATH.search(t)} | {"/admin"}
                )
                probe_bp = provisional(inp.base_url, inp.role, self_signup, admin_paths)
                try:
                    await privilege_check(
                        role_ctx.context, role_ctx.firewall, probe_bp, inp.role, inp.base_url
                    )
                except PrivilegedAccountError as exc:
                    raise DiscoveryFailed(
                        f"Akkaunt adminga o'xshash huquqqa ega: {exc}. Ish to'xtatildi (SEC-6)."
                    ) from exc
                walled = [p.url for p in guest.pages.values() if p.login_wall]
                concrete = [
                    u for u in (clean_url(p, inp.base_url) for p in js_pages if ":" not in p) if u
                ]
                member = await crawl(
                    role_ctx.page,
                    inp.base_url,
                    kit.engine,
                    inp.allowed,
                    start=walled + concrete,
                    max_pages=inp.max_pages,
                    cancel=cancel,
                    settle=kit.capturer.settle,
                    wait=inp.wait,
                )
                progress.advance(len(member.pages))
                progress.log("info", f"«{inp.role}» sifatida {len(member.pages)} ta sahifa topildi")
                if kit.opts.environment == "staging":
                    for tpl, seen in member.pages.items():
                        if ":" in tpl or tpl in guest.pages and not guest.pages[tpl].login_wall:
                            continue
                        for raw in seen.forms:
                            if any(f.get("type") == "password" for f in raw.get("fields", [])):
                                continue
                            result = await probe_form(role_ctx.page, seen.url, raw["index"])
                            if result:
                                form_id = (
                                    f"{tpl.strip('/').replace('/', '_') or 'home'}_{raw['index']}"
                                )
                                probed[form_id] = apply_messages(to_form(raw, tpl, form_id), result)
                if inp.agent is not None:
                    role_pages = [
                        path_of(p.url)
                        for t, p in sorted(member.pages.items())
                        if ":" not in t and not ADMIN_PATH.search(t)
                    ]
                    agent = Agent(
                        kit,
                        inp.agent,
                        inp.role,
                        inp.role_label or inp.role,
                        progress,
                        cancel,
                        AgentLimits(steps=inp.agent_steps),
                        wait=inp.wait,
                    )
                    found = await agent.explore(role_ctx.page, role_pages, [])
                    agent_flows = found.flows
                    notes += found.notes[:20]
                else:
                    notes.append("LLM agenti ishlatilmadi: faqat avtomatik razvedka")
    finally:
        await kit.session.close()

    for note in notes:
        progress.log("info", f"razvedka: {note}")
    bp = build(
        base_url=inp.base_url,
        project=inp.project,
        role=inp.role,
        role_label=inp.role_label or inp.role,
        self_signup=self_signup,
        guest=guest,
        member=member,
        js_pages=js_pages,
        auth=auth,
        signup_choices=signup_choices,
        agent_flows=agent_flows,
        probed_forms=probed,
        verify_email=verify_email,
        extra_deny=inp.extra_deny,
        public_values=kit.ledger.public_values,
        generator=inp.generator,
    )
    progress.log(
        "info",
        f"razvedka blueprint'i: {len(bp.pages)} sahifa, {len(bp.flows)} flow, "
        f"{len(bp.excluded)} chiqarib tashlangan",
    )
    return bp
