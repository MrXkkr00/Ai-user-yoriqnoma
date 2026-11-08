"""Blueprint: the map of a site's user features (ARCHITECTURE §3.3)."""

from __future__ import annotations

import hashlib
import heapq
import json
from datetime import datetime
from typing import Literal, Self

from pydantic import Field, HttpUrl, model_validator

from yoriqnoma_schemas.common import (
    SCHEMA_VERSION,
    Access,
    RoleId,
    RoleKind,
    SchemaVersion,
    Source,
    Stage,
    StrictModel,
    Target,
)
from yoriqnoma_schemas.policy import Policy


class RoleInfo(StrictModel):
    id: RoleId  # "manager"
    label: str  # "Menejer"
    kind: RoleKind
    reason: str  # why role / excluded
    source: str  # where it was found
    self_signup: bool = False  # the tool can register an account itself (FR-RL4)
    description: str | None = None  # short text for the option card


class RouteInfo(StrictModel):
    path: str
    kind: Literal["page", "api"]
    methods: list[str] = Field(default_factory=list)
    access: Access
    roles: list[RoleId] = Field(default_factory=list)
    reason: str
    source: str  # "app/api/orders.py:42"


class FormField(StrictModel):
    name: str
    label: str | None = None
    type: str = "text"  # text|email|password|tel|number|select|file|textarea|checkbox|...
    required: bool = False
    rules: str | None = None  # "min:8|max:64|regex:..."
    options: list[str] | None = None


class Form(StrictModel):
    id: str
    page_path: str
    fields: list[FormField]
    submit: Target
    api: str | None = None  # "POST /api/orders"


class EntityStatus(StrictModel):
    value: str
    label: str | None = None
    reachable_by: list[RoleId] = Field(default_factory=list)
    set_by: list[str] = Field(default_factory=list)  # route sources


class Entity(StrictModel):
    name: str
    source: str
    owner_field: str | None = None
    pii_fields: list[str] = Field(default_factory=list)  # may hold other people's data
    actions: list[str] = Field(default_factory=list)  # create, view, list, cancel, pay, ...
    statuses: list[EntityStatus] = Field(default_factory=list)
    status_field: str | None = None  # name of the status field in API responses
    created_by: list[RoleId] = Field(default_factory=list)  # roles that can create it
    confidence: float = 1.0


StepAction = Literal[
    "goto",
    "click",
    "fill",
    "select",
    "check",
    "upload",
    "expect_url",
    "expect_text",
    "expect_visible",
    "verify_email",
    "wait_for",
    "human_input",
]


class Step(StrictModel):
    action: StepAction
    target: Target | None = None
    path: str | None = None  # goto/expect_url; may contain "{own:order_id}"
    # "fake:full_name" | "fake:first_name" | "fake:last_name" | "fake:username" |
    # "fake:email" | "fake:phone_uz" | "fake:password" | "fake:text" | "fake:number" |
    # "fake:option" | "fake:address" | "fake:date" | "peer:email" | "literal:..." |
    # "own:<entity>_id" | "file:<name>"
    data: str | None = None
    text: str | None = None
    rules: str | None = None
    confirm: bool = False  # confirmation button (production stops here)
    destructive: bool = False
    payment: bool = False

    @model_validator(mode="after")
    def _needs(self) -> Self:
        needs_target = {"click", "fill", "select", "check", "upload", "expect_visible"}
        if self.action in needs_target and self.target is None:
            raise ValueError(f"step {self.action!r} needs a target")
        if self.action in {"goto", "expect_url"} and not self.path:
            raise ValueError(f"step {self.action!r} needs a path")
        if self.action in {"fill", "select"} and self.data is None:
            raise ValueError(f"step {self.action!r} needs data")
        return self


class Flow(StrictModel):
    id: str
    title: str
    stage: Stage
    role: RoleId  # only roles of kind "guest" or "role"
    entity: str | None = None
    action: str | None = None
    requires: list[str] = Field(default_factory=list)
    account: Literal["A", "B"] = "A"
    source: str
    status: Literal["unverified", "verified", "failed", "skipped"] = "unverified"
    confidence: float = 1.0
    creates: str | None = None  # entity whose new id this flow records as an own object
    sets_status: str | None = None  # status the entity object has after this flow
    needs_status: list[str] = Field(default_factory=list)  # object must be in one of these
    steps: list[Step]


