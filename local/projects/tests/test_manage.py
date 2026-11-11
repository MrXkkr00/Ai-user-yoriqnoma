"""Project form wording, named sign-in hosts, Uzbek run numbers, deleting runs and projects."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from projects.admin_access import roles_blueprint
from projects.forms import ProjectForm
from projects.models import BlueprintVersion, Project
from projects.services import _new_version, delete_project
from runs.models import Run
from runs.services import DeleteBlocked, delete_run, remove_run_folder
from yoriqnoma_core.provision.base import classify_role

pytestmark = pytest.mark.django_db

BASE_DATA = {
    "mode": "admin",
    "base_url": "https://app.example.uz/home?version=1",
    "environment": "staging",
    "language": "uz",
    "admin_login": "admin",
    "admin_password": "Parol-12345",
}


def test_folder_field_is_not_called_optional_where_it_is_required() -> None:
    form = ProjectForm()
    assert "ixtiyoriy" not in str(form.fields["source_dir"].label).lower()
    assert "blueprint.json" not in str(form.fields["source_dir"].help_text)


def test_project_names_are_unique_ignoring_case() -> None:
    Project.objects.create(name="Test", slug="test", base_url="https://a.example.uz")
    same = ProjectForm({**BASE_DATA, "name": "  test "})
    assert not same.is_valid() and "name" in same.errors
    assert ProjectForm({**BASE_DATA, "name": "Boshqa"}).is_valid()
    # editing a project does not clash with itself
    project = Project.objects.get(slug="test")
    own = ProjectForm({**BASE_DATA, "name": "Test"}, instance=project)
    assert own.is_valid(), own.errors


def test_sso_hosts_are_normalized_and_checked() -> None:
    form = ProjectForm(
        {**BASE_DATA, "name": "Sso", "sso_hosts": "Auth.Example.uz, https://sso.example.uz/x"}
    )
    assert form.is_valid(), form.errors
    assert form.cleaned_data["sso_hosts"] == "auth.example.uz, sso.example.uz"
    bad = ProjectForm({**BASE_DATA, "name": "Sso2", "sso_hosts": "auth.example.uz, nothost"})
    assert not bad.is_valid() and "sso_hosts" in bad.errors


def test_admin_options_carry_the_named_hosts() -> None:
    from projects.admin_access import admin_options

    project = Project.objects.create(
        name="S",
        slug="s",
        mode="admin",
        base_url="https://app.example.uz",
        sso_hosts="auth.example.uz",
    )
    assert admin_options(project, "r").trusted_hosts == ["auth.example.uz"]


def _project_with_run(
    tmp_path: Path, settings: Any, status: str = "done", pending_user: bool = False
) -> tuple[Project, Run, Path]:
    settings.MEDIA_ROOT = tmp_path
    project = Project.objects.create(
        name="Loyiha", slug="loyiha", mode="admin", base_url="https://app.example.uz"
    )
    roles = [classify_role("Menejer", "manager", "t", "role")]
    version = _new_version(project, roles_blueprint(project, roles), "admin", stats={})
    run_dir = tmp_path / "loyiha" / "20261111-000000-abcdef"
    (run_dir / "dist").mkdir(parents=True)
    (run_dir / "dist" / "manual.pdf").write_bytes(b"%PDF")
    if pending_user:
        user = {
            "role": "manager",
            "alias": "A",
            "login": "u@x.uz",
            "email": "u@x.uz",
            "remote_id": "5",
            "model": "user",
            "cleaned": False,
            "error": "",
        }
        (run_dir / "provision.json").write_text(json.dumps({"users": [user]}), encoding="utf-8")
    run = Run.objects.create(
        project=project,
        blueprint=version,
        output="full",
        status=status,
        run_dir=str(run_dir),
        stats={"flows_verified": 22, "coverage": 94.4, "cleanup": {"clean": True}},
    )
    return project, run, run_dir


def test_stats_are_shown_in_uzbek(tmp_path: Path, settings: Any) -> None:
    _, run, _ = _project_with_run(tmp_path, settings)
    shown = dict(run.stats_display)
    assert shown["Tasdiqlangan vazifalar"] == "22" and shown["Qamrov"] == "94,4%"
    assert "cleanup" not in shown and "flows_verified" not in shown


def test_delete_run_removes_row_and_folder(tmp_path: Path, settings: Any) -> None:
    _, run, run_dir = _project_with_run(tmp_path, settings)
    delete_run(run)
    assert not Run.objects.filter(pk=run.pk).exists() and not run_dir.exists()


def test_running_run_cannot_be_deleted(tmp_path: Path, settings: Any) -> None:
    _, running, folder = _project_with_run(tmp_path, settings, status="running")
    with pytest.raises(DeleteBlocked, match="bekor qiling"):
        delete_run(running)
    assert Run.objects.filter(pk=running.pk).exists() and folder.exists()


def test_leftover_test_users_on_the_site_block_deleting(tmp_path: Path, settings: Any) -> None:
    project, run, folder = _project_with_run(tmp_path, settings, status="failed", pending_user=True)
    with pytest.raises(DeleteBlocked, match="Tozalashni qayta urinish"):
        delete_run(run)
    with pytest.raises(DeleteBlocked, match="Ish"):
        delete_project(project)
    assert folder.exists() and Project.objects.filter(pk=project.pk).exists()


def test_never_deletes_outside_the_runs_folder(tmp_path: Path, settings: Any) -> None:
    settings.MEDIA_ROOT = tmp_path / "runs"
    (tmp_path / "runs").mkdir()
    outside = tmp_path / "keep"
    outside.mkdir()
    with pytest.raises(DeleteBlocked):
        remove_run_folder(outside)
    with pytest.raises(DeleteBlocked):
        remove_run_folder(tmp_path / "runs")
    assert outside.exists()


def test_delete_project_removes_everything(tmp_path: Path, settings: Any) -> None:
    project, run, run_dir = _project_with_run(tmp_path, settings)
    delete_project(project)
    assert not Project.objects.filter(pk=project.pk).exists()
    assert not Run.objects.filter(pk=run.pk).exists()
    assert not BlueprintVersion.objects.filter(project_id=project.pk).exists()
    assert not run_dir.exists() and not (tmp_path / "loyiha").exists()


def test_delete_views(client: Any, tmp_path: Path, settings: Any) -> None:
    project, run, run_dir = _project_with_run(tmp_path, settings)
    assert client.get(f"/projects/{project.pk}/").status_code == 200
    assert client.get(f"/runs/{run.pk}/").status_code == 200
    assert client.get(f"/runs/{run.pk}/delete/").status_code == 405  # only POST
    assert client.post(f"/runs/{run.pk}/delete/").status_code == 302
    assert not Run.objects.filter(pk=run.pk).exists() and not run_dir.exists()
    assert client.post(f"/projects/{project.pk}/delete/").status_code == 302
    assert not Project.objects.filter(pk=project.pk).exists()
