"""Unit-test settings: in-memory SQLite, eager Celery, fast hashing, files in a temp dir."""

import tempfile
from pathlib import Path

from yoriqnoma_server.settings.base import *  # noqa: F403

DEBUG = False
SECRET_KEY = "test-only-not-a-secret"
ALLOWED_HOSTS = ["127.0.0.1", "localhost", "testserver"]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

_TMP = Path(tempfile.mkdtemp(prefix="yoriqnoma-server-test-"))
VAR_DIR = _TMP / "var"
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
        "OPTIONS": {"location": str(_TMP / "media")},
    },
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

CELERY_BROKER_URL = "memory://"
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# Fixed test keys (not secrets).
YORIQNOMA_FERNET_KEY = "0Q2mKz7rI0VQx3wq3nq0G9mZb1u3s8l2pW4cE6vR8tA="
YORIQNOMA_PSEUDONYM_KEY = "test-pseudonym-key-not-a-secret"
YORIQNOMA_MAIL_DOMAIN = "inbox.yoriqnoma.test"
