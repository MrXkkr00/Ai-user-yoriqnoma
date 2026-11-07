from types import SimpleNamespace
from typing import Any

import pytest
from django.core import management

from settings_app.models import AppSettings
from yoriqnoma_local import health, launcher


@pytest.fixture
def recorded(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Replace migrate, the web server, the worker and checks with recorders."""
    calls: dict[str, Any] = {"commands": []}

    def fake_call_command(*args: Any, **kwargs: Any) -> None:
        calls["commands"].append(args[0])

    monkeypatch.setattr(management, "call_command", fake_call_command)
    monkeypatch.setattr(launcher, "serve", lambda port: calls.setdefault("port", port))
    monkeypatch.setattr(launcher, "start_worker", lambda: calls.setdefault("worker", None))
    monkeypatch.setattr(health, "all_checks", lambda host, model: [])
    monkeypatch.setattr(
        AppSettings,
        "load",
        classmethod(lambda cls: SimpleNamespace(ollama_host="h", ollama_model="m")),
    )
    monkeypatch.delenv("YORIQNOMA_LOCAL_PORT", raising=False)
    return calls


def test_runs_migrations_then_serves_on_loopback(recorded: dict[str, Any]) -> None:
    launcher.main(["--no-browser"])

    assert recorded["commands"][0] == "migrate"
    assert recorded["port"] == 8765 and launcher.HOST == "127.0.0.1"
    assert "worker" in recorded


def test_port_comes_from_env_but_host_stays_loopback(
    recorded: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("YORIQNOMA_LOCAL_PORT", "9123")

    launcher.main(["--no-browser", "--no-worker"])

    assert recorded["port"] == 9123
    assert "worker" not in recorded


@pytest.mark.parametrize("bad_port", ["abc", "0", "70000"])
def test_invalid_port_stops_with_a_clear_message(
    recorded: dict[str, Any], monkeypatch: pytest.MonkeyPatch, bad_port: str
) -> None:
    monkeypatch.setenv("YORIQNOMA_LOCAL_PORT", bad_port)

    with pytest.raises(SystemExit, match="YORIQNOMA_LOCAL_PORT"):
        launcher.main(["--no-browser"])
    assert "port" not in recorded
