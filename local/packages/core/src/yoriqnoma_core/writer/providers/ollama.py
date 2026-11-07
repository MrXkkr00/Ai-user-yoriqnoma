"""OllamaProvider (TZ FR-W1, FR-L6): local model through the Ollama HTTP API.

Default model ``gemma4:26b`` (vision). ``format`` is the JSON schema of the answer,
``temperature=0`` and a fixed seed make answers repeatable; thinking is turned off so the
model answers directly. A non-matching answer is sent back with the error up to two
more times; then ``SchemaError`` is raised (the writer marks the article needs_review).
"""

from __future__ import annotations

import time
from typing import Any

import httpx
import ollama
from pydantic import ValidationError

from yoriqnoma_core.writer.providers.base import (
    LLMRequest,
    LLMResult,
    ProviderError,
    SchemaError,
    T,
)

DEFAULT_MODEL = "gemma4:26b"
FALLBACK_MODEL = "qwen3.6:27b"


class OllamaProvider:
    name = "ollama"

    def __init__(
        self,
        host: str = "http://127.0.0.1:11434",
        model: str = DEFAULT_MODEL,
        num_ctx: int = 24576,
        keep_alive: str = "30m",
        timeout_s: float = 600.0,
        retries: int = 2,
        seed: int = 42,
    ) -> None:
        self.host = host
        self.model = model
        self.num_ctx = num_ctx
        self.keep_alive = keep_alive
        self.timeout_s = timeout_s
        self.retries = retries
        self.seed = seed
        self._caps: set[str] | None = None

    def _client(self) -> ollama.AsyncClient:
        return ollama.AsyncClient(host=self.host, timeout=self.timeout_s)

    def capabilities(self) -> set[str]:
        if self._caps is None:
            try:
                info = ollama.Client(host=self.host, timeout=30).show(self.model)
            except (httpx.HTTPError, ollama.ResponseError, ConnectionError) as exc:
                raise ProviderError(self._hint(exc)) from exc
            caps = set(getattr(info, "capabilities", None) or [])
            caps.add("json_schema")
            self._caps = caps
        return self._caps

    def installed_models(self) -> list[str]:
        try:
            listing = ollama.Client(host=self.host, timeout=10).list()
        except (httpx.HTTPError, ollama.ResponseError, ConnectionError) as exc:
            raise ProviderError(
                f"Ollama ishlamayapti ({self.host}). Ollama dasturini ishga tushiring."
            ) from exc
        return sorted(m.model for m in listing.models if m.model)

    def check(self) -> None:
        """Ollama runs, the model is installed and can see images."""
        models = self.installed_models()
        if self.model not in models and f"{self.model}:latest" not in models:
            raise ProviderError(
                f"«{self.model}» modeli o'rnatilmagan. Terminalda: ollama pull {self.model}"
            )
        if "vision" not in self.capabilities():
            raise ProviderError(f"«{self.model}» modeli rasmlarni ko'rmaydi (vision yo'q)")

    def _hint(self, exc: Exception) -> str:
        text = str(exc)
        if "not found" in text.lower():
            return f"«{self.model}» modeli topilmadi. Terminalda: ollama pull {self.model}"
        return f"Ollama bilan bog'lanib bo'lmadi ({self.host}): {text[:200]}"

    async def generate(self, req: LLMRequest, schema: type[T]) -> LLMResult[T]:
        client = self._client()
        user: dict[str, Any] = {"role": "user", "content": req.prompt}
        if req.images:
            user["images"] = [str(p) for p in req.images]
        messages: list[dict[str, Any]] = [{"role": "system", "content": req.system}, user]
        started = time.monotonic()
        last_error = ""
        tokens_in = tokens_out = 0
        for _attempt in range(self.retries + 1):
            try:
                resp = await client.chat(
                    model=self.model,
                    messages=messages,
                    format=schema.model_json_schema(),
                    options={
                        "temperature": req.temperature,
                        "num_ctx": self.num_ctx,
                        "num_predict": req.max_tokens,
                        "seed": self.seed,
                    },
                    keep_alive=self.keep_alive,
                    think=False,
                )
            except (httpx.HTTPError, ollama.ResponseError, ConnectionError) as exc:
                raise ProviderError(self._hint(exc)) from exc
            content = resp.message.content or ""
            tokens_in += int(resp.prompt_eval_count or 0)
            tokens_out += int(resp.eval_count or 0)
            try:
                data = schema.model_validate_json(content)
            except ValidationError as exc:
                last_error = str(exc).splitlines()[0]
                messages += [
                    {"role": "assistant", "content": content},
                    {
                        "role": "user",
                        "content": (
                            f"Javob sxemaga mos emas: {last_error}. "
                            "Faqat sxema bo'yicha to'g'ri JSON qaytaring."
                        ),
                    },
                ]
                continue
            return LLMResult(
                data=data,
                model=self.model,
                input_tokens=tokens_in,
                output_tokens=tokens_out,
                cost_usd=None,
                latency_s=round(time.monotonic() - started, 2),
            )
        raise SchemaError(f"{req.task}: javob sxemaga mos kelmadi ({last_error})")
