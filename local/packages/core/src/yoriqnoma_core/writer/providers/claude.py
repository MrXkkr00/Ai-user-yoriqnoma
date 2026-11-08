"""ClaudeProvider (TZ FR-W1, FR-SV6, SEC-7, SEC-12): the server's writer, Anthropic SDK.

``messages.parse(..., output_format=Schema)`` returns a validated answer
(``parsed_output``); the system prompt is cached (``cache_control``). Models by task:
classification -> Haiku, descriptions -> Sonnet, the final review -> Opus. Every call is
priced from ``usage`` (cache reads and writes apart) and checked against the job budget.

Before anything is sent, the prompt text is checked for personal data that is neither a
test value nor a public one (masked and reported), and every image must come from the
run's own folder (images there went through the replacement of other people's data).

The API key is given to the constructor only: never read from Django settings or the
environment here, never shown in ``repr``, logs or error messages. The ``anthropic``
package is the optional ``yoriqnoma-core[claude]`` extra (the local app does not need it).
"""

from __future__ import annotations

import base64
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import SecretStr, ValidationError

from yoriqnoma_core.safety.pii import find_pii, mask_text
from yoriqnoma_core.writer.providers.base import (
    LLMRequest,
    LLMResult,
    ProviderError,
    SchemaError,
    T,
)

DEFAULT_MODELS = {
    "classify": "claude-haiku-5-5",
    "final_review": "claude-opus-5-5",
    "*": "claude-sonnet-5-5",  # describe_*, section_intro, faq, reference, agent steps
}
KEY_PATTERN = re.compile(r"sk-ant-[A-Za-z0-9_\-]+")
MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


@dataclass(frozen=True)
class Prices:
    """US dollars per million tokens."""

    input: float
    output: float
    cache_read: float
    cache_write: float


DEFAULT_PRICES = {
    "claude-opus-5-5": Prices(4.0, 20.0, 0.40, 5.0),
    "claude-sonnet-5-5": Prices(2.0, 10.0, 0.20, 2.5),
    "claude-haiku-5-5": Prices(0.10, 0.50, 0.01, 0.125),
}


class BudgetExceeded(ProviderError):
    """The job's Claude budget is spent: no further calls are made."""


Sanitizer = Callable[[str], tuple[str, int]]
CostHook = Callable[[dict[str, Any]], None]


def make_sanitizer(ignore: set[str]) -> Sanitizer:
    """Mask personal values that are neither test values nor public ones (TZ SEC-7)."""

    def sanitize(text: str) -> tuple[str, int]:
        found = find_pii(text, ignore)
        return (mask_text(text, found), len(found)) if found else (text, 0)

    return sanitize


def prices_from(raw: dict[str, Any] | None) -> dict[str, Prices]:
    """``{"model": {"input": 2, "output": 10, "cache_read": 0.2, "cache_write": 2.5}}``."""
    out = dict(DEFAULT_PRICES)
    for model, p in (raw or {}).items():
        out[model] = Prices(
            float(p["input"]), float(p["output"]), float(p["cache_read"]), float(p["cache_write"])
        )
    return out


