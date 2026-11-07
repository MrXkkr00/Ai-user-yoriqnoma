from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from runs.management.commands._common import run_by_id
from yoriqnoma_core.pipeline import make_bundle


class Command(BaseCommand):
    help = "Ish natijasidan bundle.zip yasaydi (server A' rejimi uchun)"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--run", type=int, required=True)
        parser.add_argument("--out", type=Path, required=True)

    def handle(self, *args: Any, **opts: Any) -> None:
        run = run_by_id(opts["run"])
        path = make_bundle(Path(run.run_dir))
        shutil.copy(path, opts["out"])
        self.stdout.write(
            f"bundle: {opts['out']} — buni server sahifasidagi «Yangi ish» formasida yuklang"
        )
