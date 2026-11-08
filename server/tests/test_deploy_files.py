"""Deployment files (T22, T23, TZ SEC-12): the Claude key reaches the worker only.

These read docker/compose.yml and the Dockerfiles as text and YAML; no Docker needed.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import yaml

SERVER = Path(__file__).resolve().parent.parent
DOCKER = SERVER / "docker"


def compose() -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load((DOCKER / "compose.yml").read_text(encoding="utf-8"))
    return data


def env_files(service: dict[str, Any]) -> list[str]:
    value = service.get("env_file", [])
    return [value] if isinstance(value, str) else list(value)


def test_claude_key_only_in_worker() -> None:
    services = compose()["services"]
    with_key = [name for name, s in services.items() if "worker.env" in env_files(s)]
    assert with_key == ["worker"]
    for name, service in services.items():
        env = service.get("environment") or {}
        assert "ANTHROPIC_API_KEY" not in env, name
    for path in [*DOCKER.glob("Dockerfile*"), DOCKER / "compose.yml", DOCKER / "compose.test.yml"]:
        text = path.read_text(encoding="utf-8")
        code = [ln for ln in text.splitlines() if not ln.lstrip().startswith("#")]
        assert not any("ANTHROPIC_API_KEY" in ln for ln in code), path.name  # comments only
        assert "sk-ant-" not in text
    assert "ANTHROPIC_API_KEY" not in (DOCKER / ".env.example").read_text(encoding="utf-8")
    worker_template = (DOCKER / "worker.env.example").read_text(encoding="utf-8")
    assert "ANTHROPIC_API_KEY=\n" in worker_template  # a template without a value


def test_services_networks_and_profiles() -> None:
    data = compose()
    services = data["services"]
    assert {"caddy", "web", "worker", "beat", "postgres", "redis", "minio", "mailpit"} <= set(
        services
    )
    assert data["networks"]["internal"]["internal"] is True
    assert set(services["worker"]["networks"]) == {"internal", "egress"}
    for name in ("postgres", "redis"):
        assert services[name]["networks"] == ["internal"], name
    assert services["demo_shop"]["profiles"] == ["test"]
    assert "ALL" in services["worker"]["cap_drop"]


def test_env_files_are_git_ignored_and_templates_are_not() -> None:
    repo = SERVER.parent
    ignored = subprocess.run(
        ["git", "check-ignore", "server/docker/.env", "server/docker/worker.env"],
        cwd=repo,
        capture_output=True,
        text=True,
    ).stdout.split()
    assert ignored == ["server/docker/.env", "server/docker/worker.env"]
    kept = subprocess.run(
        ["git", "check-ignore", "server/docker/.env.example", "server/docker/worker.env.example"],
        cwd=repo,
        capture_output=True,
        text=True,
    ).stdout.split()
    assert kept == []
    dockerignore = (SERVER / ".dockerignore").read_text(encoding="utf-8")
    for pattern in ("docker/.env", "docker/worker.env", ".venv/", "var/", "*.key"):
        assert pattern in dockerignore


def test_production_never_allows_private_addresses() -> None:
    prod = (SERVER / "yoriqnoma_server" / "settings" / "prod.py").read_text(encoding="utf-8")
    assert "\nYORIQNOMA_PRIVATE_ALLOWLIST = []\n" in prod
    e2e = (SERVER / "yoriqnoma_server" / "settings" / "e2e.py").read_text(encoding="utf-8")
    assert 'YORIQNOMA_PRIVATE_ALLOWLIST = ["demo_shop"]' in e2e
