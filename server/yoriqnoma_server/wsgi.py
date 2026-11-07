"""WSGI entry point for gunicorn. Production settings unless told otherwise."""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "yoriqnoma_server.settings.prod")

application = get_wsgi_application()
