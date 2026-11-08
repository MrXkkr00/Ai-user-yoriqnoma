"""REST API (T22, ARCHITECTURE §7.4): session + CSRF only, owners only (TZ SEC-15)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework.test import APIClient

import domains.services
from domains.models import Domain
from jobs.models import InputRequest, Job, JobEvent
from jobs.tests.samples import named

pytestmark = pytest.mark.django_db


@pytest.fixture
def api(user: User) -> APIClient:
    client = APIClient()
    client.force_authenticate(user)
    return client


def test_anonymous_gets_nothing() -> None:
    client = APIClient()
    assert client.get("/api/jobs/").status_code == 403
    assert client.get("/api/domains/").status_code == 403


def test_domains(api: APIClient, user: User, monkeypatch: pytest.MonkeyPatch) -> None:
    made = api.post("/api/domains/", {"host": "https://Shop.Example.uz/"}, format="json")
    assert made.status_code == 201 and made.data["host"] == "shop.example.uz"
    assert set(made.data["methods"]) == {"wellknown", "meta", "dns"}
    assert api.post("/api/domains/", {"host": "127.0.0.1"}, format="json").status_code == 400
    monkeypatch.setattr(domains.services, "check_methods", lambda d, *a, **k: "wellknown")
    checked = api.post(f"/api/domains/{made.data['id']}/verify/")
    assert checked.status_code == 200 and checked.data["method"] == "wellknown"


def test_create_job_and_read_it(
    api: APIClient, user: User, domain: Domain, blueprint_bytes: bytes
) -> None:
    accounts = {"manager": {"A": {"login": "m@shop.example.uz", "password": "Sinov-1"}}}
    made = api.post(
        "/api/jobs/",
        {
            "mode": "A",
            "url": "https://shop.example.uz/",
            "role": "manager",
            "formats": "html,pdf",
            "accounts": json.dumps(accounts),
            "budget_usd": "2.50",
            "blueprint": named(blueprint_bytes, "blueprint.json"),
        },
        format="multipart",
    )
    assert made.status_code == 201, made.data
    job = Job.objects.get(pk=made.data["id"])
    assert job.source == "api" and job.formats == ["html", "pdf"]
    assert made.data["web_url"] == reverse("jobs:detail", args=[job.pk])
    detail = api.get(f"/api/jobs/{job.pk}/").data
    assert detail["role"] == "manager" and "accounts_enc" not in detail
    assert "Sinov-1" not in json.dumps(detail, default=str)


def test_create_job_errors(api: APIClient, domain: Domain) -> None:
    bad = api.post("/api/jobs/", {"mode": "B", "url": "http://127.0.0.1/", "role": "customer"})
    assert bad.status_code == 400 and "kirib bo'lmaydi" in bad.data["detail"]
    assert api.post("/api/jobs/", {"mode": "Z"}).status_code == 400
    assert api.post("/api/jobs/", {"mode": "B", "accounts": "{bad"}).status_code == 400


def test_events_input_cancel(api: APIClient, user: User, domain: Domain) -> None:
    job = Job.objects.create(
        owner=user,
        mode="B",
        url="https://shop.example.uz/",
        role="customer",
        budget_usd=1,
        status="waiting_input",
    )
    first = JobEvent.objects.create(job=job, kind="status", payload={"status": "queued"})
    JobEvent.objects.create(job=job, kind="log", payload={"level": "info", "message": "x"})
    events = api.get(f"/api/jobs/{job.pk}/events/?after={first.pk}").data
    assert [e["kind"] for e in events] == ["log"]
    request = InputRequest.objects.create(job=job, kind="sms_code", message="kod")
    assert (
        api.post(
            f"/api/jobs/{job.pk}/input/", {"request_id": request.pk, "value": "1234"}, format="json"
        ).status_code
        == 200
    )
    assert api.post(f"/api/jobs/{job.pk}/cancel/").data["cancel_requested"] is True


def test_other_users_objects_are_404(api: APIClient, other_user: User) -> None:
    job = Job.objects.create(
        owner=other_user, mode="B", url="https://x.uz/", role="c", budget_usd=1
    )
    domain = Domain.objects.create(owner=other_user, host="other.example.uz")
    for method, url in [
        ("get", f"/api/jobs/{job.pk}/"),
        ("get", f"/api/jobs/{job.pk}/events/"),
        ("post", f"/api/jobs/{job.pk}/cancel/"),
        ("get", f"/api/jobs/{job.pk}/artifacts/manual.pdf/"),
        ("get", f"/api/domains/{domain.pk}/"),
        ("post", f"/api/domains/{domain.pk}/verify/"),
    ]:
        assert getattr(api, method)(url).status_code == 404, url
    assert api.get("/api/jobs/").data == []


def test_session_api_needs_csrf(user: User) -> None:
    client = APIClient(enforce_csrf_checks=True)
    client.force_login(user)
    response = client.post("/api/domains/", {"host": "shop.example.uz"}, format="json")
    assert response.status_code == 403 and "CSRF" in str(response.data)


def test_artifact_download(api: APIClient, user: User, tmp_path: Path) -> None:
    from django.core.files.base import ContentFile

    from jobs.models import Artifact

    job = Job.objects.create(
        owner=user, mode="B", url="https://x.uz/", role="c", budget_usd=1, status="done"
    )
    art = Artifact(job=job, name="manual.docx", size=4, sha256="0" * 64)
    art.file.save("manual.docx", ContentFile(b"docx"), save=True)
    response: Any = api.get(f"/api/jobs/{job.pk}/artifacts/manual.docx/")
    assert response.status_code == 200 and b"".join(response.streaming_content) == b"docx"
    listed = api.get(f"/api/jobs/{job.pk}/").data["artifacts"]
    assert listed[0]["url"].endswith("/artifacts/manual.docx/")
