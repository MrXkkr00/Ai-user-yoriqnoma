"""Discovered blueprint (``source="discovered"``) from what the scout saw (ARCHITECTURE §7.6).

Pages (TZ FR-S4, default-deny):
* opened as a guest -> ``guest``;
* opened only after signing in (a guest was sent to the login page) -> the target role;
* admin-like paths (deny_paths, ``/admin``, users/roles/permissions management) ->
  ``excluded``; seen only in JavaScript but never opened -> ``excluded`` (unclear).

Roles (TZ FR-RL1, FR-RL2): guest; the target role the user named; sign-up choices of the
site; an ``admin`` role always ``excluded``. Flows: sign-up and sign-in, one "open the
page" flow per page template, one flow per form of the role's pages, and the agent's
flows. Every item carries a ``confidence``.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from urllib.parse import urlsplit

from yoriqnoma_core.discovery.auth_flow import AuthForms, auth_flows
from yoriqnoma_core.discovery.crawler import CrawlResult, PageSeen
from yoriqnoma_core.discovery.forms import fill_steps, to_form
from yoriqnoma_core.discovery.network_infer import infer_entities
from yoriqnoma_core.safety.pii import find_pii, mask_text
from yoriqnoma_schemas import (
    Blueprint,
    Entity,
    Flow,
    Form,
    Policy,
    RoleInfo,
    RouteInfo,
    Step,
)
from yoriqnoma_schemas.policy import DEFAULT_DENY_PATHS

ADMIN_PATH = re.compile(
    r"(^|/)(admin|administrator|superadmin|ops|staff/users|users/manage|roles|permissions|"
    r"settings/site|site-settings|dashboard/admin|wp-admin|backend)(/|$)",
    re.I,
)
STAGES = {
    "profile": "manage",
    "account": "settings",
    "settings": "settings",
    "sozlama": "settings",
    "message": "social",
    "chat": "social",
    "xabar": "social",
    "pay": "payment",
    "checkout": "payment",
    "tolov": "payment",
    "orders": "core",
    "order": "core",
}


def _stage(path: str) -> str:
    low = path.lower()
    for word, stage in STAGES.items():
        if word in low:
            return stage
    return "core"


def _title(page: PageSeen, ignore: set[str]) -> str:
    """A page title without personal data (detail pages get a generic name)."""
    if ":" in page.template:
        base = page.template.rstrip("/").split("/")
        words = [w for w in base if w and not w.startswith(":")]
        return f"«{words[-1] if words else 'sahifa'}» tafsiloti"
    text = page.h1 or page.title.split("—")[0].split("|")[0].strip() or page.template
    found = find_pii(text, ignore)
    return mask_text(text, found)[:100] if found else text[:100]


def _flow_id(role: str, template: str, prefix: str = "page") -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", template.lower()).strip("_") or "home"
    return f"{role}.{prefix}.{slug}"[:120]


def build(
    *,
    base_url: str,
    project: str,
    role: str,
    role_label: str,
    self_signup: bool,
    guest: CrawlResult,
    member: CrawlResult | None,
    js_pages: set[str],
    auth: AuthForms,
    signup_choices: list[str],
    agent_flows: list[Flow],
    probed_forms: dict[str, Form],
    verify_email: bool,
    extra_deny: list[str],
    public_values: set[str],
    generator: str = "yoriqnoma-discovery",
) -> Blueprint:
    deny = sorted(set(DEFAULT_DENY_PATHS) | set(extra_deny))
    policy = Policy(target_role=role, deny_paths=deny)
    roles = [
        RoleInfo(
            id="guest",
            label="Mehmon",
            kind="guest",
            reason="kirmagan foydalanuvchi",
            source="discovered",
        ),
        RoleInfo(
            id=role,
            label=role_label or role,
            kind="role",
            reason="ish egasi ko'rsatgan rol"
            + (" (o'zi ro'yxatdan o'tadi)" if self_signup else ""),
            source="job",
            self_signup=self_signup,
        ),
        RoleInfo(
            id="admin",
            label="Administrator",
            kind="excluded",
            reason="adminga o'xshash rol: yo'riqnoma yozilmaydi (default-deny)",
            source="discovered",
        ),
    ]
    for choice in signup_choices:
        cid = re.sub(r"[^a-z0-9_]+", "_", choice.lower()).strip("_")[:40]
        if cid and cid not in {r.id for r in roles}:
            roles.append(
                RoleInfo(
                    id=cid,
                    label=choice[:60],
                    kind="role",
                    self_signup=True,
                    reason="ro'yxatdan o'tishdagi tanlov",
                    source="discovered: sign-up form",
                )
            )

    pages: list[RouteInfo] = []
    excluded: list[RouteInfo] = []
    seen: set[str] = set()

    def add(path: str, access: str, roles_: list[str], reason: str, source: str) -> None:
        if path in seen:
            return
        seen.add(path)
        if access == "excluded":
            excluded.append(
                RouteInfo(
                    path=path,
                    kind="page",
                    methods=["GET"],
                    access="excluded",
                    reason=reason,
                    source=source,
                )
            )
        else:
            pages.append(
                RouteInfo(
                    path=path,
                    kind="page",
                    methods=["GET"],
                    access=access,  # type: ignore[arg-type]
                    roles=roles_,
                    reason=reason,
                    source=source,
                )
            )

    guest_open = {t for t, p in guest.pages.items() if not p.login_wall}
    walled = {t for t, p in guest.pages.items() if p.login_wall}
    member_pages = member.pages if member else {}
    for tpl in sorted(set(guest.pages) | set(member_pages) | js_pages):
        if ADMIN_PATH.search(tpl) or any(_glob(tpl, d) for d in deny):
            add(tpl, "excluded", [], "adminga o'xshash yo'l (default-deny)", "discovered")
        elif tpl in guest_open and tpl not in walled:
            add(tpl, "guest", [], "mehmon sifatida ochildi", "crawl:guest")
        elif tpl in member_pages:
            add(tpl, "roles", [role], f"«{role}» akkaunti bilan ochildi", f"crawl:{role}")
        else:
            add(
                tpl, "excluded", [], "faqat JS'da ko'rindi, ochilmadi (noaniq — default-deny)", "js"
            )

    forms: list[Form] = []
    flows: list[Flow] = list(auth_flows(role, auth, verify_email=verify_email) if auth else [])
    if not self_signup:
        flows = [f for f in flows if f.action != "register"]
        for f in flows:
            f.requires = [r for r in f.requires if not r.endswith(".register")]
    login_id = f"{role}.login" if any(f.action == "login" for f in flows) else None

    for page in pages:
        crawl = guest if page.access == "guest" else member
        seen_page = crawl.pages.get(page.path) if crawl else None
        flow_role = "guest" if page.access == "guest" else role
        if seen_page is None or ":" in page.path:
            continue
        flows.append(
            Flow(
                id=_flow_id(flow_role, page.path),
                title=_title(seen_page, public_values),
                stage="start" if flow_role == "guest" else _stage(page.path),  # type: ignore[arg-type]
                role=flow_role,
                action="view",
                requires=[login_id] if flow_role != "guest" and login_id else [],
                source=f"crawl: {seen_page.url and urlsplit(seen_page.url).path}",
                confidence=0.8,
                steps=[
                    Step(action="goto", path=page.path),
                    Step(action="expect_url", path=page.path),
                ],
            )
        )
        if flow_role == "guest":
            continue
        for raw in seen_page.forms:
            form_id = f"{page.path.strip('/').replace('/', '_') or 'home'}_{raw['index']}"
            form = probed_forms.get(form_id) or to_form(raw, page.path, form_id)
            if not form.fields or (auth.login and auth.login[1].id == form.id):
                continue
            forms.append(form)
            if form.submit.name is None:
                continue
            flows.append(
                Flow(
                    id=_flow_id(role, page.path, "form") + f"_{raw['index']}",
                    title=f"«{form.submit.name}» — {_title(seen_page, public_values)}"[:120],
                    stage=_stage(page.path),  # type: ignore[arg-type]
                    role=role,
                    action="submit",
                    requires=[login_id] if login_id else [],
                    source=f"form: {page.path}",
                    confidence=0.5,
                    steps=[
                        Step(action="goto", path=page.path),
                        *fill_steps(form),
                        Step(action="click", target=form.submit),
                    ],
                )
            )
    if auth.register:
        forms.append(auth.register[1])
    if auth.login:
        forms.append(auth.login[1])
    known = {f.id for f in flows}
    for flow in agent_flows:
        if flow.id not in known:
            flow.requires = [login_id] if login_id else []
            flows.append(flow)
            known.add(flow.id)

    calls = list(guest.api_calls) + (list(member.api_calls) if member else [])
    entities: list[Entity] = infer_entities(calls)
    for entity in entities:
        entity.created_by = [role] if "create" in entity.actions else []
    nav = list(guest.nav)
    for item in member.nav if member else []:
        if item not in nav:
            nav.append(item)
    nav = [n for n in nav if not ADMIN_PATH.search(n["path"]) and n["path"] in seen]
    return Blueprint(
        project=project,
        base_url=base_url,  # type: ignore[arg-type]
        source="discovered",
        generated_at=datetime.now(UTC),
        generator=generator,
        policy=policy,
        roles=roles,
        pages=pages,
        forms=_unique_forms(forms),
        entities=entities,
        flows=flows,
        nav=nav,
        excluded=excluded,
    )


def _glob(path: str, pattern: str) -> bool:
    import fnmatch

    return fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(path + "/", pattern)


def _unique_forms(forms: list[Form]) -> list[Form]:
    out: dict[str, Form] = {}
    for form in forms:
        out.setdefault(form.id, form)
    return list(out.values())
