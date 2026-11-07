"""Network firewall and API-answer rewriting for one browser context (TZ SEC-4, FR-E10).

Every request of the page passes ``PolicyEngine.allows_request``; blocked requests are
aborted and logged. Same-origin JSON answers are rewritten by the privacy ledger (other
people's data -> fakes) and by status patches (FR-E8) before the page sees them.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from playwright.async_api import Request, Route

from yoriqnoma_core.explorer.pseudonymize import PrivacyLedger
from yoriqnoma_core.safety.policy_engine import PolicyEngine, RequestContext
from yoriqnoma_core.safety.url_guard import same_origin
from yoriqnoma_schemas import BlockedRequest


@dataclass
class StatusPatch:
    entity: str
    object_id: str
    field: str
    value: str


@dataclass
class Firewall:
    engine: PolicyEngine
    ledger: PrivacyLedger
    collections: set[str]
    log: list[BlockedRequest] = field(default_factory=list)
    patches: list[StatusPatch] = field(default_factory=list)
    probe: bool = False
    on_block: Callable[[BlockedRequest], None] | None = None

    def own_ids(self) -> set[str]:
        return {i for ids in self.ledger.own_ids.values() for i in ids}

    async def handle(self, route: Route, request: Request) -> None:
        ctx = RequestContext(own_ids=self.own_ids(), collections=self.collections, probe=self.probe)
        allowed, rule = self.engine.allows_request(
            request.method, request.url, request.resource_type, ctx
        )
        if not allowed:
            parts = urlsplit(request.url)
            blocked = BlockedRequest(
                method=request.method,
                url=f"{parts.scheme}://{parts.netloc}{parts.path}",
                rule=rule,
                at=datetime.now(UTC),
            )
            self.log.append(blocked)
            if self.on_block:
                self.on_block(blocked)
            await route.abort("blockedbyclient")
            return
        if (
            not self.probe
            and request.method == "GET"
            and request.resource_type in {"fetch", "xhr"}
            and same_origin(request.url, self.engine.base_url)
        ):
            try:
                response = await route.fetch()
            except Exception:  # noqa: BLE001 - network errors: let the page see them
                await route.continue_()
                return
            if "json" in response.headers.get("content-type", ""):
                try:
                    data = await response.json()
                except (ValueError, json.JSONDecodeError):
                    await route.fulfill(response=response)
                    return
                path = urlsplit(request.url).path
                data = self.ledger.transform_json(data, path)
                data = self._patch(data, path)
                await route.fulfill(response=response, json=data)
                return
            await route.fulfill(response=response)
            return
        await route.continue_()

    def _patch(self, data: Any, path: str) -> Any:
        if not self.patches:
            return data
        entity = self.ledger.entity_for_path(path)

        def walk(node: Any) -> Any:
            if isinstance(node, list):
                return [walk(n) for n in node]
            if isinstance(node, dict):
                out = {k: walk(v) for k, v in node.items()}
                for p in self.patches:
                    if p.entity == entity and str(out.get("id")) == p.object_id and p.field in out:
                        out[p.field] = p.value
                return out
            return node

        return walk(data)
