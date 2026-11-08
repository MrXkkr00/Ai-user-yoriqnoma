"""Writer: turns blueprint + capture into manual.json with an LLM provider."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from yoriqnoma_core.writer.assemble import ManualBuilder
from yoriqnoma_core.writer.cache import LLMCache
from yoriqnoma_core.writer.providers.base import LLMProvider
from yoriqnoma_core.writer.review import final_review
from yoriqnoma_core.writer.tasks import TaskRunner, TaskStats
from yoriqnoma_schemas import Blueprint, CaptureRun, Manual, load_json, save_json


def estimate_calls(run_dir: Path) -> int:
    """Rough number of LLM calls for progress bars: one per article plus fixed tasks."""
    capture = load_json(run_dir / "capture" / "capture.json", CaptureRun)
    verified = sum(1 for f in capture.flows if not f.helper and f.status == "verified")
    return verified + 10


async def write_manual(
    run_dir: Path,
    provider: LLMProvider,
    cache_dir: Path | None = None,
    source_mode: str = "local",
    before_call: Callable[[str], None] | None = None,
) -> tuple[Manual, TaskStats]:
    bp = load_json(run_dir / "blueprint.json", Blueprint)
    capture = load_json(run_dir / "capture" / "capture.json", CaptureRun)
    info = bp.role(capture.role)
    role_label = info.label if info else capture.role
    ignore = set(capture.test_values) | set(capture.public_values)
    cache = LLMCache(cache_dir) if cache_dir is not None else None
    tasks = TaskRunner(provider, cache, role_label, ignore, run_dir / ".cache" / "llm_images")
    tasks.before_call = before_call
    builder = ManualBuilder(bp, capture, tasks, run_dir / "capture", source_mode)
    manual = await builder.build([provider.model])
    if "final_review" in provider.capabilities():  # Claude: Opus reads it all (T21)
        known = builder._known(list(capture.states))
        tasks.stats.review_fixes = await final_review(manual, tasks, run_dir / "capture", known)
        model_for = getattr(provider, "model_for", None)
        if callable(model_for):
            manual.models = list(dict.fromkeys([*manual.models, model_for("final_review")]))
    save_json(run_dir / "manual.json", manual)
    return manual, tasks.stats


__all__ = ["estimate_calls", "write_manual"]
