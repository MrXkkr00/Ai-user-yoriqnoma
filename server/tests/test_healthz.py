"""/healthz: the web process answers without a login (used by the container healthcheck)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from django.test import Client


@pytest.mark.django_db
def test_healthz_is_public_and_plain(client: Client) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.content == b"ok"
    assert "text/plain" in response["Content-Type"]


def test_compose_web_has_a_healthcheck_and_caddy_waits_for_it() -> None:
    compose: dict[str, Any] = yaml.safe_load(
        (Path(__file__).parent.parent / "docker" / "compose.yml").read_text(encoding="utf-8")
    )
    services = compose["services"]
    assert services["web"]["healthcheck"]["test"][0] == "CMD"
    assert services["caddy"]["depends_on"]["web"]["condition"] == "service_healthy"
    # the key still reaches the worker only
    assert "worker.env" in str(services["worker"]["env_file"])
    assert "worker.env" not in str(services["web"].get("env_file", ""))
