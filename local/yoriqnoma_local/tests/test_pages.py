import pytest
from django.contrib.staticfiles import finders
from django.test import Client

from yoriqnoma_local import views
from yoriqnoma_local.health import Check

pytestmark = pytest.mark.django_db


def test_home_page_greets_in_uzbek_and_loads_htmx(client: Client) -> None:
    response = client.get("/")

    assert response.status_code == 200
    body = response.content.decode()
    assert "Salom!" in body
    assert 'lang="uz"' in body
    assert "vendor/htmx.min.js" in body
    assert 'hx-get="/system-status/"' in body
    assert "X-CSRFToken" in body


def test_htmx_is_served_locally_without_cdn() -> None:
    path = finders.find("vendor/htmx.min.js")

    assert path is not None
    with open(path, encoding="utf-8") as fh:
        assert fh.read(64).startswith("var htmx=")


def test_system_status_partial(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        views,
        "all_checks",
        lambda host, model: [
            Check("Ollama", True, "ishlayapti"),
            Check("Model", False, "«x» o'rnatilmagan", "Terminalda: ollama pull x"),
        ],
    )
    response = client.get("/system-status/")

    body = response.content.decode()
    assert response.status_code == 200
    assert "Tizim holati" in body and "ollama pull x" in body


def test_pages_reject_post(client: Client) -> None:
    assert client.post("/").status_code == 405


def test_unknown_host_is_rejected(client: Client) -> None:
    response = client.get("/", HTTP_HOST="evil.example.com")

    assert response.status_code == 400


def test_settings_page(client: Client) -> None:
    assert client.get("/settings/").status_code == 200
    bad = client.post(
        "/settings/",
        {
            "ollama_host": "http://127.0.0.1:11434",
            "ollama_model": "gemma4:26b",
            "num_ctx": "100",
            "language": "uz",
        },
    )
    assert "4096" in bad.content.decode()
