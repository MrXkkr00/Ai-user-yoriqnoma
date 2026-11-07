"""The single API both Django apps call (ARCHITECTURE §5). It knows nothing about Django.

* ``run_explore`` — blueprint -> capture/ (and blueprint.json in the run folder);
* ``run_write`` — capture -> manual.json with an LLM provider;
* ``run_render`` — manual -> dist/ (HTML, PDF, DOCX, coverage report);
* ``make_bundle`` — capture -> bundle.zip for server mode A'.

Progress, cancellation and human input are protocols the apps implement.
"""

from __future__ import annotations

from pathlib import Path

from yoriqnoma_core.explorer import bundle as _bundle
from yoriqnoma_core.explorer.options import (
    AccountCredentials,
    Cancelled,
    CancelToken,
    ExploreOptions,
    HumanInput,
    NeverCancel,
    NoHuman,
    NullProgress,
    ProgressSink,
)
from yoriqnoma_core.explorer.runner import RunAborted, run_explorer
from yoriqnoma_core.render import RenderResult, build
from yoriqnoma_core.writer import estimate_calls, write_manual
from yoriqnoma_core.writer.providers.base import LLMProvider
from yoriqnoma_schemas import Blueprint, CaptureRun, Manual, save_json

__all__ = [
    "AccountCredentials",
    "CancelToken",
    "Cancelled",
    "ConsoleProgressSink",
    "ExploreOptions",
    "HumanInput",
    "NeverCancel",
    "NoHuman",
    "NullProgress",
    "ProgressSink",
    "RunAborted",
    "TerminalHumanInput",
    "make_bundle",
    "run_explore",
    "run_render",
    "run_write",
]


async def run_explore(
    blueprint: Blueprint,
    run_dir: Path,
    opts: ExploreOptions,
    human: HumanInput,
    progress: ProgressSink,
    cancel: CancelToken,
) -> CaptureRun:
    run_dir.mkdir(parents=True, exist_ok=True)
    save_json(run_dir / "blueprint.json", blueprint)
    if cancel.is_cancelled():
        raise Cancelled("ish bekor qilindi")
    return await run_explorer(blueprint, run_dir, opts, human, progress, cancel)


async def run_write(
    run_dir: Path,
    provider: LLMProvider,
    progress: ProgressSink,
    cancel: CancelToken,
    cache_dir: Path | None = None,
    source_mode: str = "local",
) -> Manual:
    progress.stage("write", estimate_calls(run_dir))

    def before_call(task: str) -> None:
        if cancel.is_cancelled():
            raise Cancelled("ish bekor qilindi")
        progress.advance()

    manual, stats = await write_manual(
        run_dir, provider, cache_dir=cache_dir, source_mode=source_mode, before_call=before_call
    )
    progress.log(
        "info",
        f"yozuvchi: {stats.calls} ta chaqiruv ({stats.cached} keshdan), "
        f"{stats.needs_review} ta matn tekshirilishi kerak, {stats.fallbacks} ta shablon matn",
    )
    for error in stats.errors[:5]:
        progress.log("warning", error)
    return manual


def run_render(run_dir: Path, formats: set[str]) -> RenderResult:
    return build(run_dir, formats)


def make_bundle(run_dir: Path) -> Path:
    return _bundle.make_bundle(run_dir)


class ConsoleProgressSink:
    """Prints progress to the terminal (debug and management commands)."""

    def __init__(self) -> None:
        self.total = 0
        self.done = 0
        self.name = ""

    def stage(self, name: str, total: int) -> None:
        self.name, self.total, self.done = name, total, 0
        print(f"== {name} ({total})", flush=True)

    def advance(self, n: int = 1) -> None:
        self.done += n

    def log(self, level: str, message: str) -> None:
        print(f"[{self.name} {self.done}/{self.total}] {level}: {message}", flush=True)

    def event(self, kind: str, payload: dict[str, object]) -> None:
        return None


class TerminalHumanInput:
    """Asks in the terminal (``manage.py`` commands and debug runs)."""

    async def ask(self, kind: str, message: str) -> str:
        import asyncio

        return await asyncio.to_thread(input, f"{message}: ")
