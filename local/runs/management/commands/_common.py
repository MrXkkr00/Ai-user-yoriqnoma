"""Shared helpers of the management commands (they call the same services as the UI)."""

from __future__ import annotations

from django.core.management.base import CommandError

from projects.models import Project
from runs.models import Run


def project_by_slug(slug: str) -> Project:
    try:
        return Project.objects.get(slug=slug)
    except Project.DoesNotExist as exc:
        raise CommandError(f"loyiha topilmadi: {slug}") from exc


def run_by_id(run_id: int) -> Run:
    try:
        return Run.objects.select_related("project").get(pk=run_id)
    except Run.DoesNotExist as exc:
        raise CommandError(f"ish topilmadi: {run_id}") from exc
