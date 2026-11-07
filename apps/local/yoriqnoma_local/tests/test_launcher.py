from typing import Any

import pytest
from django.core import management

from yoriqnoma_local import launcher


@pytest.fixture
def recorded(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Replace migrate and runserver with recorders so nothing really starts."""
    calls: dict[str, Any] = {}

    def fake_call_command(*args: Any, **kwargs: Any) -> None:
        calls["call_command"] = (args, kwargs)

    def fake_execute(argv: list[str]) -> None:
        calls["argv"] = argv

    monkeypatch.setattr(management, "call_command", fake_call_command)
    monkeypatch.setattr(management, "execute_from_command_line", fake_execute)
    monkeypatch.delenv("YORIQNOMA_LOCAL_PORT", raising=False)
    return calls


def test_runs_migrations_then_serves_on_loopback(recorded: dict[str, Any]) -> None:
    launcher.main(["--no-browser"])

    assert recorded["call_command"][0] == ("migrate",)
    assert recorded["argv"][1:3] == ["runserver", "127.0.0.1:8765"]


def test_port_comes_from_env_but_host_stays_loopback(
    recorded: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("YORIQNOMA_LOCAL_PORT", "9123")

    launcher.main(["--no-browser"])

    assert recorded["argv"][2] == "127.0.0.1:9123"


@pytest.mark.parametrize("bad_port", ["abc", "0", "70000"])
def test_invalid_port_stops_with_a_clear_message(
    recorded: dict[str, Any], monkeypatch: pytest.MonkeyPatch, bad_port: str
) -> None:
    monkeypatch.setenv("YORIQNOMA_LOCAL_PORT", bad_port)

    with pytest.raises(SystemExit, match="YORIQNOMA_LOCAL_PORT"):
        launcher.main(["--no-browser"])
    assert "argv" not in recorded
