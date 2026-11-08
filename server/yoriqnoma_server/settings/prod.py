"""Production settings. Every secret, host and service address comes from the environment.

Missing values stop the start-up with ImproperlyConfigured. Hardening (TZ SEC-17): HTTPS
only, HSTS, secure cookies, CSP (base.py), login attempt limits (django-axes, base.py);
``manage.py check --deploy`` passes.
"""

from yoriqnoma_server.settings.base import *  # noqa: F403
from yoriqnoma_server.settings.base import env

DEBUG = False
SECRET_KEY = env.str("DJANGO_SECRET_KEY")
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])

DATABASES = {"default": env.db("DATABASE_URL")}
DATABASES["default"]["CONN_MAX_AGE"] = 60

# Results, uploads and images in MinIO (S3); downloads are short-lived signed links.
STORAGES = {
    "default": {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "endpoint_url": env.str("S3_ENDPOINT_URL"),
            "bucket_name": env.str("S3_BUCKET"),
            "access_key": env.str("S3_ACCESS_KEY"),
            "secret_key": env.str("S3_SECRET_KEY"),
            "region_name": env.str("S3_REGION", default="us-east-1"),
            "addressing_style": "path",
            "signature_version": "s3v4",
            "querystring_auth": True,
            "querystring_expire": 300,
            "file_overwrite": False,
            "default_acl": None,
        },
    },
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

# Signed download links are opened by the user's browser: they are made for the public
# MinIO address (Caddy routes it). Without one, Django streams the file after the owner check.
S3_PUBLIC_ENDPOINT_URL = env.str("S3_PUBLIC_ENDPOINT_URL", default="")

YORIQNOMA_FERNET_KEY = env.str("YORIQNOMA_FERNET_KEY")
# Never any private address in production (TZ SEC-10), whatever the environment says.
YORIQNOMA_PRIVATE_ALLOWLIST = []
YORIQNOMA_PSEUDONYM_KEY = env.str("YORIQNOMA_PSEUDONYM_KEY")

# TLS terminates at Caddy, which forwards X-Forwarded-Proto.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = env.int("DJANGO_HSTS_SECONDS", default=31536000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_SECURE = True
