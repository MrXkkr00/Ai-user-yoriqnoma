"""Server Django project. Importing it registers the Celery app for @shared_task."""

from yoriqnoma_server.celery import app as celery_app

__all__ = ("celery_app",)
