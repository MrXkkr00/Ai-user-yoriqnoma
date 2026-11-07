from pathlib import Path

from django.conf import settings
from huey import SqliteHuey
from huey.contrib.djhuey import HUEY

from yoriqnoma_local import settings as local_settings

LOCAL_APPS = ["projects", "runs", "settings_app", "evaluation"]


def test_listens_on_loopback_only() -> None:
    # django.conf.settings gains "testserver" during tests; check the real module.
    assert local_settings.ALLOWED_HOSTS == ["127.0.0.1", "localhost"]


def test_language_and_timezone() -> None:
    assert settings.LANGUAGE_CODE == "uz"
    assert settings.TIME_ZONE == "Asia/Tashkent"
    assert settings.USE_TZ is True


def test_own_database_is_sqlite_in_var() -> None:
    # pytest-django swaps the live DB settings for a test database; read the file itself
    import runpy

    db = runpy.run_path(local_settings.__file__)["DATABASES"]["default"]
    assert db["ENGINE"] == "django.db.backends.sqlite3"
    assert Path(str(db["NAME"])) == local_settings.VAR_DIR / "local.sqlite3"


def test_csrf_protection_is_enabled() -> None:
    assert "django.middleware.csrf.CsrfViewMiddleware" in settings.MIDDLEWARE


def test_local_apps_are_installed() -> None:
    for app in LOCAL_APPS:
        assert app in settings.INSTALLED_APPS


def test_huey_uses_sqlite_and_runs_inline_in_tests() -> None:
    assert local_settings.HUEY["huey_class"] == "huey.SqliteHuey"
    assert local_settings.HUEY["immediate"] is False
    assert isinstance(HUEY, SqliteHuey)
    assert HUEY.immediate is True


def test_secret_key_is_generated_per_install() -> None:
    key_file = local_settings.VAR_DIR / "django_secret_key.txt"
    assert key_file.read_text(encoding="utf-8").strip() == settings.SECRET_KEY
    assert len(settings.SECRET_KEY) >= 50
