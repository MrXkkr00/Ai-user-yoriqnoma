"""QM-1 for a Django project (T29): roles, every user page, admin and staff parts excluded."""

from __future__ import annotations

import builtins
import io
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from yoriqnoma_scanner.api import ScanResult, scan
from yoriqnoma_scanner.detect import detect
from yoriqnoma_scanner.fs_guard import SafeFS
from yoriqnoma_schemas import Blueprint

ROLE_PAGES = {
    "guest": {"/", "/accounts/login/", "/accounts/signup/"},
    "customer": {"/tickets/", "/tickets/new/", "/tickets/:pk/", "/profile/"},
    "support": {
        "/tickets/",
        "/tickets/new/",
        "/tickets/:pk/",
        "/profile/",
        "/support/",
        "/support/tickets/:pk/reply/",
    },
}


def test_detects_django(demo_django_dir: Path) -> None:
    info = detect(SafeFS(demo_django_dir))

    assert "django" in info.stacks
    assert any(p.name == "django.po" for p in info.po_files)
    assert any(p.name == "base.html" for p in info.template_files)


def test_roles_from_the_user_model_choices(django_scan: ScanResult) -> None:
    bp = django_scan.blueprint
    kinds = {r.id: r.kind for r in bp.roles}

    assert kinds == {"guest": "guest", "customer": "role", "support": "role", "admin": "excluded"}
    customer = bp.role("customer")
    support = bp.role("support")
    assert customer is not None and customer.self_signup and customer.label == "Mijoz"
    assert support is not None and not support.self_signup and support.label == "Operator"
    assert len(bp.selectable_roles()) == 2


@pytest.mark.parametrize("role", sorted(ROLE_PAGES))
def test_every_page_of_each_role_is_found(django_scan: ScanResult, role: str) -> None:
    pages = [p for p in django_scan.blueprint.pages if p.kind == "page"]
    if role == "guest":
        found = {p.path for p in pages if p.access == "guest"}
    else:
        found = {p.path for p in pages if role in p.roles}

    assert found == ROLE_PAGES[role]


def test_admin_and_staff_paths_only_in_excluded(django_scan: ScanResult) -> None:
    bp = django_scan.blueprint
    kept = {p.path for p in bp.pages}
    excluded = {p.path for p in bp.excluded}

    assert not [p for p in kept if p.startswith(("/admin", "/panel"))]
    assert {"/admin/", "/panel/users/", "/panel/tickets/:pk/archive/"} <= excluded
    for flow in bp.flows:
        for step in flow.steps:
            assert not (step.path or "").startswith(("/admin", "/panel")), flow.id
    assert all(not n["path"].startswith(("/admin", "/panel")) for n in bp.nav)
    assert not any(f.role == "admin" for f in bp.flows)


def test_ticket_entity_statuses_and_owner(django_scan: ScanResult) -> None:
    ticket = django_scan.blueprint.entity("ticket")
    assert ticket is not None

    assert {"create", "list", "view", "close", "reply"} <= set(ticket.actions)
    reach = {s.value: sorted(s.reachable_by) for s in ticket.statuses}
    assert reach == {
        "open": ["customer", "support"],
        "answered": ["support"],
        "closed": ["customer", "support"],
        "archived": [],  # only staff archive tickets
    }
    labels = {s.value: s.label for s in ticket.statuses}
    assert labels["answered"] == "Javob berilgan"
    assert ticket.owner_field == "owner"
    assert ticket.status_field == "status"
    assert "contact_phone" in ticket.pii_fields


def test_account_and_role_flows(django_scan: ScanResult) -> None:
    flows = {f.id: f for f in django_scan.blueprint.flows}

    register = flows["customer.register"]
    fills = [s for s in register.steps if s.action == "fill"]
    filled = {(s.target.css or s.target.label) if s.target else None: s.data for s in fills}
    assert filled["[name='username']"] == "fake:username"
    assert filled["Telefon"] == "fake:phone_uz"
    assert filled["[name='password1']"] == filled["[name='password2']"] == "fake:password"
    assert register.steps[-1].target is not None
    assert register.steps[-1].target.name == "Ro'yxatdan o'tish"

    login = flows["support.login"]
    labels = [s.target.label if s.target else None for s in login.steps if s.action == "fill"]
    assert labels == ["Login", "Parol"]

    reply = flows["support.ticket.reply"]
    assert reply.steps[0].path == "/support/tickets/{own:ticket_id}/reply/"
    assert reply.needs_status == ["open"] and reply.sets_status == "answered"
    assert "customer.ticket.create" in reply.requires

    close = flows["customer.ticket.close"]
    assert close.needs_status == ["answered"]
    assert "support.ticket.reply" in close.requires
    assert close.title == "Murojaatni yopish"

    assert flows["customer.ticket.create"].title == "Murojaat yaratish"
    assert flows["customer.ticket.create"].creates == "ticket"
    assert flows["customer.profile_edit"].stage == "manage"
    assert flows["customer.logout"].steps[-1].target.name == "Chiqish"  # type: ignore[union-attr]


def test_forms_from_form_classes_and_templates(django_scan: ScanResult) -> None:
    forms = {f.api: f for f in django_scan.blueprint.forms}

    ticket = forms["POST /tickets/new/"]
    labels = {f.name: f.label for f in ticket.fields}
    assert labels == {
        "subject": "Mavzu",
        "body": "Murojaat matni",
        "contact_phone": "Aloqa telefoni",
    }
    phone = next(f for f in ticket.fields if f.name == "contact_phone")
    assert phone.rules is not None and "regex:" in phone.rules
    subject = next(f for f in ticket.fields if f.name == "subject")
    assert subject.rules == "max:120"
    reply = forms["POST /support/tickets/:pk/reply/"]
    assert reply.fields[0].type == "textarea" and reply.fields[0].rules == "min:2|max:2000"


def test_nav_is_translated_and_blueprint_round_trips(django_scan: ScanResult) -> None:
    bp = django_scan.blueprint
    nav = {n["path"]: n["label"] for n in bp.nav}

    assert nav["/tickets/"] == "Murojaatlarim"
    assert nav["/support/"] == "Murojaatlar navbati"
    assert Blueprint.model_validate_json(bp.model_dump_json()) == bp
    assert "registration/password_change_form.html" in django_scan.report_md


def test_scanning_demo_django_never_opens_env(
    monkeypatch: pytest.MonkeyPatch, demo_django_dir: Path, tmp_path: Path
) -> None:
    # The trap .env (fake secrets) is made here: env files never go into git.
    project = tmp_path / "demo_django"
    shutil.copytree(demo_django_dir, project, ignore=shutil.ignore_patterns("var", ".env"))
    (project / ".env").write_text("DJANGO_SECRET_KEY=fake-trap-value\n", encoding="utf-8")
    opened: list[str] = []
    real_open, real_io_open = builtins.open, io.open

    def make(real: Callable[..., Any]) -> Callable[..., Any]:
        def spy(file: Any, *args: Any, **kwargs: Any) -> Any:
            opened.append(str(file))
            return real(file, *args, **kwargs)

        return spy

    monkeypatch.setattr(builtins, "open", make(real_open))
    monkeypatch.setattr(io, "open", make(real_io_open))

    result = scan(project, "http://127.0.0.1:8810")

    assert opened
    names = {Path(p).name for p in opened}
    assert ".env" not in names and "db.sqlite3" not in names
    assert any(s.path == ".env" for s in result.skipped)
