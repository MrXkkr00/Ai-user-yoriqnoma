"""manage.py cleanup --run <id>: remove what the test users left on the site (modes 2, 3).

The same as «Tozalashni qayta urinish» on the run page: the list comes from the run's
provision.json, the admin login of the project is used, the result is printed.
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from runs.models import Run
from runs.services import retry_cleanup


class Command(BaseCommand):
    help = "Ish yaratgan test foydalanuvchilar va ularning yozuvlarini saytdan o'chirish"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--run", type=int, required=True)

    def handle(self, *args: Any, **options: Any) -> None:
        run = Run.objects.filter(pk=options["run"]).select_related("project").first()
        if run is None:
            raise CommandError("Bunday ish yo'q")
        if not run.project.uses_admin:
            raise CommandError("Bu loyihada admin login yo'q: tozalash kerak emas")
        result = retry_cleanup(run.pk).stats.get("cleanup", {})
        self.stdout.write(
            f"O'chirildi: {result.get('users_removed', 0)} ta foydalanuvchi, "
            f"{result.get('objects_removed', 0)} ta obyekt"
        )
        for item in result.get("left", []):
            self.stdout.write(self.style.WARNING(f"Qoldi: {item}"))