class Blueprint(StrictModel):
    schema_version: SchemaVersion = SCHEMA_VERSION
    project: str
    base_url: HttpUrl
    source: Source
    generated_at: datetime
    generator: str
    language: str = "uz"
    policy: Policy
    roles: list[RoleInfo]  # every role found, excluded ones too (with reasons)
    pages: list[RouteInfo] = Field(default_factory=list)
    forms: list[Form] = Field(default_factory=list)
    entities: list[Entity] = Field(default_factory=list)
    flows: list[Flow] = Field(default_factory=list)
    nav: list[dict[str, str]] = Field(default_factory=list)  # {label, path}
    i18n: dict[str, str] = Field(default_factory=dict)
    excluded: list[RouteInfo] = Field(default_factory=list)

    # --- validation ---------------------------------------------------------------

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        role_ids = [r.id for r in self.roles]
        if len(set(role_ids)) != len(role_ids):
            raise ValueError(f"duplicate role ids: {role_ids}")
        kinds = {r.id: r.kind for r in self.roles}
        usable = {rid for rid, kind in kinds.items() if kind != "excluded"}

        for page in self.pages:
            if page.access == "excluded":
                raise ValueError(f"pages must not contain excluded routes: {page.path}")
            for rid in page.roles:
                if rid not in usable:
                    raise ValueError(f"route {page.path} names unknown or excluded role {rid!r}")
        for route in self.excluded:
            if route.access != "excluded":
                raise ValueError(f"excluded holds a non-excluded route: {route.path}")

        flow_ids = [f.id for f in self.flows]
        if len(set(flow_ids)) != len(flow_ids):
            dupes = sorted({f for f in flow_ids if flow_ids.count(f) > 1})
            raise ValueError(f"duplicate flow ids: {dupes}")
        known = set(flow_ids)
        for flow in self.flows:
            if flow.role not in usable:
                raise ValueError(f"flow {flow.id} uses unknown or excluded role {flow.role!r}")
            missing = [r for r in flow.requires if r not in known]
            if missing:
                raise ValueError(f"flow {flow.id} requires unknown flows: {missing}")
        cycle = _find_cycle({f.id: f.requires for f in self.flows})
        if cycle:
            raise ValueError("flow requires graph has a cycle: " + " -> ".join(cycle))
        return self

    # --- helpers ------------------------------------------------------------------

    def role(self, role_id: RoleId) -> RoleInfo | None:
        return next((r for r in self.roles if r.id == role_id), None)

    def flow(self, flow_id: str) -> Flow | None:
        return next((f for f in self.flows if f.id == flow_id), None)

    def entity(self, name: str) -> Entity | None:
        return next((e for e in self.entities if e.name == name), None)

    def selectable_roles(self) -> list[RoleInfo]:
        """Roles a manual can be written for: kind "role" (guest is part of every manual)."""
        return [r for r in self.roles if r.kind == "role"]

    def topo_order(self, flows: list[Flow] | None = None) -> list[Flow]:
        """Flows ordered so that every flow comes after the flows it requires.

        Ties keep the blueprint order, so the result is deterministic.
        """
        chosen = self.flows if flows is None else flows
        ids = {f.id for f in chosen}
        index = {f.id: i for i, f in enumerate(chosen)}
        by_id = {f.id: f for f in chosen}
        indegree = {f.id: sum(1 for r in f.requires if r in ids) for f in chosen}
        dependants: dict[str, list[str]] = {f.id: [] for f in chosen}
        for f in chosen:
            for r in f.requires:
                if r in ids:
                    dependants[r].append(f.id)
        ready = [(index[fid], fid) for fid, deg in indegree.items() if deg == 0]
        heapq.heapify(ready)
        out: list[Flow] = []
        while ready:
            _, fid = heapq.heappop(ready)
            out.append(by_id[fid])
            for dep in dependants[fid]:
                indegree[dep] -= 1
                if indegree[dep] == 0:
                    heapq.heappush(ready, (index[dep], dep))
        if len(out) != len(chosen):
            raise ValueError("flow requires graph has a cycle")
        return out

    def requirement_closure(self, flow_ids: list[str]) -> list[Flow]:
        """The given flows plus everything they require, in topological order."""
        seen: set[str] = set()
        stack = list(flow_ids)
        while stack:
            fid = stack.pop()
            if fid in seen:
                continue
            seen.add(fid)
            flow = self.flow(fid)
            if flow is not None:
                stack.extend(flow.requires)
        return self.topo_order([f for f in self.flows if f.id in seen])

    def flows_for_role(self, role_id: RoleId) -> list[Flow]:
        """Flows written into a manual for ``role_id``: its own flows and guest flows."""
        return [f for f in self.flows if f.role in (role_id, "guest")]

    def content_hash(self) -> str:
        """sha256 of the canonical content, ignoring generation time and generator."""
        data = self.model_dump(mode="json", exclude={"generated_at", "generator"})
        raw = json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _find_cycle(graph: dict[str, list[str]]) -> list[str] | None:
    """Return one cycle as a path (first node repeated at the end), or None."""
    white, grey, black = 0, 1, 2
    color = dict.fromkeys(graph, white)
    parent: dict[str, str] = {}

    for start in graph:
        if color[start] != white:
            continue
        stack: list[tuple[str, int]] = [(start, 0)]
        color[start] = grey
        while stack:
            node, i = stack[-1]
            edges = [e for e in graph.get(node, []) if e in graph]
            if i < len(edges):
                stack[-1] = (node, i + 1)
                nxt = edges[i]
                if color[nxt] == white:
                    color[nxt] = grey
                    parent[nxt] = node
                    stack.append((nxt, 0))
                elif color[nxt] == grey:
                    path = [node]
                    while path[-1] != nxt:
                        path.append(parent[path[-1]])
                    path.reverse()
                    return [*path, nxt]
            else:
                color[node] = black
                stack.pop()
    return None
