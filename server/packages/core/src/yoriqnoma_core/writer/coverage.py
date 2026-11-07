"""Coverage of the manual (TZ FR-W6): role routes, forms, buttons, actions, statuses, sections."""

from __future__ import annotations

import fnmatch
import re
from urllib.parse import urlsplit

from yoriqnoma_core.text_uz import normalize_uz
from yoriqnoma_schemas import Blueprint, CaptureRun, Coverage, CoverageItem, Manual


def _matches(template: str, path: str) -> bool:
    pattern = re.sub(r":[^/]+", "*", template)
    return fnmatch.fnmatch(path.rstrip("/") or "/", pattern.rstrip("/") or "/")


def compute(bp: Blueprint, capture: CaptureRun, manual: Manual) -> Coverage:
    role = capture.role
    items: list[CoverageItem] = []
    visited = {urlsplit(s.url).path for s in capture.states}
    in_manual = {a.flow_id for s in manual.sections for a in s.articles if s.stage != "unverified"}
    flow_status = {f.flow_id: f for f in capture.flows}

    # routes the role (or a guest) can open
    for page in bp.pages:
        if page.kind != "page":
            continue
        if not (page.access == "guest" or role in page.roles):
            continue
        covered = any(_matches(page.path, v) for v in visited)
        items.append(
            CoverageItem(
                kind="route",
                key=page.path,
                covered=covered,
                reason=None if covered else "sahifa ochilmadi",
            )
        )

    # forms on those pages
    flows_by_id = {f.id: f for f in bp.flows}
    for form in bp.forms:
        form_page = next((p for p in bp.pages if p.path == form.page_path), None)
        if form_page is None or not (form_page.access == "guest" or role in form_page.roles):
            continue
        labels = {normalize_uz(f.label or f.name) for f in form.fields}
        used = False
        for fid in in_manual:
            mflow = flows_by_id.get(fid)
            if mflow is not None and any(
                s.target is not None
                and normalize_uz(s.target.label or s.target.name or "") in labels
                for s in mflow.steps
            ):
                used = True
                break
        items.append(
            CoverageItem(
                kind="form",
                key=form.id,
                covered=used,
                reason=None if used else "formani to'ldiruvchi tekshirilgan flow yo'q",
            )
        )

    # buttons seen by the role and explained somewhere in the manual
    mentioned = set()
    for section in manual.sections:
        for article in section.articles:
            for step in article.steps:
                mentioned |= {normalize_uz(n) for n in re.findall(r"«([^»]+)»", step.text)}
    for ref in manual.reference:
        mentioned |= {normalize_uz(e) for e in ref.elements}
    buttons = sorted(
        {
            el.name
            for s in capture.states
            if not s.patched
            for el in s.elements
            if el.kind == "button" and el.name
        }
    )
    for name in buttons:
        ok = normalize_uz(name) in mentioned
        items.append(
            CoverageItem(
                kind="button",
                key=name,
                covered=ok,
                reason=None if ok else "yo'riqnomada tilga olinmagan",
            )
        )

    # entity actions of the role
    for flow in bp.flows:
        if flow.role != role or not flow.entity or not flow.action:
            continue
        result = flow_status.get(flow.id)
        ok = flow.id in in_manual
        reason = None if ok else (result.reason if result and result.reason else "flow bajarilmadi")
        items.append(
            CoverageItem(
                kind="action", key=f"{flow.entity}.{flow.action}", covered=ok, reason=reason
            )
        )

    # statuses of the role's entities
    seen_status = {(s.entity, s.entity_status) for s in capture.states if s.entity_status}
    role_entities = {f.entity for f in bp.flows if f.role == role and f.entity}
    for entity in bp.entities:
        if entity.name not in role_entities:
            continue
        for status in entity.statuses:
            ok = (entity.name, status.value) in seen_status
            items.append(
                CoverageItem(
                    kind="status",
                    key=f"{entity.name}.{status.value}",
                    covered=ok,
                    reason=None if ok else "holat ko'rsatilmadi",
                )
            )

    for section in manual.sections:
        if section.stage == "unverified":
            continue
        ok = bool(section.articles) or section.stage in {"reference", "faq"}
        items.append(
            CoverageItem(kind="section", key=section.title, covered=ok, reason=section.empty_reason)
        )

    percent: dict[str, float] = {}
    for kind in ("route", "form", "button", "action", "status"):
        group = [i for i in items if i.kind == kind]
        if group:
            percent[kind] = round(100.0 * sum(i.covered for i in group) / len(group), 1)
    core = [i for i in items if i.kind in {"route", "form", "action", "status"}]
    if core:
        percent["total"] = round(100.0 * sum(i.covered for i in core) / len(core), 1)
    return Coverage(percent=percent, items=items)
