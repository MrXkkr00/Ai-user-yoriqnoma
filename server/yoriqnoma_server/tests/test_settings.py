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
    "S3_ENDPOINT_URL": "http://minio:9000",
    "S3_BUCKET": "yoriqnoma",
    "S3_ACCESS_KEY": "access",
    "S3_SECRET_KEY": "secret",
    "YORIQNOMA_FERNET_KEY": "0Q2mKz7rI0VQx3wq3nq0G9mZb1u3s8l2pW4cE6vR8tA=",
    "YORIQNOMA_PSEUDONYM_KEY": "p" * 40,
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
    assert prod.SECURE_HSTS_SECONDS >= 31536000 and prod.SECURE_SSL_REDIRECT is True
    assert prod.STORAGES["default"]["BACKEND"] == "storages.backends.s3.S3Storage"
    assert prod.YORIQNOMA_PRIVATE_ALLOWLIST == []


@pytest.mark.parametrize("missing", sorted(PROD_ENV))
def test_prod_refuses_to_start_without_required_env(
    monkeypatch: pytest.MonkeyPatch, missing: str
) -> None:
    for key, value in PROD_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv(missing)

    with pytest.raises(ImproperlyConfigured):
        _fresh_import("yoriqnoma_server.settings.prod")


def test_hardening_settings() -> None:
    base = _fresh_import("yoriqnoma_server.settings.base")
    assert base.PASSWORD_HASHERS[0] == "django.contrib.auth.hashers.Argon2PasswordHasher"
    assert base.MIDDLEWARE[-1] == "axes.middleware.AxesMiddleware"
    assert "csp.middleware.CSPMiddleware" in base.MIDDLEWARE
    assert base.CONTENT_SECURITY_POLICY["DIRECTIVES"]["script-src"] == ["'self'"]
    assert base.REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"] == [
        "rest_framework.authentication.SessionAuthentication"
    ]
    assert not hasattr(base, "ANTHROPIC_API_KEY")  # never a Django setting


def test_deploy_check_is_clean() -> None:
    """`manage.py check --deploy` with production settings: no warnings (TZ SEC-17)."""
    import os
    import subprocess
    import sys

    env = {**os.environ, **PROD_ENV, "DJANGO_SETTINGS_MODULE": "yoriqnoma_server.settings.prod"}
    env["DJANGO_SECRET_KEY"] = "t3st-0nly_" + "".join(chr(65 + i % 26) + str(i) for i in range(30))
    env.pop("ANTHROPIC_API_KEY", None)
    result = subprocess.run(
        [sys.executable, "manage.py", "check", "--deploy", "--fail-level", "WARNING"],
        cwd=str(settings.BASE_DIR),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
