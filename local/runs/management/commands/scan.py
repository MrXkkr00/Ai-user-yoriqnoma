from __future__ import annotations

from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from projects.models import Project
from projects.services import BlueprintError, create_project, raw_blueprint, scan_project
from runs.management.commands._common import project_by_slug


class Command(BaseCommand):
    help = "Loyiha kodini skanerlaydi va blueprint yaratadi"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--project", help="mavjud loyiha slug'i")
        parser.add_argument("--path", type=Path, help="kod papkasi (yangi loyiha)")
        parser.add_argument("--base-url", help="sayt manzili (yangi loyiha)")
        parser.add_argument("--name", help="yangi loyiha nomi")
        parser.add_argument("--mailbox", default="", help="pochta papkasi yoki Mailpit URL")
        parser.add_argument("--out", type=Path, help="blueprint.json nusxasini shu faylga yozish")

    def handle(self, *args: Any, **opts: Any) -> None:
        if opts["project"]:
            project = project_by_slug(opts["project"])
        elif opts["path"] and opts["base_url"]:
            path: Path = opts["path"].resolve()
            if not path.is_dir():
                raise CommandError(f"papka topilmadi: {path}")
            name = opts["name"] or path.name
            mailbox = opts["mailbox"]
            project = Project.objects.filter(source_dir=str(path)).first() or create_project(
                name=name,
                source_dir=str(path),
                base_url=opts["base_url"],
                mailbox_kind="mailpit" if mailbox.startswith("http") else "dir",
                mailbox_target=mailbox,
            )
        else:
            raise CommandError("--project yoki --path va --base-url bering")
        try:
            version = scan_project(project)
        except BlueprintError as exc:
            raise CommandError(str(exc)) from exc
        bp = raw_blueprint(version)
        self.stdout.write(f"Loyiha: {project.slug}")
        for key, value in version.stats.items():
            self.stdout.write(f"  {key}: {value}")
        for role in bp.roles:
            self.stdout.write(f"  rol {role.id:12} {role.kind:9} {role.reason}")
        if opts["out"]:
            opts["out"].write_text(Path(version.path).read_text(encoding="utf-8"), encoding="utf-8")
            self.stdout.write(f"blueprint: {opts['out']}")
