"""Blueprint review overrides (TZ FR-L5). They only REDUCE: exclude pages or flows, rename.

Anything excluded by the scanner stays excluded: an override can never add a page,
flow or role back (default-deny is kept).
"""

from __future__ import annotations

import re
from typing import Any

from yoriqnoma_schemas import Blueprint

ALLOWED_KEYS = {"exclude_pages", "exclude_flows", "rename_flows"}


def _page_matches(template: str, step_path: str) -> bool:
    path = re.sub(r"\{own:[^}]+\}", ":x", step_path.split("?")[0])
    a = [s for s in template.split("/") if s]
    b = [s for s in path.split("/") if s]
    return len(a) == len(b) and all(
        x == y or x.startswith(":") or y.startswith(":") for x, y in zip(a, b, strict=True)
    )


def apply(blueprint: Blueprint, overrides: dict[str, Any]) -> tuple[Blueprint, list[str]]:
    unknown = set(overrides) - ALLOWED_KEYS
    if unknown:
        raise ValueError(f"noma'lum override kalitlari: {sorted(unknown)}")
    notes: list[str] = []
    excluded_pages = set(overrides.get("exclude_pages", []))
    excluded_flows = set(overrides.get("exclude_flows", []))
    renames: dict[str, str] = dict(overrides.get("rename_flows", {}))

    pages = [p for p in blueprint.pages if p.path not in excluded_pages]
    for path in sorted(excluded_pages):
        notes.append(f"sahifa {path} foydalanuvchi tomonidan chiqarildi")

    removed: set[str] = set()
    for flow in blueprint.flows:
        if flow.id in excluded_flows:
            removed.add(flow.id)
            notes.append(f"flow {flow.id} foydalanuvchi tomonidan chiqarildi")
        elif any(
            s.action == "goto" and s.path and any(_page_matches(p, s.path) for p in excluded_pages)
            for s in flow.steps
        ):
            removed.add(flow.id)
            notes.append(f"flow {flow.id} chiqarilgan sahifani ochadi: chiqarildi")
    changed = True
    while changed:
        changed = False
        for flow in blueprint.flows:
            if flow.id not in removed and set(flow.requires) & removed:
                removed.add(flow.id)
                notes.append(
                    f"flow {flow.id} chiqarilgan flow'ga bog'liq ("
                    f"{', '.join(sorted(set(flow.requires) & removed))}): chiqarildi"
                )
                changed = True

    flows = []
    for flow in blueprint.flows:
        if flow.id in removed:
            continue
        title = renames.get(flow.id)
        if title is not None and title.strip():
            flow = flow.model_copy(update={"title": title.strip()[:200]})
        flows.append(flow)
    ignored = sorted(set(renames) - {f.id for f in flows})
    for fid in ignored:
        notes.append(f"nomini o'zgartirish e'tiborsiz qoldirildi: {fid} yo'q")

    excluded = list(blueprint.excluded)  # never shrinks: excluded stays excluded
    updated = blueprint.model_copy(update={"pages": pages, "flows": flows, "excluded": excluded})
    return Blueprint.model_validate(updated.model_dump()), notes
