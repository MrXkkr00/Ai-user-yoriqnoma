"""ClaudeProvider with a fake Anthropic client: request shape, cost, budget, secrets (T21)."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from PIL import Image
from pydantic import BaseModel, ValidationError

from yoriqnoma_core.writer.providers import LLMRequest, ProviderError, SchemaError
from yoriqnoma_core.writer.providers.claude import (
    BudgetExceeded,
    ClaudeProvider,
    make_sanitizer,
    prices_from,
)

FAKE_KEY = "sk-ant-test-0123456789abcdef"


class Answer(BaseModel):
    purpose: str


def usage(fresh: int = 1000, out: int = 200, read: int = 0, write: int = 0) -> Any:
    return SimpleNamespace(
        input_tokens=fresh,
        output_tokens=out,
        cache_read_input_tokens=read,
        cache_creation_input_tokens=write,
    )


class FakeMessages:
    def __init__(self, answers: list[Any]) -> None:
        self.answers = answers
        self.calls: list[dict[str, Any]] = []

    async def parse(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        item = self.answers.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def client(*answers: Any) -> Any:
    return SimpleNamespace(messages=FakeMessages(list(answers)))


def ok(text: str = "Buyurtma berish uchun.", **u: int) -> Any:
    return SimpleNamespace(
        parsed_output=Answer(purpose=text), usage=usage(**u), stop_reason="end_turn"
    )


def req(task: str = "describe_flow", **kw: Any) -> LLMRequest:
    return LLMRequest(task=task, system="Siz yo'riqnoma yozasiz.", prompt="Vazifa", **kw)


def test_request_shape_models_and_cost(tmp_path: Path) -> None:
    image = tmp_path / "s001_som.png"
    Image.new("RGB", (8, 8), "white").save(image)
    fake = client(ok(read=5000, write=0), ok())
    events: list[dict[str, Any]] = []
    provider = ClaudeProvider(FAKE_KEY, client=fake, on_cost=events.append, image_roots=[tmp_path])

    result = asyncio.run(provider.generate(req(images=[image]), Answer))
    asyncio.run(provider.generate(req("final_review"), Answer))

    first, second = fake.messages.calls
    assert first["model"] == "claude-sonnet-5-5" and second["model"] == "claude-opus-5-5"
    assert first["output_format"] is Answer
    assert first["system"][0]["cache_control"] == {"type": "ephemeral"}
    blocks = first["messages"][0]["content"]
    assert blocks[0]["type"] == "image" and blocks[0]["source"]["media_type"] == "image/png"
    assert blocks[-1] == {"type": "text", "text": "Vazifa"}
    assert "temperature" not in first  # not an SDK parameter any more
    # 1000 fresh * $2 + 200 out * $10 + 5000 cache reads * $0.2 per million tokens
    assert result.cost_usd == pytest.approx((1000 * 2 + 200 * 10 + 5000 * 0.2) / 1e6)
    assert result.data.purpose.startswith("Buyurtma")
    assert [e["kind"] for e in events] == ["cost", "cost"]
    assert provider.spent_usd == pytest.approx((result.cost_usd or 0) + (1000 * 4 + 200 * 20) / 1e6)


def test_budget_stops_further_calls() -> None:
    provider = ClaudeProvider(FAKE_KEY, client=client(ok(fresh=1_000_000)), budget_usd=1.0)

    asyncio.run(provider.generate(req(), Answer))  # $2: over budget after this call

    with pytest.raises(BudgetExceeded):
        asyncio.run(provider.generate(req(), Answer))


def test_key_never_in_repr_or_errors() -> None:
    error = RuntimeError(f"401 invalid x-api-key {FAKE_KEY} for sk-ant-other-key-999")
    provider = ClaudeProvider(FAKE_KEY, client=client(error))

    assert FAKE_KEY not in repr(provider) and FAKE_KEY not in str(provider)
    with pytest.raises(ProviderError) as info:
        asyncio.run(provider.generate(req(), Answer))
    assert FAKE_KEY not in str(info.value) and "sk-ant-other" not in str(info.value)
    with pytest.raises(ProviderError):
        ClaudeProvider("")  # no key, no client: refuses at once


def test_personal_data_is_masked_before_sending(tmp_path: Path) -> None:
    fake = client(ok())
    events: list[dict[str, Any]] = []
    provider = ClaudeProvider(
        FAKE_KEY,
        client=fake,
        on_cost=events.append,
        sanitize=make_sanitizer({"+998901112233"}),
        image_roots=[tmp_path / "run"],
    )
    request = LLMRequest(
        task="faq",
        system="s",
        prompt="Mijoz: +998 97 765 43 21, test: +998901112233",
    )

    asyncio.run(provider.generate(request, Answer))

    sent = fake.messages.calls[0]["messages"][0]["content"][-1]["text"]
    assert "765 43 21" not in sent and "+998901112233" in sent
    assert {"kind": "pii_masked", "task": "faq", "count": 1} in events
    outside = tmp_path / "other.png"
    Image.new("RGB", (4, 4)).save(outside)
    with pytest.raises(ProviderError, match="tashqarida"):
        asyncio.run(provider.generate(req(images=[outside]), Answer))


def test_schema_errors_are_retried_then_reported() -> None:
    try:
        Answer.model_validate({})
    except ValidationError as exc:
        bad = exc
    fake = client(bad, ok("Ikkinchi urinish."))
    provider = ClaudeProvider(FAKE_KEY, client=fake, retries=2)

    assert asyncio.run(provider.generate(req(), Answer)).data.purpose == "Ikkinchi urinish."
    assert "sxemaga mos emas" in fake.messages.calls[1]["messages"][-1]["content"]

    refused = SimpleNamespace(parsed_output=None, usage=usage(), stop_reason="refusal")
    with pytest.raises(SchemaError, match="refusal"):
        asyncio.run(ClaudeProvider(FAKE_KEY, client=client(refused)).generate(req(), Answer))


def test_prices_from_config() -> None:
    prices = prices_from(
        {"claude-sonnet-5-5": {"input": 3, "output": 15, "cache_read": 0.3, "cache_write": 3.75}}
    )
    assert prices["claude-sonnet-5-5"].input == 3 and "claude-opus-5-5" in prices


@pytest.mark.llm
def test_real_claude_small_request() -> None:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        pytest.skip("ANTHROPIC_API_KEY yo'q")
    provider = ClaudeProvider(key, models={"*": "claude-haiku-5-5"}, budget_usd=0.05)
    result = asyncio.run(
        provider.generate(
            LLMRequest(task="t", system="O'zbek tilida javob bering.", prompt="Choynak nima?"),
            Answer,
        )
    )
    assert result.data.purpose and result.cost_usd is not None
