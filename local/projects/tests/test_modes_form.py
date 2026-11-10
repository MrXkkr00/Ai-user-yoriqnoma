"""The project form: the mailbox and the admin panel path may stay empty."""

from __future__ import annotations

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
