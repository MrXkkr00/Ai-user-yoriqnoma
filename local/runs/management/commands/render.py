from __future__ import annotations

from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from runs.management.commands._common import run_by_id
from yoriqnoma_core.pipeline import run_render


class Command(BaseCommand):
    help = "manual.json dan HTML, PDF va DOCX tayyorlaydi"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--run", type=int, required=True)
        parser.add_argument("--formats", default="html,pdf,docx")

    def handle(self, *args: Any, **opts: Any) -> None:
        run = run_by_id(opts["run"])
        result = run_render(Path(run.run_dir), set(opts["formats"].split(",")))
        for kind, path in result.files.items():
            self.stdout.write(f"{kind}: {path}")
