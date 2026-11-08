"""Celery tasks (ARCHITECTURE §7.3): the job itself and two periodic chores (beat)."""

from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from jobs.models import ACTIVE, Job
from jobs.sinks import add_event

log = logging.getLogger("jobs")


@shared_task(
    name="jobs.run_job",
    acks_late=True,
    reject_on_worker_lost=True,
    time_limit=settings.YORIQNOMA_JOB_TIME_LIMIT_S + 60,
    soft_time_limit=settings.YORIQNOMA_JOB_TIME_LIMIT_S,
)
def run_job(job_id: int) -> str:
    from jobs.pipeline import execute

    return execute(job_id).status


@shared_task(name="jobs.cleanup_expired")
def cleanup_expired() -> int:
    """Remove the results of jobs past their retention time (TZ FR-SV7).

    The job row stays (its cost counts towards the monthly limits); files go.
    """
    now = timezone.now()
    removed = 0
    for job in Job.objects.filter(expires_at__lt=now).exclude(status__in=ACTIVE):
        for artifact in job.artifacts.all():
            artifact.file.delete(save=False)
            artifact.delete()
            removed += 1
        for field in (job.blueprint, job.bundle):
            if field:
                field.delete(save=False)
        job.input_requests.all().delete()
        Job.objects.filter(pk=job.pk).update(blueprint="", bundle="", accounts_enc=None)
    log.info("cleanup_expired: %s files removed", removed)
    return removed


@shared_task(name="jobs.reap_stuck_jobs")
def reap_stuck_jobs() -> int:
    """Jobs running longer than the time limit (a crashed worker) are marked failed."""
    limit = timedelta(seconds=int(settings.YORIQNOMA_JOB_TIME_LIMIT_S) + 600)
    cutoff = timezone.now() - limit
    stuck = Job.objects.filter(status__in=ACTIVE, started_at__lt=cutoff).exclude(status="queued")
    count = 0
    for job in stuck:
        Job.objects.filter(pk=job.pk).update(
            status="failed",
            error="Ish osilib qoldi (vaqt limiti o'tdi) va to'xtatildi",
            finished_at=timezone.now(),
            accounts_enc=None,
        )
        add_event(job.pk, "status", {"status": "failed", "error": "vaqt limiti o'tdi"})
        count += 1
    return count
