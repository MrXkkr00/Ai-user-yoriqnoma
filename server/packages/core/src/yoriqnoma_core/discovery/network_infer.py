"""Entities and actions from the site's own API calls (ARCHITECTURE §7.6).

Input: what the browser saw — method, path, status and the NAMES of the JSON keys of the
answers. Values are never kept (only key names), so no personal data is stored here.
``/api/orders`` + POST -> entity ``order`` with ``create``; ``/api/orders/:id/cancel``
+ POST -> ``cancel``. Key names that may hold someone's data become ``pii_fields``.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from yoriqnoma_core.discovery.urls import template_path
from yoriqnoma_core.safety.pii import is_pii_field
from yoriqnoma_schemas import Entity

SKIP_RESOURCES = {"auth", "session", "sessions", "login", "logout", "me", "csrf", "token", "health"}
STATUS_KEYS = ("status", "state", "holat")


@dataclass
class ApiCall:
    method: str
    path: str
    status: int
    keys: list[str] = field(default_factory=list)  # JSON key names of the answer only


def singular(word: str) -> str:
    if word.endswith("ies"):
        return word[:-3] + "y"
    if word.endswith("ses"):
        return word[:-2]
    if word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def _segments(path: str) -> list[str]:
    parts = [p for p in template_path(path).split("/") if p]
    if parts and parts[0] == "api":
        parts = parts[1:]
    if parts and len(parts[0]) <= 3 and parts[0].startswith("v") and parts[0][1:].isdigit():
        parts = parts[1:]
    return parts


def infer_entities(calls: list[ApiCall], confidence: float = 0.6) -> list[Entity]:
    actions: dict[str, set[str]] = defaultdict(set)
    keys: dict[str, set[str]] = defaultdict(set)
    sources: dict[str, str] = {}
    for call in calls:
        if call.status >= 400:
            continue
        parts = _segments(call.path)
        if not parts or parts[0] in SKIP_RESOURCES or not parts[0].isidentifier():
            continue
        name = singular(parts[0].lower())
        rest = parts[1:]
        method = call.method.upper()
        sources.setdefault(name, f"network: {method} {template_path(call.path)}")
        if not rest:
            actions[name].add({"GET": "list", "POST": "create"}.get(method, method.lower()))
        elif rest[0] in {":id", ":slug"}:
            if len(rest) == 1:
                verb = {"GET": "view", "PUT": "update", "PATCH": "update", "DELETE": "delete"}
                actions[name].add(verb.get(method, method.lower()))
            elif rest[1].isidentifier() and not rest[1].startswith(":"):
                if method == "GET" and len(rest) == 2:
                    actions[name].add(f"view_{rest[1]}")
                else:
                    actions[name].add(rest[1])
        keys[name].update(call.keys)
    out = []
    for name in sorted(actions):
        names = keys[name]
        status_field = next((k for k in STATUS_KEYS if k in names), None)
        owner = next(
            (k for k in ("user_id", "owner_id", "author_id", "customer_id") if k in names), None
        )
        out.append(
            Entity(
                name=name,
                source=sources[name],
                owner_field=owner,
                pii_fields=sorted(k for k in names if is_pii_field(k)),
                actions=sorted(actions[name]),
                status_field=status_field,
                confidence=confidence,
            )
        )
    return out


def json_key_names(data: object, limit: int = 300) -> list[str]:
    """Key names anywhere in a JSON answer (values are dropped at once)."""
    seen: list[str] = []

    def walk(node: object, depth: int) -> None:
        if depth > 6 or len(seen) >= limit:
            return
        if isinstance(node, dict):
            for key, value in node.items():
                if isinstance(key, str) and key not in seen:
                    seen.append(key)
                walk(value, depth + 1)
        elif isinstance(node, list):
            for item in node[:5]:
                walk(item, depth + 1)

    walk(data, 0)
    return seen
