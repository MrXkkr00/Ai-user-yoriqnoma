"""A+B: the uploaded (code) blueprint wins; the discovered one only adds what is new.

* Pages: a discovered page is added only if its path is not known to the code blueprint
  at all — neither in ``pages`` nor in ``excluded`` (the code's default-deny stays).
* Flows: added when the id is new and the flow's role is one the code blueprint allows.
* Entities: new names only; known entities get discovered ``pii_fields`` added (more
  replacement is always safe).
* Roles, policy and forms of the code blueprint are kept; disagreements are reported.
"""

from __future__ import annotations

from yoriqnoma_schemas import Blueprint


def merge(code: Blueprint, found: Blueprint) -> tuple[Blueprint, list[str]]:
    notes: list[str] = []
    known_paths = {p.path for p in code.pages} | {p.path for p in code.excluded}
    allowed_roles = {r.id for r in code.roles if r.kind in {"guest", "role"}}
    pages = list(code.pages)
    added_pages = 0
    for page in found.pages:
        if page.path in known_paths:
            continue
        if any(r not in allowed_roles for r in page.roles):
            notes.append(f"razvedka: {page.path} — kodda yo'q rol uchun, qo'shilmadi")
            continue
        pages.append(page.model_copy(update={"source": f"discovered: {page.source}"}))
        added_pages += 1
    excluded = list(code.excluded) + [p for p in found.excluded if p.path not in known_paths]

    flow_ids = {f.id for f in code.flows}
    flows = list(code.flows)
    added_flows = 0
    for flow in found.flows:
        if flow.id in flow_ids or flow.action in {"register", "login"}:
            continue
        if flow.role not in allowed_roles:
            continue
        requires = [r for r in flow.requires if r in flow_ids]
        missing = [r for r in flow.requires if r not in flow_ids]
        login = f"{flow.role}.login"
        if missing and login in flow_ids and login not in requires:
            requires.append(login)
        flows.append(flow.model_copy(update={"requires": requires}))
        flow_ids.add(flow.id)
        added_flows += 1

    entities = list(code.entities)
    by_name = {e.name: i for i, e in enumerate(entities)}
    for entity in found.entities:
        if entity.name in by_name:
            i = by_name[entity.name]
            extra = sorted(set(entity.pii_fields) - set(entities[i].pii_fields))
            if extra:
                entities[i] = entities[i].model_copy(
                    update={"pii_fields": sorted(set(entities[i].pii_fields) | set(extra))}
                )
        else:
            entities.append(entity)
            notes.append(f"razvedka: yangi obyekt «{entity.name}» (ishonch {entity.confidence})")

    nav = list(code.nav) + [n for n in found.nav if n not in code.nav]
    notes.insert(
        0, f"A+B birlashtirildi: {added_pages} ta sahifa va {added_flows} ta flow qo'shildi"
    )
    merged = code.model_copy(
        update={
            "source": "merged",
            "pages": pages,
            "excluded": excluded,
            "flows": flows,
            "entities": entities,
            "nav": nav,
        }
    )
    return Blueprint.model_validate(merged.model_dump()), notes
