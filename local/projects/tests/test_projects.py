from __future__ import annotations

import json
from pathlib import Path

import pytest
from django.test import Client

from projects.models import Project, ProjectAccount
from projects.services import (
    BlueprintError,
    accounts_for,
    create_project,
    effective_blueprint,
    role_options,
    scan_project,
    set_account,
    set_override,
    upload_blueprint,
)

DEMO_SHOP = Path(__file__).resolve().parents[2] / "fixtures" / "demo_shop"
EXAMPLE = (
    Path(__file__).resolve().parents[3] / "docs" / "schemas" / "examples" / "blueprint.example.json"
)
pytestmark = pytest.mark.django_db


@pytest.fixture
def project() -> Project:
    return create_project(
        name="Demo shop",
        source_dir=str(DEMO_SHOP),
        base_url="http://127.0.0.1:8800",
        mailbox_kind="dir",
    )


def test_scan_creates_a_current_version(project: Project) -> None:
    version = scan_project(project)
    bp, notes = effective_blueprint(version)

    assert version.is_current and version.stats["flows"] == len(bp.flows) and not notes
    assert Path(version.report_path).read_text(encoding="utf-8").startswith("# Skan hisoboti")
    options = {o.id: o for o in role_options(project, bp)}
    assert options["customer"].selectable and options["customer"].self_signup
    assert not options["admin"].selectable
    assert "test akkaunt berishi kerak" in options["manager"].account_note


def test_account_password_is_encrypted(project: Project) -> None:
    set_account(project, "manager", "A", "manager@demo.local", "Manager12345")
    acc = ProjectAccount.objects.get()

    assert b"Manager12345" not in bytes(acc.password_enc)
    assert accounts_for(project) == {"manager": {"A": ("manager@demo.local", "Manager12345")}}


def test_overrides_reduce_and_cannot_bring_back_excluded(project: Project) -> None:
    version = scan_project(project)
    set_override(version, "exclude_flows", "customer.order.create", True)
    bp, _ = effective_blueprint(version)
    ids = {f.id for f in bp.flows}

    assert "customer.order.create" not in ids and "customer.order.pay" not in ids
    assert {p.path for p in bp.excluded} >= {"/admin", "/admin/users"}
    with pytest.raises(BlueprintError):
        set_override(version, "include_pages", "/admin", True)
    set_override(version, "exclude_flows", "customer.order.create", False)
    assert "customer.order.create" in {f.id for f in effective_blueprint(version)[0].flows}


def test_upload_blueprint_validates_schema(project: Project) -> None:
    with pytest.raises(BlueprintError, match="sxemaga mos emas"):
        upload_blueprint(project, b'{"schema_version": "1.0", "project": "x"}')
    if EXAMPLE.exists():
        version = upload_blueprint(project, EXAMPLE.read_bytes())
        assert version.source == "upload"


def test_pages_and_forms(client: Client, project: Project) -> None:
    assert client.get("/").status_code == 200
    assert client.get("/projects/new/").status_code == 200
    assert client.get(f"/projects/{project.pk}/").status_code == 200
    bad = client.post(
        "/projects/new/",
        {
            "name": "x",
            "base_url": "ftp://x",
            "environment": "staging",
            "mailbox_kind": "dir",
            "language": "uz",
            "source_dir": "Z:/no/such/folder",
        },
    )
    assert bad.status_code == 200
    assert "topilmadi" in bad.content.decode() or "http" in bad.content.decode()
    resp = client.post(f"/projects/{project.pk}/scan/")
    assert resp.status_code == 302
    for tab in ("roles", "pages", "entities", "flows", "excluded", "report"):
        page = client.get(f"/projects/{project.pk}/blueprint/?tab={tab}")
        assert page.status_code == 200, tab
    assert client.get(f"/projects/{project.pk}/runs/new/").status_code == 200


def test_override_toggle_through_htmx(client: Client, project: Project) -> None:
    scan_project(project)
    resp = client.post(
        f"/projects/{project.pk}/blueprint/override/",
        {"kind": "exclude_flows", "key": "customer.message.create", "value": "1"},
        HTTP_HX_REQUEST="true",
    )

    assert resp.status_code == 200 and resp["HX-Refresh"] == "true"
    version = project.current_blueprint()
    assert version is not None
    assert version.overrides["exclude_flows"] == ["customer.message.create"]


def test_csrf_is_enforced(project: Project) -> None:
    strict = Client(enforce_csrf_checks=True)

    assert strict.post(f"/projects/{project.pk}/scan/").status_code == 403


def test_local_app_never_talks_to_the_server() -> None:
    """CLAUDE.md rule 10: no server URL, key or API path anywhere in the local app code."""
    root = Path(__file__).resolve().parents[2]
    code = []
    for folder in (
        "yoriqnoma_local",
        "projects",
        "runs",
        "settings_app",
        "evaluation",
        "templates",
    ):
        for path in (root / folder).rglob("*"):
            if path.suffix in {".py", ".html"} and "tests" not in path.parts:
                code.append(path.read_text(encoding="utf-8"))
    text = "\n".join(code)
    for needle in ("/api/jobs", "SERVER_URL", "server_url", "ANTHROPIC", "api_key"):
        assert needle not in text, needle
    assert "server" not in json.dumps([f.name for f in Project._meta.get_fields()])
