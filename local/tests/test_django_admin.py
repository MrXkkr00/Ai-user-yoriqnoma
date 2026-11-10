"""The Django admin adapter on demo_django (slow): roles, test users, their tickets, cleanup.

demo_django runs as its own process (``manage.py runserver``) with a temporary database.
The test user of the support role is made through ``/admin/``, a ticket of a test
customer is removed through the admin, then both users; the seed data stays as it was.
"""

from __future__ import annotations

import asyncio
import os
import socket
import subprocess
import sys
import time
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest
from pydantic import SecretBytes, SecretStr

from yoriqnoma_core.explorer.options import ExploreOptions
from yoriqnoma_core.provision.base import AdminCredentials, CleanupReport
from yoriqnoma_core.provision.django_admin import DjangoAdminAdapter
from yoriqnoma_core.provision.provisioner import Provisioner

pytestmark = pytest.mark.slow
DEMO = Path(__file__).resolve().parents[1] / "fixtures" / "demo_django"


def _manage(env: dict[str, str], *args: str) -> str:
    out = subprocess.run(
        [sys.executable, "manage.py", *args],
        cwd=DEMO,
        env=env,
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )
    return out.stdout


@pytest.fixture(scope="module")
def demo_django(tmp_path_factory: pytest.TempPathFactory) -> Iterator[tuple[str, dict[str, str]]]:
    db = tmp_path_factory.mktemp("demo_django") / "db.sqlite3"
    env = {**os.environ, "DEMO_DJANGO_DB": str(db), "DJANGO_SETTINGS_MODULE": "config.settings"}
    _manage(env, "migrate", "--noinput")
    _manage(env, "seed")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    proc = subprocess.Popen(
        [sys.executable, "manage.py", "runserver", f"127.0.0.1:{port}", "--noreload"],
        cwd=DEMO,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}/"
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(url + "admin/login/", timeout=1)
                break
            except OSError:
                time.sleep(0.3)
        yield url, env
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def _count(env: dict[str, str], code: str) -> str:
    return _manage(env, "shell", "-c", code).strip().splitlines()[-1]  # last line: the answer


def test_django_admin_provisioning(demo_django: tuple[str, dict[str, str]], tmp_path: Path) -> None:
    url, env = demo_django
    users_before = _count(env, "from helpdesk.models import User; print(User.objects.count())")
    opts = ExploreOptions(
        base_url=url,
        role="guest",
        allow_private=True,
        run_id="dj-test",
        pseudonym_key=SecretBytes(b"k" * 32),
    )
    prov = Provisioner(
        opts, AdminCredentials("admin", SecretStr("Admin-pass-1"), "/admin/"), tmp_path / "p.json"
    )

    async def go() -> tuple[list[tuple[str, str]], str, CleanupReport]:
        await prov.start()
        try:
            assert isinstance(prov.adapter, DjangoAdminAdapter)
            roles: list[tuple[str, str]] = [(r.id, str(r.kind)) for r in await prov.list_roles()]
            support = await prov.find_role("support", "Operator")
            made = await prov.create_accounts(support, ("A",))
            check = _count(
                env,
                "from helpdesk.models import User; "
                f"u = User.objects.get(username='{made['A'].login}'); "
                "print(u.role, u.is_staff, u.is_superuser, u.check_password("
                f"'{made['A'].password.get_secret_value()}'))",
            )
            report = await prov.cleanup({})
            return roles, check, report
        finally:
            await prov.close()

    roles, check, report = asyncio.run(go())

    assert ("support", "role") in roles and ("customer", "role") in roles
    assert ("admin", "excluded") in roles  # «Administrator» is never offered
    assert check == "support False False True"  # the right role, no admin rights, can sign in
    assert report.clean and report.users_removed == 1
    assert _count(env, "from helpdesk.models import User; print(User.objects.count())") == (
        users_before
    )
    assert not prov.guard.log
