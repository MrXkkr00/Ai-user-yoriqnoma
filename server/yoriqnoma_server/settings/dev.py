"""Developer settings: DEBUG on, SQLite and files in var/ unless DATABASE_URL is set."""

from cryptography.fernet import Fernet

from yoriqnoma_server.settings.base import *  # noqa: F403
from yoriqnoma_server.settings.base import VAR_DIR, env

DEBUG = True
SECRET_KEY = env.str("DJANGO_SECRET_KEY", default="django-insecure-dev-only-never-use-in-prod")
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]

VAR_DIR.mkdir(parents=True, exist_ok=True)

if env.str("DATABASE_URL", default=""):
    DATABASES = {"default": env.db("DATABASE_URL")}
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": VAR_DIR / "server-dev.sqlite3",
        }
    }

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
        "OPTIONS": {"location": str(VAR_DIR / "media")},
    },
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


def _dev_key(name: str, make: bytes) -> str:
    """Dev-only keys live in var/ (git-ignored); production takes them from env."""
    path = VAR_DIR / name
    if not path.exists():
        path.write_bytes(make)
    return path.read_text(encoding="ascii").strip()


YORIQNOMA_FERNET_KEY = env.str("YORIQNOMA_FERNET_KEY", default="") or _dev_key(
    "fernet.key", Fernet.generate_key()
)
YORIQNOMA_PSEUDONYM_KEY = env.str("YORIQNOMA_PSEUDONYM_KEY", default="") or _dev_key(
    "pseudonym.key", Fernet.generate_key()
)
