from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from projects.services import effective_blueprint, role_options
from runs.management.commands._common import project_by_slug
from runs.models import Run
from runs.services import RunError, execute_run, run_files, start_run


class Command(BaseCommand):
    help = "Ish: to'liq yo'riqnoma, blueprint yoki bundle (terminalda, navbatsiz)"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--project", required=True)
        parser.add_argument("--output", choices=["full", "blueprint", "bundle"], default="full")
        parser.add_argument("--role", action="append", default=[], help="bir necha marta mumkin")
        parser.add_argument(
            "--list-roles", action="store_true", help="rol variantlarini ko'rsatish"
        )
        parser.add_argument("--model", default="")
        parser.add_argument("--formats", default="html,pdf,docx", help="+ tour, gif")
        parser.add_argument(
            "--previous", type=int, help="yangilanadigan ish raqami: changelog.md tuziladi"
        )

    def handle(self, *args: Any, **opts: Any) -> None:
        project = project_by_slug(opts["project"])
        version = project.current_blueprint()
        if version is None:
            raise CommandError("avval: manage.py scan")
        bp, _ = effective_blueprint(version)
        options = role_options(project, bp)
        if opts["list_roles"] or (not opts["role"] and opts["output"] != "blueprint"):
            usable = [o for o in options if o.selectable]
            self.stdout.write(
                f"Saytda administratordan boshqa {len(usable)} ta rol topildi. "
                "Qaysi rol uchun yo'riqnoma yozay? (--role <id>)"
            )
            for o in options:
                mark = "  " if o.selectable else "x "
                self.stdout.write(
                    f"{mark}{o.id:12} {o.label:16} sahifa: {o.pages:3} "
                    f"vazifa: {o.flows:3}  {o.account_note if o.selectable else o.reason}"
                )
            return
        roles = opts["role"] or [""]
        for role in roles:
            try:
                run = start_run(
                    project,
                    opts["output"],
                    role,
                    opts["model"],
                    opts["formats"].split(","),
                    enqueue=False,
                    previous=Run.objects.filter(pk=opts["previous"]).first()
                    if opts["previous"]
                    else None,
                )
            except RunError as exc:
                raise CommandError(str(exc)) from exc
            if run.status == "queued":
                self.stdout.write(f"Ish {run.pk} ({role}) boshlandi: {run.run_dir}")
                run = execute_run(run.pk)
            for event in run.events.all():
                self.stdout.write(f"[{event.level}] {event.message}")
            self.stdout.write(f"Natija: {run.get_status_display()} {run.error}")
            for item in run_files(run):
                self.stdout.write(f"  {item['label']}: {run.run_dir}/{item['rel']}")
            if run.status != "done":
                raise CommandError(run.error or run.status)
