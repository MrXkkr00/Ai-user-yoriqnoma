"""Mode B: build a blueprint from the site itself (ARCHITECTURE §7.6, TZ FR-SV5).

    preflight -> guest crawl (+ sitemap, + routes from the site's JavaScript)
    -> sign-up/sign-in forms -> sign in as the target role (not in passive mode)
    -> privilege check (SEC-6) -> crawl as the role -> validation probe
    -> Claude agent (budget share of the job) -> discovered blueprint

The result covers only what the site shows to a guest and to the given accounts; the
coverage report says so. Passive mode (unverified domain): guest pages only.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from django.conf import settings
from pydantic import SecretStr

from jobs.models import Job
from jobs.pipeline import JobFailed, explore_options
from scout.agent import Agent, AgentLimits
from scout.auth_flow import AuthForms, auth_flows, find_auth_forms, verify_steps_for
from scout.blueprint_builder import ADMIN_PATH, build
from scout.crawler import CrawlResult, PageSeen, crawl
from scout.forms import FORMS_JS, signup_roles, to_form
from scout.js_routes import routes_from_js, routes_from_source_map, source_map_url
from scout.kit import ScoutKit
from scout.preflight import Preflight, preflight
from scout.urls import clean_url, path_of, template_path
from scout.validation_probe import apply_messages, probe_form
from security.robots import deny_globs
from security.ssrf import safe_get
from yoriqnoma_core.explorer.datagen import Identity
from yoriqnoma_core.explorer.mailbox import make_mailbox
from yoriqnoma_core.explorer.options import CancelToken, HumanInput, ProgressSink
from yoriqnoma_core.explorer.privilege import PrivilegedAccountError, privilege_check
from yoriqnoma_core.explorer.steps import StepContext, StepExecutor, StepFailed
from yoriqnoma_core.writer.providers.base import LLMProvider
from yoriqnoma_core.writer.providers.claude import ClaudeProvider, make_sanitizer, prices_from
from yoriqnoma_schemas import Blueprint, Form, Policy
from yoriqnoma_schemas.policy import DEFAULT_DENY_PATHS

SHOWN_ERROR = (
    "() => { const el = document.querySelector('.error, .errorlist, [role=alert]');"
    " return el ? (el.innerText || '').trim() : ''; }"
)


class ScoutFailed(JobFailed):
    """Mode B cannot go on; the reason is shown to the user."""


def claude_for_scout(job: Job, kit: ScoutKit, progress: ProgressSink) -> LLMProvider | None:
    """Claude for the agent and form classification, with its own share of the budget."""
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        return None
    share = float(job.budget_usd) * float(settings.YORIQNOMA_SCOUT_AGENT_SHARE)
    return ClaudeProvider(
        api_key=SecretStr(key),
        models=dict(settings.YORIQNOMA_MODELS),
        prices=prices_from(settings.YORIQNOMA_PRICES),
        budget_usd=share,
        on_cost=lambda payload: progress.event(str(payload.get("kind", "cost")), payload),
        sanitize=lambda text: make_sanitizer(kit.ledger.ignore())(text),
        image_roots=[kit.run_dir / "capture"],
    )


# Replaced in tests (no Claude in unit tests).
provider_factory: Any = claude_for_scout


def _js_routes(scripts: set[str], limit: int = 15) -> set[str]:
    """Route strings from the site's own JS files and their public source maps."""
    found: set[str] = set()
    for url in sorted(scripts)[:limit]:
        try:
            answer = safe_get(url, max_bytes=8 * 1024 * 1024)
        except Exception:  # noqa: BLE001 - a script that cannot be read is skipped
            continue
        if answer.status != 200:
            continue
        text = answer.text
        found |= routes_from_js(text)
        map_url = source_map_url(text, url)
        if map_url:
            try:
                mapped = safe_get(map_url, max_bytes=16 * 1024 * 1024)
            except Exception:  # noqa: BLE001
                continue
            if mapped.status == 200:
                found |= routes_from_source_map(mapped.text)[0]
    return {template_path(p.replace("*", "")) for p in found if p}


