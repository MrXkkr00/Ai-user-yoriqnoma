"""Manual: the structured user manual (ARCHITECTURE §3.5)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from yoriqnoma_schemas.common import SCHEMA_VERSION, RoleId, SchemaVersion, Stage, StrictModel

SectionStage = Stage | Literal["reference", "faq", "unverified"]
SourceMode = Literal["A", "A'", "B", "A+B", "local"]


class StepText(StrictModel):
    n: int
    text: str
    image: str | None = None  # path relative to capture/ (state image) or dist images
    markers: list[int] = Field(default_factory=list)
    state_id: str | None = None


class StatusRow(StrictModel):
    status: str
    meaning: str
    what_you_can_do: str
    patched_image: bool = False
    image: str | None = None


class Article(StrictModel):
    flow_id: str
    title: str
    purpose: str
    steps: list[StepText] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    statuses: list[StatusRow] = Field(default_factory=list)
    needs_review: bool = False


class Section(StrictModel):
    id: str
    stage: SectionStage
    title: str
    intro: str
    articles: list[Article] = Field(default_factory=list)
    empty_reason: str | None = None  # the site has no such feature


class RefEntry(StrictModel):
    page_title: str
    path: str
    purpose: str
    elements: list[str] = Field(default_factory=list)


class QA(StrictModel):
    q: str
    a: str


class CoverageItem(StrictModel):
    kind: str  # route | form | button | action | status | section
    key: str
    covered: bool
    reason: str | None = None


class Coverage(StrictModel):
    percent: dict[str, float] = Field(default_factory=dict)
    items: list[CoverageItem] = Field(default_factory=list)


class Manual(StrictModel):
    schema_version: SchemaVersion = SCHEMA_VERSION
    project: str
    language: str = "uz"
    role: RoleId
    role_label: str
    role_granted_by: str = ""  # who gives this role ("sayt administratori", "o'zingiz")
    generated_at: datetime
    source_mode: SourceMode
    models: list[str] = Field(default_factory=list)
    sections: list[Section]
    reference: list[RefEntry] = Field(default_factory=list)
    faq: list[QA] = Field(default_factory=list)
    coverage: Coverage = Field(default_factory=Coverage)
