from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandParser

from runs.management.commands._common import run_by_id
from runs.services import provider_for
from yoriqnoma_core.pipeline import ConsoleProgressSink, NeverCancel, run_write


class Command(BaseCommand):
    help = "Capture asosida yo'riqnoma matnini Ollama bilan yozadi (manual.json)"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--run", type=int, required=True)
        parser.add_argument("--model", default="")

    def handle(self, *args: Any, **opts: Any) -> None:
        run = run_by_id(opts["run"])
        if opts["model"]:
            run.model = opts["model"]
        provider = provider_for(run)
        provider.check()
        manual = asyncio.run(
            run_write(
                Path(run.run_dir),
                provider,
                ConsoleProgressSink(),
                NeverCancel(),
                cache_dir=Path(settings.VAR_DIR) / "cache" / "llm",
            )
        )
        self.stdout.write(
            f"manual.json: {sum(len(s.articles) for s in manual.sections)} maqola, "
            f"qamrov {manual.coverage.percent.get('total', 0)}%"
        )
