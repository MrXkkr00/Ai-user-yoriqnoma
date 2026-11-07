"""Capture: what the explorer saw (ARCHITECTURE §3.4)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Self

from pydantic import Field, HttpUrl, model_validator

from yoriqnoma_schemas.common import BBox, Environment, RoleId, StrictModel, Target

AccountAlias = Literal["A", "B", "guest"]
ElementKind = Literal["button", "link", "input", "select", "tab", "menu", "other"]


class Element(StrictModel):
    marker: int
    role: str
    name: str
    bbox: BBox
    selector: Target
    kind: ElementKind
    enabled: bool = True


class NetCall(StrictModel):
    method: str
    path_template: str
    status: int


class HiddenArea(BBox):
    """A blurred area (TZ FR-E10): not the role's, or a value that could not be replaced."""

    reason: str = ""


class State(StrictModel):
    id: str
    hash: str
    url: str
    title: str
    flow_id: str | None = None
    step_index: int | None = None
    account: AccountAlias
    images: dict[Literal["clean", "som"], str]  # paths relative to capture/
    elements: list[Element] = Field(default_factory=list)
    aria: str = ""
    entity: str | None = None
    entity_status: str | None = None
    patched: bool = False
    network: list[NetCall] = Field(default_factory=list)
    hidden: list[HiddenArea] = Field(default_factory=list)
    substituted: int = 0  # other people's values replaced with fakes (values never stored)
    kept_public: int = 0  # found, but kept: organization or published content
    privacy: dict[str, int] = Field(default_factory=dict)  # "zone:decision" -> count
    parent_id: str | None = None  # state graph: state this one was reached from
    trigger: str | None = None  # state graph: element that was clicked
    viewport: tuple[int, int] = (1280, 800)


class FlowResult(StrictModel):
    flow_id: str
    status: Literal["verified", "failed", "skipped"]
    reason: str | None = None
    state_ids: list[str] = Field(default_factory=list)
    duration_s: float = 0.0
    role: RoleId | None = None
    helper: bool = False  # run only to prepare objects for the target role
    stopped_at_confirm: bool = False  # production: stopped at the confirmation step


class BlockedRequest(StrictModel):
    method: str
    url: str
    rule: str
    at: datetime


class CaptureRun(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    run_id: str
    blueprint_hash: str
    role: RoleId  # the target role
    role_label: str = ""
    project: str = ""
    base_url: HttpUrl
    environment: Environment
    started_at: datetime
    finished_at: datetime | None = None
    flows: list[FlowResult] = Field(default_factory=list)
    states: list[State] = Field(default_factory=list)
    firewall_log: list[BlockedRequest] = Field(default_factory=list)
    own_objects: dict[str, list[str]] = Field(default_factory=dict)  # entity -> ids
    test_values: list[str] = Field(default_factory=list)  # every value datagen produced
    public_values: list[str] = Field(default_factory=list)  # kept org / published values
    privilege_ok: bool | None = None  # SEC-6 probe result: yes / no only
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _state_refs(self) -> Self:
        ids = {s.id for s in self.states}
        if len(ids) != len(self.states):
            raise ValueError("duplicate state ids")
        for fr in self.flows:
            missing = [sid for sid in fr.state_ids if sid not in ids]
            if missing:
                raise ValueError(f"flow {fr.flow_id} points to unknown states: {missing}")
        return self

    def state_by_id(self, state_id: str) -> State | None:
        return next((s for s in self.states if s.id == state_id), None)

    def flow_result(self, flow_id: str) -> FlowResult | None:
        return next((f for f in self.flows if f.flow_id == flow_id), None)
