"""Celery application for the server's background jobs.

The default settings module is ``prod`` on purpose: this file runs whenever the
``yoriqnoma_server`` package is imported, and it must not quietly switch a
production process (wsgi, worker) to dev settings. ``manage.py`` sets ``dev``
before anything is imported, so local development is unaffected.
"""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "yoriqnoma_server.settings.prod")

app = Celery("yoriqnoma_server")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
