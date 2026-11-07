from __future__ import annotations

from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from evaluation.services import DEFAULT_GOLDEN, run_eval, start_eval


class Command(BaseCommand):
    help = "Oltin to'plamda Ollama modellarini solishtiradi"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN)
        parser.add_argument("--models", default="gemma4:26b,qwen3.6:27b")
        parser.add_argument("--limit", type=int, default=None)

    def handle(self, *args: Any, **opts: Any) -> None:
        models = [m.strip() for m in opts["models"].split(",") if m.strip()]
        run = run_eval(start_eval(models, opts["golden"], enqueue=False), limit=opts["limit"])
        self.stdout.write(f"Eval {run.pk}: {run.get_status_display()} {run.error}")
        for model, metrics in run.summary.items():
            self.stdout.write(f"  {model}: {metrics}")
