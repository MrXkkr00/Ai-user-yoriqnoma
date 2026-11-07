"""ASGI entry point. Production settings unless told otherwise."""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "yoriqnoma_server.settings.prod")

application = get_asgi_application()
