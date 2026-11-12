"""Modes 2 and 3 on demo_shop (slow): test users through the admin, and nothing left.

demo_shop's admin (``/admin/users``) has a "new user" form and delete buttons, so the
plain-form adapter is used. After every run the site's user list must be exactly what
it was before: the test users and their orders, messages and reviews are gone.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import SecretBytes, SecretStr

from projects.models import Project
from projects.services import check_project, role_options, unique_slug
from runs import services
from runs.services import start_run
from yoriqnoma_core.explorer.options import ExploreOptions
from yoriqnoma_core.provision.base import AdminCredentials
from yoriqnoma_core.provision.provisioner import Provisioner
from yoriqnoma_local.keys import encrypt

pytestmark = pytest.mark.slow
DEMO_SHOP = Path(__file__).resolve().parents[2] / "fixtures" / "demo_shop"
ADMIN = ("admin@demo.local", "Admin12345")
MANAGER = ("manager@demo.local", "Manager12345")


def site_users(url: str) -> list[dict[str, Any]]:
    """The demo_shop user list, read the way its own admin reads it."""
    with httpx.Client(base_url=url, timeout=10) as client:
        client.post("/api/auth/login", json={"email": ADMIN[0], "password": ADMIN[1]})
        answer = client.get("/api/admin/users")
        answer.raise_for_status()
        users: list[dict[str, Any]] = answer.json()
        return users


def make_project(mode: str, url: str, var: Path) -> Project:
    name = f"Demo {mode}"
    return Project.objects.create(
        name=name,
        slug=unique_slug(name),
        mode=mode,
        source_dir=str(DEMO_SHOP) if mode == "code_admin" else "",
        base_url=url.rstrip("/"),
        mailbox_kind="dir",
        mailbox_target=str(var / "mail") if mode == "code_admin" else "",  # optional
        admin_login=ADMIN[0],
        admin_password_enc=encrypt(ADMIN[1]),
        admin_path="/admin" if mode == "code_admin" else "",  # mode 3: the tool finds it
    )


def test_provisioner_creates_and_removes_test_users(
    fresh_demo_shop: tuple[str, Path], tmp_path: Path
) -> None:
    url, _ = fresh_demo_shop
    before = {u["email"] for u in site_users(url)}
    opts = ExploreOptions(
        base_url=url,
        role="guest",
        allow_private=True,
        run_id="prov-test",
        pseudonym_key=SecretBytes(b"k" * 32),
    )
    prov = Provisioner(
        opts, AdminCredentials(ADMIN[0], SecretStr(ADMIN[1]), ""), tmp_path / "p.json"
    )

    async def go() -> tuple[list[str], list[str], Any, list[str]]:
        await prov.start()
        try:
            roles = await prov.list_roles()
            manager = await prov.find_role("manager", "Menejer")
            made = await prov.create_accounts(manager)
            during = [u["email"] for u in site_users(url)]
            report = await prov.cleanup({})
            return [r.id for r in roles if r.kind == "role"], list(made), report, during
        finally:
            await prov.close()

    roles, aliases, report, during = asyncio.run(go())

    assert {"customer", "manager", "courier"} <= set(roles)
    assert aliases == ["A", "B"]
    created = set(during) - before
    assert len(created) == 2 and all(e.endswith("@yoriqnoma.test") for e in created)
    assert report.clean and report.users_removed == 2
    assert {u["email"] for u in site_users(url)} == before
    assert not prov.guard.log  # nothing outside the rules was even tried


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("mode", ["code_admin", "admin"])
def test_admin_modes_run_and_leave_nothing(
    mode: str, fresh_demo_shop: tuple[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    url, var = fresh_demo_shop
    before = {(u["email"], u["role"]) for u in site_users(url)}
    monkeypatch.setattr(services, "provider_for", lambda run: None)  # no LLM: bundle only
    project = make_project(mode, url, var)

    check_project(project)
    project.refresh_from_db()
    cards = {o.id: o for o in role_options(project, _bp(project))}
    assert project.check_state == "done"
    assert cards["manager"].selectable and cards["manager"].admin_made
    assert "admin" not in cards or not cards["admin"].selectable

    run = start_run(project, "bundle", "manager")  # Huey immediate in tests
    run.refresh_from_db()

    assert run.status == "done", run.error
    assert run.stats["cleanup"]["clean"], run.stats["cleanup"]
    assert run.stats["cleanup"]["users_removed"] >= 2
    assert run.stats["flows_verified"] >= 1
    assert {(u["email"], u["role"]) for u in site_users(url)} == before
    if mode == "admin":
        assert run.blueprint.source == "discovered"
        pages = {p.path: p.roles for p in _bp(project).pages}
        assert "manager" in pages.get("/staff/orders", [])
        assert not any(p.startswith("/admin") for p in pages)


def _bp(project: Project) -> Any:
    from projects.services import raw_blueprint

    version = project.current_blueprint()
    assert version is not None
    return raw_blueprint(version)


@pytest.mark.django_db(transaction=True)
def test_account_mode_learns_site_as_the_given_role(
    fresh_demo_shop: tuple[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mode 4: link + the manager's own login; no admin, nothing created on the site."""
    from projects.forms import ProjectForm

    url, _ = fresh_demo_shop
    before = {(u["email"], u["role"]) for u in site_users(url)}
    monkeypatch.setattr(services, "provider_for", lambda run: None)
    form = ProjectForm(
        {
            "name": "Demo menejer",
            "mode": "account",
            "base_url": url.rstrip("/"),
            "environment": "staging",
            "language": "uz",
            "account_role": "Manager",
            "account_login": MANAGER[0],
            "account_password": MANAGER[1],
        }
    )
    assert form.is_valid(), form.errors
    project = form.save()
    check_project(project)

    run = start_run(project, "bundle", "manager")
    run.refresh_from_db()

    assert run.status == "done", run.error
    assert run.blueprint.source == "discovered"
    pages = {p.path: p.roles for p in _bp(project).pages}
    assert "manager" in pages.get("/staff/orders", [])
    assert not any(p.startswith("/admin") for p in pages)
    assert {(u["email"], u["role"]) for u in site_users(url)} == before
