from __future__ import annotations

from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from projects.services import upload_blueprint
from runs.management.commands._common import project_by_slug
from runs.services import RunError, execute_run, start_run


class Command(BaseCommand):
    help = "Saytni maqsadli rol bilan o'rganadi (capture + bundle.zip)"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--project", required=True)
        parser.add_argument("--role", required=True)
        parser.add_argument("--blueprint", type=Path, help="tayyor blueprint.json")

    def handle(self, *args: Any, **opts: Any) -> None:
        project = project_by_slug(opts["project"])
        if opts["blueprint"]:
            upload_blueprint(project, opts["blueprint"].read_bytes())
        try:
            run = start_run(project, "bundle", opts["role"], enqueue=False)
        except RunError as exc:
            raise CommandError(str(exc)) from exc
        run = execute_run(run.pk)
        for event in run.events.all():
            self.stdout.write(f"[{event.level}] {event.message}")
        self.stdout.write(f"Ish {run.pk}: {run.get_status_display()} — {run.run_dir}")
        if run.status != "done":
            raise CommandError(run.error)
