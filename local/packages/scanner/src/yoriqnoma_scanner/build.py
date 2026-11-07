"""Assemble the Blueprint from parser results (TZ FR-S4..S7)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime

from yoriqnoma_scanner import __version__
from yoriqnoma_scanner.classify import (
    classify_roles,
    classify_route,
    deny_glob_match,
    page_needs_auth_from_api,
)
from yoriqnoma_scanner.entities import EntityIndex, build_entities, paths_match
from yoriqnoma_scanner.flows import FlowContext, Page, build_flows
from yoriqnoma_scanner.parsers.base import ParseResult, RouteCandidate
from yoriqnoma_schemas import (
    DEFAULT_DENY_PATHS,
    Blueprint,
    Flow,
    Form,
    FormField,
    Policy,
    RoleInfo,
    RouteInfo,
)


@dataclass
class BuildOutput:
    blueprint: Blueprint
    notes: list[str] = field(default_factory=list)
    unknown_routes: list[RouteInfo] = field(default_factory=list)
    entity_index: EntityIndex | None = None


def to_glob(path: str) -> str:
    return re.sub(r":[^/]+", "*", path)


def status_labels(i18n: dict[str, str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, text in i18n.items():
        parts = key.split(".")
        if len(parts) >= 2 and parts[-2] in {"status", "statuses", "state"}:
            out.setdefault(parts[-1], text)
    return out


def merge_rules(front: str | None, back: str | None) -> str | None:
    rules: dict[str, str] = {}
    for source in (front, back):  # backend rules win
        for rule in (source or "").split("|"):
            key, _, value = rule.partition(":")
            if key:
                rules[key] = value
    return "|".join(f"{k}:{v}" for k, v in rules.items()) or None


def build_blueprint(
    parsed: ParseResult,
    e2e_flows: list[Flow],
    base_url: str,
    project: str,
) -> BuildOutput:
    notes = list(parsed.notes)
    roles = classify_roles(parsed)
    deny = list(DEFAULT_DENY_PATHS)

    api_pairs: list[tuple[RouteCandidate, RouteInfo]] = []
    page_pairs: list[tuple[RouteCandidate, RouteInfo]] = []
    for route in parsed.routes:
        info = classify_route(route, roles, deny)
        (api_pairs if route.kind == "api" else page_pairs).append((route, info))

    def api_info(load: str) -> RouteInfo | None:
        method, _, path = load.partition(" ")
        for cand, info in api_pairs:
            if method in cand.methods and paths_match(cand.path, path):
                return info
        return None

    pages: list[Page] = []
    for cand, info in page_pairs:
        component = parsed.components.get(cand.component or "")
        if component is not None:
            loads = {load: api_info(load) for load in component.loads}
            known = {k: v for k, v in loads.items() if v is not None}
            info = page_needs_auth_from_api(info, known, list(known))
        pages.append(Page(info, component))

    entity_index = build_entities(parsed.entities, api_pairs, status_labels(parsed.i18n))

    forms_by_id: dict[str, Form] = {}
    for page in pages:
        if page.component is None or page.route.access == "excluded":
            continue
        for form in page.component.forms:
            forms_by_id[form.id] = _enrich_form(form, page.route.path, api_pairs, parsed)

    usable_pages = [p for p in pages if p.route.access != "excluded"]
    nav_labels: dict[str, str] = {}
    for item in parsed.nav:
        nav_labels.setdefault(item.path, item.label)
    ctx = FlowContext(
        roles=roles,
        pages=usable_pages,
        api=[(c, i) for c, i in api_pairs if i.access != "excluded"],
        entities=entity_index,
        forms_by_id=forms_by_id,
        nav_labels=nav_labels,
    )
    flows = build_flows(ctx, parsed.components, e2e_flows)
    notes += ctx.notes
    flows = _drop_unsafe(
        flows, deny + [to_glob(p.route.path) for p in pages if p.route.access == "excluded"], notes
    )

    all_infos = [i for _, i in api_pairs] + [p.route for p in pages]
    kept = [i for i in all_infos if i.access != "excluded"]
    excluded = [i for i in all_infos if i.access == "excluded"]
    deny += sorted({to_glob(i.path) for i in excluded} - set(deny))

    nav = [
        {"label": n.label, "path": n.path}
        for n in parsed.nav
        if any(p.route.path == n.path for p in usable_pages) and not deny_glob_match(n.path, deny)
    ]
    selectable = [r for r in roles if r.kind == "role"]
    target = next((r.id for r in selectable if r.self_signup), None) or (
        selectable[0].id if selectable else "guest"
    )
    blueprint = Blueprint(
        project=project,
        base_url=base_url,  # type: ignore[arg-type]
        source="code",
        generated_at=datetime.now(UTC),
        generator=f"yoriqnoma_scanner {__version__}",
        policy=Policy(target_role=target, deny_paths=deny),
        roles=roles,
        pages=kept,
        forms=list(forms_by_id.values()),
        entities=list(entity_index.entities.values()),
        flows=flows,
        nav=nav,
        i18n=parsed.i18n,
        excluded=excluded,
    )
    unknown = [i for i in excluded if "noaniq" in i.reason]
    return BuildOutput(blueprint, notes, unknown, entity_index)


def _enrich_form(
    form: Form,
    page_path: str,
    api_pairs: list[tuple[RouteCandidate, RouteInfo]],
    parsed: ParseResult,
) -> Form:
    backend: dict[str, FormField] = {}
    if form.api:
        method, _, path = form.api.partition(" ")
        for cand, _info in api_pairs:
            if method in cand.methods and paths_match(cand.path, path) and cand.request_model:
                backend = {f.name: f for f in parsed.request_models.get(cand.request_model, [])}
                break
    fields = []
    for f in form.fields:
        back = backend.get(f.name)
        rules = merge_rules(f.rules, back.rules if back else None)
        fields.append(
            f.model_copy(
                update={"rules": rules, "required": f.required or bool(back and back.required)}
            )
        )
    return form.model_copy(update={"page_path": page_path, "fields": fields})


def _drop_unsafe(flows: list[Flow], deny: list[str], notes: list[str]) -> list[Flow]:
    """Never keep a flow that opens a denied path (defence in depth)."""
    bad = {
        f.id
        for f in flows
        for s in f.steps
        if s.action == "goto"
        and s.path
        and deny_glob_match(re.sub(r"\{own:[^}]+\}", "x", s.path), deny)
    }
    changed = True
    while changed:
        changed = False
        for f in flows:
            if f.id not in bad and set(f.requires) & bad:
                bad.add(f.id)
                changed = True
    for fid in sorted(bad):
        notes.append(f"flow {fid} taqiqlangan yo'lga olib boradi: chiqarildi")
    return [f for f in flows if f.id not in bad]


def roles_summary(roles: list[RoleInfo]) -> str:
    usable = [r for r in roles if r.kind == "role"]
    return f"Saytda administratordan boshqa {len(usable)} ta rol topildi"