async def _sign_in(
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


def _provisional(base_url: str, role: str, self_signup: bool, admin_paths: list[str]) -> Blueprint:
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


async def discover(
    job: Job,
    run_dir: Path,
    human: HumanInput,
    progress: ProgressSink,
    cancel: CancelToken,
    base: Blueprint | None = None,
) -> Blueprint:
    opts = explore_options(job)
    progress.stage("scout", int(settings.YORIQNOMA_SCOUT_MAX_PAGES) * 2)
    pre: Preflight = await asyncio.to_thread(preflight, job.url, not job.passive)
    progress.log(
        "info",
        f"preflight: til «{pre.lang or '-'}», texnologiya: {', '.join(pre.tech) or '-'}, "
        f"sitemap'da {len(pre.sitemap_urls)} ta sahifa",
    )
    extra_deny = deny_globs(pre.robots) if job.passive else []
    policy = Policy(
        target_role=job.role, deny_paths=sorted(set(DEFAULT_DENY_PATHS) | set(extra_deny))
    )
    kit = ScoutKit.create(opts, run_dir, policy)
    max_pages = int(settings.YORIQNOMA_SCOUT_MAX_PAGES)
    accounts = opts.accounts.get(job.role, {})
    await kit.session.start()
    try:
        guest_ctx = await kit.session.account("guest")
        guest = await crawl(
            guest_ctx.page,
            job.url,
            kit.engine,
            pre.robots,
            start=pre.sitemap_urls,
            max_pages=max_pages,
            cancel=cancel,
            settle=kit.capturer.settle,
        )
        progress.advance(len(guest.pages))
        progress.log("info", f"mehmon sifatida {len(guest.pages)} ta sahifa shabloni topildi")
        js_pages = await asyncio.to_thread(_js_routes, guest.scripts)
        if js_pages:
            progress.log("info", f"JavaScript'dan {len(js_pages)} ta yo'l topildi")
        classify = provider_factory(job, kit, progress) if not job.passive else None
        auth = await find_auth_forms(guest, classify)
        signup_choices = signup_roles(auth.register_raw) if auth.register_raw else []
        self_signup = not accounts and auth.register is not None
        member: CrawlResult | None = None
        verify_email = False
        agent_flows = []
        probed: dict[str, Form] = {}
        notes: list[str] = list(auth.notes)

        if job.passive:
            notes.append("passiv rejim: ro'yxatdan o'tilmadi, faqat ochiq sahifalar o'rganildi")
        elif not accounts and auth.register is None:
            raise ScoutFailed(
                f"«{job.role_label or job.role}» roli uchun test akkaunt bering: saytda "
                "ro'yxatdan o'tish formasi topilmadi"
            )
        else:
            role_ctx = await kit.session.account(f"{job.role}:A")
            if accounts.get("A") is not None:
                given = accounts["A"]
                identity = Identity(
                    job.role,
                    "A",
                    given.login,
                    given.password.get_secret_value(),
                    "",
                    "",
                    provided=True,
                    username=given.login,
                )
            else:
                identity = kit.datagen.identity(job.role, "S", opts.mail_domain)
            ok, verify_email, sign_notes = await _sign_in(
                kit, role_ctx.page, job.role, auth, identity, human, register=self_signup
            )
            notes += sign_notes
            if ok:
                admin_paths = sorted(
                    {t for t in set(guest.pages) | js_pages if ADMIN_PATH.search(t)} | {"/admin"}
                )
                probe_bp = _provisional(job.url, job.role, self_signup, admin_paths)
                try:
                    await privilege_check(
                        role_ctx.context, role_ctx.firewall, probe_bp, job.role, job.url
                    )
                except PrivilegedAccountError as exc:
                    raise ScoutFailed(
                        f"Akkaunt adminga o'xshash huquqqa ega: {exc}. Ish to'xtatildi (SEC-6)."
                    ) from exc
                walled = [p.url for p in guest.pages.values() if p.login_wall]
                concrete = [
                    u for u in (clean_url(p, job.url) for p in js_pages if ":" not in p) if u
                ]
                member = await crawl(
                    role_ctx.page,
                    job.url,
                    kit.engine,
                    pre.robots,
                    start=walled + concrete,
                    max_pages=max_pages,
                    cancel=cancel,
                    settle=kit.capturer.settle,
                )
                progress.advance(len(member.pages))
                progress.log("info", f"«{job.role}» sifatida {len(member.pages)} ta sahifa topildi")
                if opts.environment == "staging":
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
                agent_provider = provider_factory(job, kit, progress)
                if agent_provider is not None:
                    role_pages = [
                        path_of(p.url)
                        for t, p in sorted(member.pages.items())
                        if ":" not in t and not ADMIN_PATH.search(t)
                    ]
                    agent = Agent(
                        kit,
                        agent_provider,
                        job.role,
                        job.role_label or job.role,
                        progress,
                        cancel,
                        AgentLimits(steps=int(settings.YORIQNOMA_SCOUT_AGENT_STEPS)),
                    )
                    found = await agent.explore(role_ctx.page, role_pages, [])
                    agent_flows = found.flows
                    notes += found.notes[:20]
                else:
                    notes.append(
                        "Claude agenti ishlatilmadi (kalit yo'q): faqat avtomatik razvedka"
                    )
    finally:
        await kit.session.close()

    for note in notes:
        progress.log("info", f"razvedka: {note}")
    bp = build(
        base_url=job.url,
        project=base.project if base else (urlsplit(job.url).hostname or "site"),
        role=job.role,
        role_label=job.role_label or job.role,
        self_signup=self_signup,
        guest=guest,
        member=member,
        js_pages=js_pages,
        auth=auth,
        signup_choices=signup_choices,
        agent_flows=agent_flows,
        probed_forms=probed,
        verify_email=verify_email,
        extra_deny=extra_deny,
        public_values=kit.ledger.public_values,
    )
    progress.log(
        "info",
        f"razvedka blueprint'i: {len(bp.pages)} sahifa, {len(bp.flows)} flow, "
        f"{len(bp.excluded)} chiqarib tashlangan",
    )
    return bp
