"""LLM provider interface (ARCHITECTURE §4.1, CLAUDE.md rule 7)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Generic, Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class ProviderError(Exception):
    """The provider could not answer (not running, model missing, network)."""


class SchemaError(ProviderError):
    """The answer did not match the JSON schema even after retries."""


@dataclass(frozen=True)
class LLMRequest:
    task: str  # describe_flow, describe_statuses, section_intro, faq, reference
    system: str
    prompt: str
    images: list[Path] = field(default_factory=list)
    max_tokens: int = 2048
    temperature: float = 0.0
    cacheable_prefix: str | None = None


@dataclass
class LLMResult(Generic[T]):  # noqa: UP046 - T is shared with provider modules
    data: T
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float | None = None
    latency_s: float = 0.0
    cached: bool = False


class LLMProvider(Protocol):
    name: str
    model: str

    def capabilities(self) -> set[str]: ...

    async def generate(self, req: LLMRequest, schema: type[T]) -> LLMResult[T]: ...
