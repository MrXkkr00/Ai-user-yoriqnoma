"""Django settings for the local app.

The local app reads folders on the user's machine, so it only ever listens on
127.0.0.1 (CLAUDE.md rule 9). Its own data (SQLite DB, Huey queue, run folders,
keys) lives in ``local/var/`` unless ``YORIQNOMA_VAR_DIR`` is set.
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent  # local/
VAR_DIR = Path(os.environ.get("YORIQNOMA_VAR_DIR") or BASE_DIR / "var").resolve()
VAR_DIR.mkdir(parents=True, exist_ok=True)


def _load_or_create_secret_key(path: Path) -> str:
    """Return this installation's Django secret key, creating it on first start."""
    try:
        with path.open("x", encoding="utf-8") as fh:
            key = secrets.token_urlsafe(50)
            fh.write(key)
            return key
    except FileExistsError:
        key = path.read_text(encoding="utf-8").strip()
    if not key:
        raise ImproperlyConfigured(f"{path} is empty. Delete it and restart to regenerate.")
    return key


SECRET_KEY = _load_or_create_secret_key(VAR_DIR / "django_secret_key.txt")
DEBUG = os.environ.get("YORIQNOMA_DEBUG") == "1"  # set by `yoriqnoma-local --dev`
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "huey.contrib.djhuey",
    "projects",
    "runs",
    "settings_app",
    "evaluation",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "yoriqnoma_local.urls"
WSGI_APPLICATION = "yoriqnoma_local.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.template.context_processors.i18n",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": VAR_DIR / "local.sqlite3",
    }
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LANGUAGE_CODE = "uz"
LANGUAGES = [("uz", "O'zbekcha")]
TIME_ZONE = "Asia/Tashkent"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = VAR_DIR / "static"
MEDIA_ROOT = VAR_DIR / "runs"

X_FRAME_OPTIONS = "DENY"

# Background tasks: SQLite-backed Huey with thread workers (works on Windows).
HUEY: dict[str, object] = {
    "huey_class": "huey.SqliteHuey",
    "name": "yoriqnoma",
    "filename": str(VAR_DIR / "huey.sqlite3"),
    # djhuey defaults `immediate` to DEBUG; keep a real queue even in --dev mode.
    "immediate": False,
    "consumer": {
        "workers": int(os.environ.get("YORIQNOMA_HUEY_WORKERS", "2")),
        "worker_type": "thread",
    },
}
