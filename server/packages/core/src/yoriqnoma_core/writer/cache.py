"""File cache of LLM answers (TZ FR-W7): same input -> no new call. No database."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pydantic import BaseModel

from yoriqnoma_core.writer.providers.base import LLMProvider, LLMRequest, LLMResult, T


def cache_key(req: LLMRequest, prompt_version: str, model: str, schema: type[BaseModel]) -> str:
    h = hashlib.sha256()
    for part in (req.task, prompt_version, model, schema.__name__, req.system, req.prompt):
        h.update(part.encode("utf-8"))
        h.update(b"\0")
    for image in req.images:
        h.update(hashlib.sha256(image.read_bytes()).digest() if image.is_file() else b"-")
    return h.hexdigest()


class LLMCache:
    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self.hits = 0
        self.misses = 0

    def path(self, key: str) -> Path:
        return self.folder / f"{key}.json"

    def get(self, key: str) -> dict[str, object] | None:
        path = self.path(key)
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, dict) else None

    def put(self, key: str, data: dict[str, object]) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        tmp = self.path(key).with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path(key))


async def cached_generate(
    provider: LLMProvider,
    cache: LLMCache | None,
    req: LLMRequest,
    schema: type[T],
    prompt_version: str,
) -> LLMResult[T]:
    if cache is None:
        return await provider.generate(req, schema)
    key = cache_key(req, prompt_version, provider.model, schema)
    hit = cache.get(key)
    if hit is not None:
        try:
            cache.hits += 1
            return LLMResult(
                schema.model_validate(hit["data"]), str(hit.get("model", "")), cached=True
            )
        except (KeyError, ValueError):
            pass
    cache.misses += 1
    result = await provider.generate(req, schema)
    cache.put(key, {"model": result.model, "data": result.data.model_dump(mode="json")})
    return result
