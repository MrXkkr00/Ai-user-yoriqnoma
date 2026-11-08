from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from django.test import Client

from projects.models import Project
from projects.services import create_project, scan_project, set_account
from runs import services
from runs.models import InputRequest, Run
from runs.services import RunError, answer_input, cancel_run, start_run
from yoriqnoma_core.writer.providers import FakeProvider
from yoriqnoma_schemas import Blueprint, CaptureRun, load_json

DEMO_SHOP = Path(__file__).resolve().parents[2] / "fixtures" / "demo_shop"
pytestmark = pytest.mark.django_db


@pytest.fixture
def project() -> Project:
    p = create_project(name="Demo", source_dir=str(DEMO_SHOP), base_url="http://127.0.0.1:8800")
    scan_project(p)
    return p


def test_blueprint_output_is_ready_at_once(project: Project) -> None:
    run = start_run(project, "blueprint")

    assert run.status == "done"
    bp = load_json(Path(run.run_dir) / "blueprint.json", Blueprint)
    assert bp.selectable_roles()
    assert (Path(run.run_dir) / "scan_report.md").is_file()
    assert any("«Yangi ish»" in e.message for e in run.events.all())


def test_role_must_be_selectable(project: Project) -> None:
    with pytest.raises(RunError):
        start_run(project, "full", "admin", enqueue=False)
    with pytest.raises(RunError):
        start_run(project, "full", "nobody", enqueue=False)


def test_cancel_and_input(project: Project) -> None:
    run = start_run(project, "bundle", "customer", enqueue=False)
    cancel_run(run)
    run.refresh_from_db()
    assert run.status == "cancelled" and run.cancel_requested

    req = InputRequest.objects.create(run=run, kind="sms_code", message="Kod?")
    answer_input(req, "123456")
    req.refresh_from_db()
    assert req.answered_at is not None and b"123456" not in bytes(req.value_enc or b"")


def test_run_page_files_and_path_traversal(client: Client, project: Project) -> None:
    run = start_run(project, "blueprint")
    page = client.get(f"/runs/{run.pk}/")

    assert page.status_code == 200 and "blueprint.json" in page.content.decode()
    assert client.get(f"/runs/{run.pk}/status/").status_code == 200
    assert client.get(f"/runs/{run.pk}/files/blueprint.json").status_code == 200
    for evil in ("../../secret.key", "..%2F..%2Fsecret.key", "../" * 6 + "Windows/win.ini"):
        assert client.get(f"/runs/{run.pk}/files/{evil}").status_code == 404


def test_update_run_keeps_the_scope_of_fakes(
    client: Client, project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T30: «Oldingi natija asosida yangilash» starts a linked run with the same fakes."""
    first = start_run(project, "full", "customer", formats=["html", "gif"], enqueue=False)
    with pytest.raises(services.RunError):
        services.update_run(first)  # not finished yet
    capture_dir = Path(first.run_dir) / "capture"
    capture_dir.mkdir(parents=True)
    (capture_dir / "capture.json").write_text(
        '{"run_id": "r1", "blueprint_hash": "h", "role": "customer", '
        '"base_url": "http://127.0.0.1:8800/", "environment": "staging", '
        '"started_at": "2026-11-08T00:00:00Z", "flows": [], "states": [], '
        '"firewall_log": [], "own_objects": {}, "pseudonym_scope": "r0"}',
        encoding="utf-8",
    )
    first.status = "done"
    first.save()
    queued: list[int] = []
    monkeypatch.setattr("runs.tasks.execute_run_task", queued.append)

    response = client.post(f"/runs/{first.pk}/update/")
    second = Run.objects.exclude(pk=first.pk).get(project=project, role="customer")

    assert response.status_code == 302 and response["Location"] == f"/runs/{second.pk}/"
    assert queued == [second.pk]
    assert second.previous == first and second.formats == ["html", "gif"]
    assert services.explore_options(second).pseudonym_scope == "r0"
    assert services.explore_options(second).device_scale_factor == 2.0
    assert services.explore_options(first).pseudonym_scope == ""


@pytest.mark.slow
@pytest.mark.django_db(transaction=True)  # the run writes from its own DB thread
@pytest.mark.parametrize("output", ["bundle", "full"])
def test_outputs_on_demo_shop(
    output: str, demo_shop_url: str, demo_shop_var: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = create_project(
        name=f"Demo {output}",
        source_dir=str(DEMO_SHOP),
        base_url=demo_shop_url.rstrip("/"),
        mailbox_kind="dir",
        mailbox_target=str(demo_shop_var / "mail"),
    )
    scan_project(project)
    set_account(project, "manager", "A", "manager@demo.local", "Manager12345")

    class Fake(FakeProvider):
        def check(self) -> None:
            return None

    monkeypatch.setattr(services, "provider_for", lambda run: Fake())
    run = start_run(project, output, "manager", formats=["html", "docx"])  # Huey immediate
    run.refresh_from_db()

    assert run.status == "done", run.error
    assert run.stats["flows_verified"] >= 0.9 * run.stats["flows_total"]
    base = Path(run.run_dir)
    if output == "bundle":
        with zipfile.ZipFile(base / "bundle.zip") as zf:
            CaptureRun.model_validate_json(zf.read("capture/capture.json"))
    else:
        assert (base / "dist" / "html" / "index.html").is_file()
        assert (base / "dist" / "manual.docx").is_file()
    assert Run.objects.get(pk=run.pk).events.filter(message="Tayyor.").exists()
