import importlib
import sys
from types import ModuleType

import pytest
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from yoriqnoma_server.celery import app as celery_app

SERVER_APPS = ["accounts", "domains", "jobs", "scout", "security", "api"]
PROD_ENV = {
    "DJANGO_SECRET_KEY": "x" * 50,
    "DJANGO_ALLOWED_HOSTS": "yoriqnoma.example.com",
    "DATABASE_URL": "postgres://yoriqnoma:secret@postgres:5432/yoriqnoma",
}


def _fresh_import(name: str) -> ModuleType:
    """Execute a settings module from scratch without touching django.conf.settings."""
    sys.modules.pop(name, None)
    try:
        return importlib.import_module(name)
    finally:
        sys.modules.pop(name, None)


def test_server_apps_and_drf_are_installed() -> None:
    for app in [*SERVER_APPS, "rest_framework"]:
        assert app in settings.INSTALLED_APPS


def test_language_and_timezone() -> None:
    assert settings.LANGUAGE_CODE == "uz"
    assert settings.TIME_ZONE == "Asia/Tashkent"


def test_drf_denies_anonymous_access_by_default() -> None:
    assert settings.REST_FRAMEWORK["DEFAULT_PERMISSION_CLASSES"] == [
        "rest_framework.permissions.IsAuthenticated"
    ]


def test_celery_runs_eagerly_in_tests() -> None:
    assert celery_app.conf.task_always_eager is True
    assert celery_app.conf.task_acks_late is True
    assert celery_app.conf.worker_prefetch_multiplier == 1


def test_dev_uses_sqlite_without_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    dev = _fresh_import("yoriqnoma_server.settings.dev")

    assert dev.DEBUG is True
    assert dev.DATABASES["default"]["ENGINE"] == "django.db.backends.sqlite3"


def test_prod_reads_everything_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in PROD_ENV.items():
        monkeypatch.setenv(key, value)

    prod = _fresh_import("yoriqnoma_server.settings.prod")

    assert prod.DEBUG is False
    assert prod.ALLOWED_HOSTS == ["yoriqnoma.example.com"]
    assert prod.DATABASES["default"]["ENGINE"] == "django.db.backends.postgresql"
    assert prod.SESSION_COOKIE_SECURE is True
    assert prod.CSRF_COOKIE_SECURE is True


@pytest.mark.parametrize("missing", sorted(PROD_ENV))
def test_prod_refuses_to_start_without_required_env(
    monkeypatch: pytest.MonkeyPatch, missing: str
) -> None:
    for key, value in PROD_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv(missing)

    with pytest.raises(ImproperlyConfigured):
        _fresh_import("yoriqnoma_server.settings.prod")
