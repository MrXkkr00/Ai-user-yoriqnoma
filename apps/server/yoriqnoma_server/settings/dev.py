"""Developer settings: DEBUG on, SQLite in var/ unless DATABASE_URL is set."""

from yoriqnoma_server.settings.base import *  # noqa: F403
from yoriqnoma_server.settings.base import REPO_ROOT, env

DEBUG = True
SECRET_KEY = env.str("DJANGO_SECRET_KEY", default="django-insecure-dev-only-never-use-in-prod")
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]

if env.str("DATABASE_URL", default=""):
    DATABASES = {"default": env.db("DATABASE_URL")}
else:
    VAR_DIR = REPO_ROOT / "var"
    VAR_DIR.mkdir(parents=True, exist_ok=True)
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": VAR_DIR / "server-dev.sqlite3",
        }
    }
