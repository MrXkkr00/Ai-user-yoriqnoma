"""The project form: the mailbox and the admin panel path may stay empty."""

from __future__ import annotations

from typing import Any

import pytest

from projects.forms import ProjectForm

pytestmark = pytest.mark.django_db


def test_admin_mode_needs_only_link_and_admin_login() -> None:
    form = ProjectForm(
        {
            "name": "Sayt",
            "mode": "admin",
            "base_url": "https://staging.shop.example.uz",
            "environment": "staging",
            "language": "uz",
            "admin_login": "admin@shop.example.uz",
            "admin_password": "Admin-parol-1",
        }
    )
    assert form.is_valid(), form.errors
    project = form.save(commit=False)
    assert project.admin_path == "" and project.mailbox_target == ""
    assert project.mailbox_kind == "dir"


def test_code_mode_needs_a_folder_and_admin_mode_a_password() -> None:
    no_code = ProjectForm(
        {
            "name": "x",
            "mode": "code",
            "base_url": "http://127.0.0.1:8800",
            "environment": "staging",
            "language": "uz",
        }
    )
    assert not no_code.is_valid() and "source_dir" in no_code.errors
    no_password = ProjectForm(
        {
            "name": "x",
            "mode": "admin",
            "base_url": "http://127.0.0.1:8800",
            "environment": "staging",
            "language": "uz",
            "admin_login": "a",
        }
    )
    assert not no_password.is_valid() and "admin_password" in no_password.errors


def test_mode_three_pages_and_no_blueprint_output(client: Any) -> None:
    """Mode 3 after «Tekshirish»: roles only; pages open, "blueprint" output is refused."""
    from projects.admin_access import roles_blueprint
    from projects.models import Project
    from projects.services import _new_version, role_options
    from runs.services import RunError, start_run
    from yoriqnoma_core.provision.base import classify_role

    project = Project.objects.create(
        name="Kodsiz",
        slug="kodsiz",
        mode="admin",
        base_url="https://shop.example.uz",
        admin_login="admin",
    )
    roles = [
        classify_role(label, value, "test", "role")
        for label, value in [("Menejer", "manager"), ("Administrator", "admin")]
    ]
    _new_version(
        project,
        roles_blueprint(project, roles),
        "admin",
        stats={"admin_roles": {"manager": "manager"}},
    )

    cards = {o.id: o for o in role_options(project, roles_blueprint(project, roles))}
    assert cards["manager"].admin_made and not cards["admin"].selectable
    for url in (
        f"/projects/{project.pk}/",
        f"/projects/{project.pk}/blueprint/",
        f"/projects/{project.pk}/runs/new/",
        f"/projects/{project.pk}/edit/",
    ):
        assert client.get(url).status_code == 200, url
    with pytest.raises(RunError, match="Kodsiz rejimda"):
        start_run(project, "blueprint")


def _account_form(**extra: str) -> dict[str, str]:
    data = {
        "name": "Menejer yo'riqnomasi",
        "mode": "account",
        "base_url": "https://shop.example.uz",
        "environment": "staging",
        "language": "uz",
        "account_role": "Sotuv menejeri",
        "account_login": "menejer@shop.example.uz",
        "account_password": "Parol-12345",
    }
    data.update(extra)
    return data


def test_account_mode_saves_one_encrypted_account_and_one_role(client: Any) -> None:
    from projects.models import Project
    from projects.services import accounts_for, role_options
    from runs.services import RunError, start_run

    form = ProjectForm(_account_form())
    assert form.is_valid(), form.errors
    project = form.save()
    assert project.admin_login == "" and project.account_role == "Sotuv menejeri"
    given = accounts_for(project)
    assert list(given) == ["sotuv_menejeri"] and given["sotuv_menejeri"]["A"][1] == "Parol-12345"

    assert client.post(f"/projects/{project.pk}/scan/").status_code == 302
    version = Project.objects.get(pk=project.pk).current_blueprint()
    assert version is not None
    from projects.services import effective_blueprint

    bp, _ = effective_blueprint(version)
    options = {o.id: o for o in role_options(project, bp)}
    assert options["sotuv_menejeri"].selectable and options["sotuv_menejeri"].has_account
    with pytest.raises(RunError, match="Kodsiz rejimda"):
        start_run(project, "blueprint")

    # editing with an empty password keeps the old one; another role replaces the account
    again = ProjectForm(_account_form(account_password="", account_role="Kuryer"), instance=project)
    assert again.is_valid(), again.errors
    project = again.save()
    assert accounts_for(project) == {"kuryer": {"A": ("menejer@shop.example.uz", "Parol-12345")}}


def test_account_mode_rejects_admin_like_roles_and_missing_fields() -> None:
    admin_like = ProjectForm(_account_form(account_role="Administrator"))
    assert not admin_like.is_valid() and "account_role" in admin_like.errors
    empty = ProjectForm(_account_form(account_login="", account_password=""))
    assert not empty.is_valid()
    assert {"account_login", "account_password"} <= set(empty.errors)
