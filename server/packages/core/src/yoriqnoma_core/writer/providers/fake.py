"""FakeProvider: deterministic answers for tests (no network, no model).

Answers come from ``<fixtures>/<task>/<hash>.json`` when present, otherwise a minimal
valid object is built from the schema.
"""

from __future__ import annotations

import hashlib
import json
import types
import typing
from pathlib import Path
from typing import Any, Union, get_args, get_origin

from pydantic import BaseModel

from yoriqnoma_core.writer.providers.base import LLMRequest, LLMResult, T


def request_hash(req: LLMRequest) -> str:
    return hashlib.sha256(f"{req.task}\n{req.system}\n{req.prompt}".encode()).hexdigest()[:16]


def sample_value(annotation: Any, name: str) -> Any:
    origin = get_origin(annotation)
    if origin in (Union, types.UnionType):
        args = [a for a in get_args(annotation) if a is not type(None)]
        return sample_value(args[0], name) if args else None
    if origin in (list, typing.List):  # noqa: UP006
        return []
    if origin in (dict, typing.Dict):  # noqa: UP006
        return {}
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return sample(annotation)
    if annotation is bool:
        return False
    if annotation is int:
        return 0
    if annotation is float:
        return 0.0
    return f"{name.replace('_', ' ').capitalize()} (namuna matn)."


def sample(schema: type[BaseModel]) -> dict[str, Any]:
    return {
        name: sample_value(field.annotation, name)
        for name, field in schema.model_fields.items()
        if field.is_required() or True
    }


class FakeProvider:
    name = "fake"

    def __init__(self, fixtures: Path | None = None, model: str = "fake-model") -> None:
        self.fixtures = fixtures
        self.model = model
        self.calls: list[LLMRequest] = []

    def capabilities(self) -> set[str]:
        return {"vision", "json_schema"}

    async def generate(self, req: LLMRequest, schema: type[T]) -> LLMResult[T]:
        self.calls.append(req)
        if self.fixtures is not None:
            path = self.fixtures / req.task / f"{request_hash(req)}.json"
            if path.is_file():
                return LLMResult(schema.model_validate_json(path.read_text("utf-8")), self.model)
            default = self.fixtures / req.task / "default.json"
            if default.is_file():
                return LLMResult(
                    schema.model_validate(json.loads(default.read_text("utf-8"))), self.model
                )
        return LLMResult(schema.model_validate(sample(schema)), self.model)
