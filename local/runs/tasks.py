"""Huey tasks. Only one exploration at a time (one browser and one GPU on this machine)."""

from __future__ import annotations

from huey.contrib.djhuey import HUEY, db_task
from huey.exceptions import TaskLockedException

from projects.models import Project
from projects.services import scan_project


@db_task(retries=720, retry_delay=5)
def execute_run_task(run_id: int) -> None:
    from runs.services import execute_run

    try:
        with HUEY.lock_task("yoriqnoma-explore"):
            execute_run(run_id)
    except TaskLockedException:
        raise  # another run is busy: Huey retries in 5 s


@db_task()
def scan_project_task(project_id: int) -> None:
    scan_project(Project.objects.get(pk=project_id))
