"""Celery application for the server's background jobs.

The default settings module is ``prod`` on purpose: this file runs whenever the
``yoriqnoma_server`` package is imported, and it must not quietly switch a
production process (wsgi, worker) to dev settings. ``manage.py`` sets ``dev``
before anything is imported, so local development is unaffected.

The worker refuses to start without the Claude key or the pseudonym key (TZ SEC-12).
"""

import os
from typing import Any

from celery import Celery
from celery.signals import worker_init

from yoriqnoma_server.worker_env import worker_env_problems

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "yoriqnoma_server.settings.prod")

app = Celery("yoriqnoma_server")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@worker_init.connect
def check_worker_env(**_: Any) -> None:
    problems = worker_env_problems(os.environ)
    if problems:
        raise SystemExit("Worker ishga tushmadi:\n- " + "\n- ".join(problems))
