"""Shared types of every schema (ARCHITECTURE §3.1) and JSON helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, model_validator

SCHEMA_VERSION: Literal["1.0"] = "1.0"

RoleId = str  # "guest" is the anonymous visitor; others are the site's own role ids
RoleKind = Literal["guest", "role", "excluded"]  # TZ FR-RL2
Access = Literal["guest", "roles", "excluded", "unknown"]
Stage = Literal["start", "core", "manage", "social", "payment", "settings", "exit"]
STAGES: tuple[Stage, ...] = ("start", "core", "manage", "social", "payment", "settings", "exit")
Environment = Literal["staging", "production"]
Source = Literal["code", "discovered", "merged"]
GUEST: RoleId = "guest"


class StrictModel(BaseModel):
    """Base of every schema model: unknown fields are an error."""

    model_config = ConfigDict(extra="forbid")


class Target(StrictModel):
    """How to find an element. At least one field is set; priority follows field order."""

    role: str | None = None  # "button", "textbox", "link", ...
    name: str | None = None  # accessible name
    label: str | None = None
    testid: str | None = None
    css: str | None = None  # last resort

    @model_validator(mode="after")
    def _not_empty(self) -> Self:
        if not any((self.role, self.name, self.label, self.testid, self.css)):
            raise ValueError("Target needs at least one of role, name, label, testid, css")
        return self

    def describe(self) -> str:
        """Short human-readable form for logs and reports."""
        if self.role and self.name:
            return f"{self.role} «{self.name}»"
        if self.label:
            return f"label «{self.label}»"
        if self.testid:
            return f"testid {self.testid}"
        if self.name:
            return f"«{self.name}»"
        if self.css:
            return f"css {self.css}"
        return str(self.role)


class BBox(StrictModel):
    x: float
    y: float
    w: float
    h: float

    def intersects(self, other: BBox) -> bool:
        return not (
            self.x + self.w <= other.x
            or other.x + other.w <= self.x
            or self.y + self.h <= other.y
            or other.y + other.h <= self.y
        )


def load_json[M: BaseModel](path: Path | str, model: type[M]) -> M:
    """Read a UTF-8 JSON file and validate it against ``model``."""
    return model.model_validate_json(Path(path).read_text(encoding="utf-8"))


def dump_json(obj: BaseModel) -> str:
    """Serialise a model as readable UTF-8 JSON (indent 2, non-ASCII kept)."""
    data = obj.model_dump(mode="json")
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def save_json(path: Path | str, obj: BaseModel) -> Path:
    """Write ``obj`` to ``path`` (parents created) and return the path."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(dump_json(obj), encoding="utf-8")
    return target