class ClaudeProvider:
    name = "claude"

    def __init__(
        self,
        api_key: str | SecretStr,
        models: dict[str, str] | None = None,
        prices: dict[str, Prices] | None = None,
        budget_usd: float | None = None,
        on_cost: CostHook | None = None,
        sanitize: Sanitizer | None = None,
        image_roots: list[Path] | None = None,
        client: Any = None,
        retries: int = 2,
        max_retries: int = 4,
        timeout_s: float = 180.0,
    ) -> None:
        self._key = api_key if isinstance(api_key, SecretStr) else SecretStr(api_key)
        if not self._key.get_secret_value() and client is None:
            raise ProviderError("Claude API kaliti berilmagan (ANTHROPIC_API_KEY)")
        self.models = {**DEFAULT_MODELS, **(models or {})}
        self.model = self.models["*"]
        self.prices = prices or dict(DEFAULT_PRICES)
        self.budget_usd = budget_usd
        self.on_cost = on_cost
        self.sanitize = sanitize
        self.image_roots = [p.resolve() for p in image_roots or []]
        self.retries = retries
        self.max_retries = max_retries
        self.timeout_s = timeout_s
        self._client = client
        self.spent_usd = 0.0
        self.tokens_in = 0
        self.tokens_out = 0
        self.masked_values = 0

    def __repr__(self) -> str:  # never the key
        return f"ClaudeProvider(model={self.model!r}, spent_usd={self.spent_usd:.4f})"

    __str__ = __repr__

    def capabilities(self) -> set[str]:
        return {"vision", "json_schema", "prompt_cache", "final_review"}

    def model_for(self, task: str) -> str:
        return self.models.get(task) or self.models["*"]

    def client(self) -> Any:
        if self._client is None:
            # optional extra yoriqnoma-core[claude]: installed on the server, not locally
            from anthropic import AsyncAnthropic  # type: ignore[import-not-found, unused-ignore]

            self._client = AsyncAnthropic(
                api_key=self._key.get_secret_value(),
                max_retries=self.max_retries,  # the SDK backs off on 429 / 5xx itself
                timeout=self.timeout_s,
            )
        return self._client

    # --- money ------------------------------------------------------------------------

    def cost(self, model: str, usage: Any) -> float:
        price = self.prices.get(model)
        if price is None:
            return 0.0
        fresh = int(getattr(usage, "input_tokens", 0) or 0)
        out = int(getattr(usage, "output_tokens", 0) or 0)
        read = int(getattr(usage, "cache_read_input_tokens", 0) or 0)
        write = int(getattr(usage, "cache_creation_input_tokens", 0) or 0)
        total = (
            fresh * price.input
            + out * price.output
            + read * price.cache_read
            + write * price.cache_write
        )
        return round(total / 1_000_000, 6)

    def _check_budget(self) -> None:
        if self.budget_usd is not None and self.spent_usd >= self.budget_usd:
            raise BudgetExceeded(
                f"ish byudjeti tugadi: ${self.spent_usd:.2f} / ${self.budget_usd:.2f}"
            )

    # --- request ----------------------------------------------------------------------

    def _safe(self, text: str) -> str:
        """Error text without the key (SEC-12)."""
        key = self._key.get_secret_value()
        if key:
            text = text.replace(key, "***")
        return KEY_PATTERN.sub("sk-ant-***", text)

    def _image_block(self, path: Path) -> dict[str, Any]:
        resolved = path.resolve()
        if self.image_roots and not any(resolved.is_relative_to(r) for r in self.image_roots):
            # only the run's own images went through the replacement of others' data
            raise ProviderError(f"rasm ish papkasidan tashqarida, yuborilmadi: {path.name}")
        media = MEDIA_TYPES.get(path.suffix.lower())
        if media is None:
            raise ProviderError(f"rasm turi qo'llab-quvvatlanmaydi: {path.suffix}")
        data = base64.standard_b64encode(path.read_bytes()).decode("ascii")
        return {"type": "image", "source": {"type": "base64", "media_type": media, "data": data}}

    def _content(self, req: LLMRequest) -> list[dict[str, Any]]:
        prompt = req.prompt
        if self.sanitize is not None:
            prompt, masked = self.sanitize(prompt)
            if masked:
                self.masked_values += masked
                if self.on_cost is not None:
                    self.on_cost({"kind": "pii_masked", "task": req.task, "count": masked})
        content: list[dict[str, Any]] = [self._image_block(p) for p in req.images]
        if req.cacheable_prefix:
            content.append(
                {
                    "type": "text",
                    "text": req.cacheable_prefix,
                    "cache_control": {"type": "ephemeral"},
                }
            )
        content.append({"type": "text", "text": prompt})
        return content

    async def generate(self, req: LLMRequest, schema: type[T]) -> LLMResult[T]:
        self._check_budget()
        model = self.model_for(req.task)
        system = [{"type": "text", "text": req.system, "cache_control": {"type": "ephemeral"}}]
        messages: list[dict[str, Any]] = [{"role": "user", "content": self._content(req)}]
        started = time.monotonic()
        tokens_in = tokens_out = 0
        cost_total = 0.0
        last_error = ""
        for _attempt in range(self.retries + 1):
            self._check_budget()
            try:
                resp = await self.client().messages.parse(
                    model=model,
                    max_tokens=req.max_tokens,
                    system=system,
                    messages=messages,
                    output_format=schema,
                )
            except ValidationError as exc:  # the JSON did not match the schema
                last_error = str(exc).splitlines()[0]
                messages = [
                    messages[0],
                    {"role": "assistant", "content": "(javob sxemaga mos kelmadi)"},
                    {"role": "user", "content": self._retry_note(last_error)},
                ]
                continue
            except Exception as exc:  # noqa: BLE001 - SDK errors: re-raised without the key
                raise ProviderError(f"Claude: {self._safe(str(exc))[:300]}") from None
            usage = getattr(resp, "usage", None)
            cost = self.cost(model, usage)
            cost_total += cost
            self.spent_usd = round(self.spent_usd + cost, 6)
            used_in = int(getattr(usage, "input_tokens", 0) or 0)
            used_out = int(getattr(usage, "output_tokens", 0) or 0)
            tokens_in += used_in
            tokens_out += used_out
            self.tokens_in += used_in
            self.tokens_out += used_out
            if self.on_cost is not None:
                self.on_cost(
                    {
                        "kind": "cost",
                        "task": req.task,
                        "model": model,
                        "cost_usd": cost,
                        "spent_usd": self.spent_usd,
                        "input_tokens": used_in,
                        "output_tokens": used_out,
                        "cache_read": int(getattr(usage, "cache_read_input_tokens", 0) or 0),
                        "cache_write": int(getattr(usage, "cache_creation_input_tokens", 0) or 0),
                    }
                )
            parsed = getattr(resp, "parsed_output", None)
            if isinstance(parsed, schema):
                return LLMResult(
                    data=parsed,
                    model=model,
                    input_tokens=tokens_in,
                    output_tokens=tokens_out,
                    cost_usd=round(cost_total, 6),
                    latency_s=round(time.monotonic() - started, 2),
                )
            reason = getattr(resp, "stop_reason", None)
            last_error = f"javob yo'q (stop_reason={reason})"
            if reason == "refusal":
                break
        raise SchemaError(f"{req.task}: javob sxemaga mos kelmadi ({last_error})")

    @staticmethod
    def _retry_note(error: str) -> str:
        return f"Javob sxemaga mos emas: {error}. Faqat sxema bo'yicha to'g'ri JSON qaytaring."
