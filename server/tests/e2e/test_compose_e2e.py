"""Server end-to-end tests against docker compose (T28, TZ QM-4..QM-6, NFR-4).

Needs the test profile running and a real Claude key in docker/worker.env (the worker
refuses to start without one), so these tests spend real money:

    cd server
    docker compose -f docker/compose.yml -f docker/compose.test.yml --profile test up -d --build
    uv run pytest -m server tests/e2e

The person's side is played by this test: the local app's files (blueprint.json made by
the local scanner, bundle.zip in the local format) are uploaded through the server's own
HTTP API with a session login, exactly like the web form does (TZ FR-SV9).
"""

from __future__ import annotations

import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any

import httpx
import pytest

from jobs.tests.samples import build_bundle

pytestmark = pytest.mark.server

SERVER = Path(__file__).resolve().parents[2]
REPO = SERVER.parent
BASE = os.environ.get("YORIQNOMA_E2E_URL", "http://127.0.0.1:8000")
SITE = "http://demo_shop:8800/"  # as the worker sees the test site
COMPOSE = ["docker", "compose", "-f", "docker/compose.yml", "-f", "docker/compose.test.yml"]
LIMIT_A_S = 20 * 60  # NFR-4: server mode A, whole job


def compose(*args: str) -> str:
    result = subprocess.run(
        [*COMPOSE, *args], cwd=SERVER, capture_output=True, text=True, timeout=600, check=True
    )
    return result.stdout


@pytest.fixture(scope="module")
def client() -> httpx.Client:
    try:
        httpx.get(BASE + "/accounts/login/", timeout=5)
    except httpx.HTTPError:
        pytest.skip(f"server is not running at {BASE} (docker compose --profile test up)")
    session = httpx.Client(base_url=BASE, timeout=60, follow_redirects=False)
    name = f"e2e{int(time.time())}"
    page = session.get("/accounts/register/")
    token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', page.text)
    assert token
    made = session.post(
        "/accounts/register/",
        data={
            "csrfmiddlewaretoken": token.group(1),
            "username": name,
            "email": f"{name}@example.uz",
            "password1": "E2e-Parol-2026!",
            "password2": "E2e-Parol-2026!",
        },
    )
    assert made.status_code == 302
    session.headers["X-CSRFToken"] = session.cookies["csrftoken"]
    session.headers["Referer"] = BASE + "/"
    domain = session.post("/api/domains/", json={"host": "demo_shop"})
    assert domain.status_code == 201, domain.text
    # The test site cannot host a verification file: the operator marks it verified.
    compose(
        "exec",
        "-T",
        "web",
        "python",
        "manage.py",
        "shell",
        "-c",
        "from django.utils import timezone; from domains.models import Domain; "
        f"Domain.objects.filter(owner__username='{name}', host='demo_shop')"
        ".update(verified_at=timezone.now(), method='dns')",
    )
    return session


def wait_done(client: httpx.Client, job_id: int, limit_s: int = 3600) -> dict[str, Any]:
    started = time.monotonic()
    while True:
        data: dict[str, Any] = client.get(f"/api/jobs/{job_id}/").json()
        if data["status"] in {"done", "failed", "cancelled"}:
            data["elapsed_s"] = round(time.monotonic() - started)
            return data
        assert time.monotonic() - started < limit_s, f"job {job_id} took too long"
        time.sleep(5)


def local_blueprint(tmp_path: Path) -> bytes:
    python = REPO / "local" / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not python.exists():
        pytest.skip("local app environment is needed to make blueprint.json")
    out = tmp_path / "blueprint.json"
    subprocess.run(
        [
            str(python),
            "-m",
            "yoriqnoma_scanner",
            str(REPO / "local" / "fixtures" / "demo_shop"),
            "--base-url",
            SITE,
            "--out",
            str(out),
        ],
        check=True,
        capture_output=True,
        timeout=300,
    )
    return out.read_bytes()


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8000/",
        "http://169.254.169.254/latest/",
        "http://[::1]/",
        "http://2130706433/",
        "http://localhost/",
    ],
)
def test_ssrf_targets_are_refused(client: httpx.Client, url: str) -> None:
    """QM-5: private and metadata addresses never become jobs."""
    response = client.post("/api/jobs/", data={"mode": "B", "url": url, "role": "customer"})
    assert response.status_code == 400


def test_mode_a_prime_from_local_bundle(client: httpx.Client, tmp_path: Path) -> None:
    """QM-4: a bundle.zip in the local app's format, uploaded by hand."""
    bundle = build_bundle(tmp_path)
    with bundle.open("rb") as f:
        made = client.post(
            "/api/jobs/",
            data={"mode": "A_PRIME", "formats": "html,pdf,docx"},
            files={"bundle": ("bundle.zip", f, "application/zip")},
        )
    assert made.status_code == 201, made.text
    job = wait_done(client, made.json()["id"])
    assert job["status"] == "done", job["error"]
    names = {a["name"] for a in job["artifacts"]}
    assert {"manual.pdf", "manual.docx", "manual-html.zip"} <= names
    pdf = client.get(job["artifacts"][0]["url"])
    assert pdf.status_code in {200, 302}


@pytest.fixture(scope="module")
def mode_a(client: httpx.Client, tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    blueprint = local_blueprint(tmp_path_factory.mktemp("a"))
    made = client.post(
        "/api/jobs/",
        data={"mode": "A", "url": SITE, "role": "customer", "formats": "html,pdf,docx"},
        files={"blueprint": ("blueprint.json", blueprint, "application/json")},
    )
    assert made.status_code == 201, made.text
    return wait_done(client, made.json()["id"])


def test_mode_a_on_demo_shop(mode_a: dict[str, Any]) -> None:
    """QM-4/QM-5 (A) and NFR-4: the whole job within 20 minutes."""
    assert mode_a["status"] == "done", mode_a["error"]
    assert mode_a["stats"]["flows_verified"] >= 0.9 * mode_a["stats"]["flows_total"]
    assert mode_a["elapsed_s"] <= LIMIT_A_S
    assert float(mode_a["cost_usd"]) <= float(mode_a["budget_usd"])


def test_mode_b_coverage_against_a(client: httpx.Client, mode_a: dict[str, Any]) -> None:
    """QM-6: mode B reaches at least 70 % of mode A's coverage."""
    made = client.post(
        "/api/jobs/",
        data={
            "mode": "B",
            "url": SITE,
            "role": "customer",
            "role_label": "Mijoz",
            "formats": "html",
        },
    )
    assert made.status_code == 201, made.text
    job = wait_done(client, made.json()["id"])
    assert job["status"] == "done", job["error"]
    assert job["stats"]["coverage"] >= 0.7 * mode_a["stats"]["coverage"]


def test_cancel(client: httpx.Client) -> None:
    made = client.post("/api/jobs/", data={"mode": "B", "url": SITE, "role": "customer"})
    job_id = made.json()["id"]
    client.post(f"/api/jobs/{job_id}/cancel/")
    assert wait_done(client, job_id, limit_s=600)["status"] in {"cancelled", "done"}
