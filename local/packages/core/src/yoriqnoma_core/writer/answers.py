"""JSON shapes the LLM answers in (TZ FR-W3): one schema per writer task."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class _Answer(BaseModel):
    model_config = ConfigDict(extra="ignore")


class FlowDescription(_Answer):
    purpose: str = Field(description="1-2 gap: bu vazifa nima uchun kerak")
    notes: list[str] = Field(default_factory=list, description="0-3 ta qisqa eslatma")


class StatusMeaning(_Answer):
    status: str
    meaning: str
    what_you_can_do: str


class StatusDescriptions(_Answer):
    rows: list[StatusMeaning] = Field(default_factory=list)


class SectionIntro(_Answer):
    intro: str


class QAItem(_Answer):
    q: str
    a: str


class FAQAnswer(_Answer):
    items: list[QAItem] = Field(default_factory=list)


class PagePurpose(_Answer):
    path: str
    purpose: str


class ReferenceAnswer(_Answer):
    pages: list[PagePurpose] = Field(default_factory=list)
