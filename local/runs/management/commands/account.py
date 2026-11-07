from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from projects.services import set_account
from runs.management.commands._common import project_by_slug


class Command(BaseCommand):
    help = "Rol uchun test akkaunt qo'shadi (parol shifrlangan holda saqlanadi)"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--project", required=True)
        parser.add_argument("--role", required=True)
        parser.add_argument("--alias", choices=["A", "B"], default="A")
        parser.add_argument("--login", required=True)
        parser.add_argument("--password", required=True)

    def handle(self, *args: Any, **opts: Any) -> None:
        project = project_by_slug(opts["project"])
        set_account(project, opts["role"], opts["alias"], opts["login"], opts["password"])
        self.stdout.write(f"{opts['role']}:{opts['alias']} akkaunti saqlandi ({opts['login']})")
