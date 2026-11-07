"""Production settings. Every secret and host must come from the environment.

Missing DJANGO_SECRET_KEY, DJANGO_ALLOWED_HOSTS or DATABASE_URL stops the start-up
with ImproperlyConfigured. Full hardening (HSTS, CSP, login rate limits,
`check --deploy`) is T23.
"""

from yoriqnoma_server.settings.base import *  # noqa: F403
from yoriqnoma_server.settings.base import env

DEBUG = False
SECRET_KEY = env.str("DJANGO_SECRET_KEY")
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])

DATABASES = {"default": env.db("DATABASE_URL")}

# TLS terminates at Caddy, which forwards X-Forwarded-Proto.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
