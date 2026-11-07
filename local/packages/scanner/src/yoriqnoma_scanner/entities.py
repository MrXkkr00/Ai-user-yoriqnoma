"""Entities: actions from API routes, statuses and which roles reach them (TZ FR-S5)."""

from __future__ import annotations

from dataclasses import dataclass, field

from yoriqnoma_scanner.parsers.base import EntityCandidate, RouteCandidate
from yoriqnoma_scanner.parsers.sqlalchemy_models import singular
from yoriqnoma_schemas import Entity, EntityStatus, RouteInfo

ENTITY_UZ = {
    "order": ("buyurtma", "buyurtmalar"),
    "product": ("mahsulot", "mahsulotlar"),
    "review": ("sharh", "sharhlar"),
    "message": ("xabar", "xabarlar"),
    "user": ("foydalanuvchi", "foydalanuvchilar"),
    "comment": ("izoh", "izohlar"),
    "post": ("post", "postlar"),
    "ticket": ("murojaat", "murojaatlar"),
    "application": ("ariza", "arizalar"),
    "booking": ("bron", "bronlar"),
    "invoice": ("hisob", "hisoblar"),
    "payment": ("to'lov", "to'lovlar"),
    "cart": ("savat", "savatlar"),
    "task": ("vazifa", "vazifalar"),
    "course": ("kurs", "kurslar"),
    "lesson": ("dars", "darslar"),
    "article": ("maqola", "maqolalar"),
    "category": ("kategoriya", "kategoriyalar"),
    "address": ("manzil", "manzillar"),
    "delivery": ("yetkazish", "yetkazishlar"),
    "shipment": ("jo'natma", "jo'natmalar"),
    "appointment": ("qabul", "qabullar"),
    "document": ("hujjat", "hujjatlar"),
    "request": ("so'rov", "so'rovlar"),
}


def entity_words(name: str) -> tuple[str, str]:
    return ENTITY_UZ.get(name, (name.replace("_", " "), name.replace("_", " ")))


def segments(path: str) -> list[str]:
    return [s for s in path.split("/") if s]


def paths_match(template: str, path: str) -> bool:
    """``/api/orders/:id/pay`` matches ``/api/orders/:order_id/pay``."""
    a, b = segments(template.split("?")[0]), segments(path.split("?")[0])
    if len(a) != len(b):
        return False
    return all(x == y or x.startswith(":") or y.startswith(":") for x, y in zip(a, b, strict=True))


@dataclass
class EntityAction:
    entity: str
    action: str


@dataclass
class EntityIndex:
    entities: dict[str, Entity] = field(default_factory=dict)
    candidates: dict[str, EntityCandidate] = field(default_factory=dict)
    by_route: dict[tuple[str, str], EntityAction] = field(default_factory=dict)  # (METHOD, path)

    def action_for(self, method: str, path: str) -> EntityAction | None:
        for (m, p), ea in self.by_route.items():
            if m == method and paths_match(p, path):
                return ea
        return None


def _entity_for_path(path: str, candidates: dict[str, EntityCandidate]) -> tuple[str, int] | None:
    parts = segments(path)
    for i in range(len(parts) - 1, -1, -1):
        seg = parts[i]
        if seg.startswith(":"):
            continue
        for name, cand in candidates.items():
            if seg in {cand.table, name, name + "s", singular(seg)} and singular(seg) in {
                name,
                singular(cand.table),
            }:
                return name, i
    return None


def action_of(route: RouteCandidate, method: str, rest: list[str]) -> str | None:
    if not rest:
        return {"POST": "create", "GET": "list"}.get(method)
    if len(rest) == 1 and rest[0].startswith(":"):
        return {"GET": "view", "PUT": "update", "PATCH": "update", "DELETE": "delete"}.get(method)
    if len(rest) == 2 and rest[0].startswith(":") and not rest[1].startswith(":"):
        verb = rest[1].replace("-", "_")
        if method == "GET":
            return f"download_{verb}" if route.downloads else None
        return verb
    return None


def build_entities(
    candidates: list[EntityCandidate],
    api_routes: list[tuple[RouteCandidate, RouteInfo]],
    status_labels: dict[str, str],
) -> EntityIndex:
    cands = {c.name: c for c in candidates}
    index = EntityIndex(candidates=cands)
    actions: dict[str, list[str]] = {}
    statuses: dict[str, dict[str, EntityStatus]] = {}
    created_by: dict[str, list[str]] = {}
    for cand in candidates:
        statuses[cand.name] = {
            v: EntityStatus(value=v, label=status_labels.get(v), reachable_by=[], set_by=[])
            for v in cand.statuses
        }
    for route, info in api_routes:
        found = _entity_for_path(route.path, cands)
        if found is None:
            continue
        name, idx = found
        rest = segments(route.path)[idx + 1 :]
        for method in route.methods:
            action = action_of(route, method, rest)
            if action is None:
                continue
            for value in (v for f, v in route.status_sets if f == cands[name].status_field):
                status = statuses[name].get(value)
                if status is None:
                    continue
                status.set_by.append(route.source)
                if info.access == "roles":
                    for role in info.roles:
                        if role not in status.reachable_by:
                            status.reachable_by.append(role)
            if info.access == "excluded":
                continue
            index.by_route[(method, route.path)] = EntityAction(name, action)
            if action not in actions.setdefault(name, []):
                actions[name].append(action)
            if action == "create" and info.access == "roles":
                for role in info.roles:
                    if role not in created_by.setdefault(name, []):
                        created_by[name].append(role)
    for name, acts in actions.items():
        cand = cands[name]
        index.entities[name] = Entity(
            name=name,
            source=cand.source,
            owner_field=cand.owner_field,
            pii_fields=cand.pii_fields,
            actions=acts,
            statuses=list(statuses.get(name, {}).values()),
            status_field=cand.status_field,
            created_by=created_by.get(name, []),
        )
    return index
