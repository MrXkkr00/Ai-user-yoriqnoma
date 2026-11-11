"""Jobs (T22, T24, T25): creation rules, limits, the pipeline, cancel, chores, pages."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from django.contrib.auth.models import User
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone

import jobs.pipeline
from domains.models import Domain
from jobs.budget import BudgetLimit, check_budget
from jobs.models import Artifact, InputRequest, Job, JobEvent
from jobs.services import JobError, JobRequest, answer_input, cancel_job, create_jobs
from jobs.tasks import cleanup_expired, reap_stuck_jobs
from jobs.tests.samples import named
from security.secrets import decrypt_json, decrypt_text
from yoriqnoma_core.writer.providers import FakeProvider

ACCOUNTS = {"manager": {"A": {"login": "menejer@shop.example.uz", "password": "Sinov-123"}}}


def job_a(user: User, blueprint: bytes, **kw: Any) -> list[Job]:
    req = JobRequest(
        mode="A",
        url="https://shop.example.uz/",
        roles=kw.pop("roles", ["manager"]),
        accounts=kw.pop("accounts", ACCOUNTS),
        blueprint=named(blueprint, "blueprint.json"),
        **kw,
    )
    return create_jobs(user, req)


@pytest.mark.django_db
def test_mode_a_job_is_created_with_encrypted_accounts(
    user: User, domain: Domain, blueprint_bytes: bytes
) -> None:
    (job,) = job_a(user, blueprint_bytes)

    assert job.status == "queued" and job.domain == domain and not job.passive
    assert job.role == "manager" and job.role_label
    assert b"Sinov-123" not in bytes(job.accounts_enc or b"")
    assert decrypt_json(job.accounts_enc) == ACCOUNTS
    assert job.blueprint.name.endswith("blueprint.json") and "uploads/" in job.blueprint.name
    assert job.expires_at and job.expires_at > timezone.now() + timedelta(days=29)


@pytest.mark.django_db
def test_one_job_per_role_and_admin_never(
    user: User, domain: Domain, blueprint_bytes: bytes
) -> None:
    jobs = job_a(user, blueprint_bytes, roles=["customer", "manager"], accounts={})
    assert sorted(j.role for j in jobs) == ["customer", "manager"]
    with pytest.raises(JobError, match="tanlab bo'lmaydi"):
        job_a(user, blueprint_bytes, roles=["admin"])
    with pytest.raises(JobError, match="adminga o'xshash"):
        create_jobs(user, JobRequest(mode="B", url="https://shop.example.uz/", roles=["admin"]))


@pytest.mark.django_db
def test_unknown_or_unverified_domain(
    user: User, unverified: Domain, blueprint_bytes: bytes
) -> None:
    with pytest.raises(JobError, match="Domenlar"):
        create_jobs(
            user,
            JobRequest(mode="B", url="https://other.example.uz/", roles=["customer"]),
        )
    (job,) = create_jobs(
        user, JobRequest(mode="B", url="https://unverified.example.uz/", roles=["customer"])
    )
    assert job.passive
    assert JobEvent.objects.filter(
        job=job, kind="log", payload__message__icontains="passiv"
    ).exists()


@pytest.mark.django_db
def test_ssrf_urls_are_refused_at_creation(user: User, blueprint_bytes: bytes) -> None:
    Domain.objects.create(owner=user, host="internal.example.uz", verified_at=timezone.now())
    for url in (
        "http://127.0.0.1:8800/",
        "https://internal.example.uz/",
        "http://169.254.169.254/",
    ):
        with pytest.raises(JobError, match="kirib bo'lmaydi"):
            create_jobs(user, JobRequest(mode="B", url=url, roles=["customer"]))


@pytest.mark.django_db
def test_wrong_file_for_mode(
    user: User, domain: Domain, bundle_path: Path, blueprint_bytes: bytes
) -> None:
    with pytest.raises(JobError, match="A' rejimi uchun"):
        create_jobs(
            user,
            JobRequest(
                mode="A",
                url="https://shop.example.uz/",
                roles=["customer"],
                blueprint=named(bundle_path.read_bytes(), "bundle.zip"),
            ),
        )
    with pytest.raises(JobError, match="A rejimi uchun"):
        create_jobs(
            user, JobRequest(mode="A_PRIME", bundle=named(blueprint_bytes, "blueprint.json"))
        )


@pytest.mark.django_db
@override_settings(
    YORIQNOMA_USER_DAILY_BUDGET_USD=5.0,
    YORIQNOMA_USER_MONTHLY_BUDGET_USD=8.0,
    YORIQNOMA_MONTHLY_BUDGET_USD=10.0,
)
def test_spending_limits(user: User, other_user: User, domain: Domain) -> None:
    check_budget(user, Decimal("5"))
    Job.objects.create(
        owner=user,
        mode="B",
        url="https://shop.example.uz/",
        role="customer",
        budget_usd=Decimal("4"),
        status="queued",
    )  # running: whole budget counts
    with pytest.raises(BudgetLimit, match="Bugungi"):
        check_budget(user, Decimal("2"))
    old = Job.objects.create(
        owner=user,
        mode="B",
        url="https://shop.example.uz/",
        role="c",
        budget_usd=Decimal("9"),
        cost_usd=Decimal("3.5"),
        status="done",
    )
    Job.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=1))
    with pytest.raises(BudgetLimit, match="Shu oydagi"):
        check_budget(user, Decimal("1"))  # 4 + 3.5 + 1 > 8 this month
    Job.objects.create(
        owner=other_user,
        mode="B",
        url="https://x.uz/",
        role="c",
        budget_usd=Decimal("2"),
        cost_usd=Decimal("2"),
        status="done",
    )
    with pytest.raises(BudgetLimit, match="Serverning"):
        check_budget(other_user, Decimal("1.5"))  # 4 + 3.5 + 2 + 1.5 > 10 on the server
    with pytest.raises(BudgetLimit):
        check_budget(user, Decimal("0"))
    with pytest.raises(BudgetLimit, match="oshmasligi"):
        check_budget(user, Decimal("500"))


@pytest.mark.django_db(transaction=True)
def test_mode_a_prime_pipeline_end_to_end(
    user: User,
    bundle_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    django_capture_on_commit_callbacks: Any,
) -> None:
    """A' (QM-4): the local app's bundle -> writer (fake Claude) -> renderer -> artifacts."""
    monkeypatch.setattr(
        jobs.pipeline, "provider_factory", lambda job, run_dir, progress: FakeProvider()
    )
    req = JobRequest(
        mode="A_PRIME",
        formats=["html", "docx"],
        bundle=named(bundle_path.read_bytes(), "bundle.zip"),
    )
    (job,) = create_jobs(user, req)
    job.refresh_from_db()

    assert job.status == "done", job.error
    names = set(job.artifacts.values_list("name", flat=True))
    assert {"manual-html.zip", "manual.docx", "manual.json", "coverage_report.html"} <= names
    kinds = list(job.events.values_list("kind", flat=True))
    statuses = [e.payload["status"] for e in job.events.filter(kind="status")]
    assert statuses[0] == "queued" and statuses[-1] == "done"
    assert "writing" in statuses and "rendering" in statuses and "artifact" in kinds
    assert job.accounts_enc is None and job.finished_at is not None
    assert not jobs.pipeline.run_dir_for(job).exists()  # the worker's folder is removed
    artifact = job.artifacts.get(name="manual.docx")
    assert artifact.size > 1000 and len(artifact.sha256) == 64


@pytest.mark.django_db(transaction=True)
def test_mode_a_pipeline_with_stub_explorer(
    user: User,
    domain: Domain,
    blueprint_bytes: bytes,
    bundle_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A: options given to the explorer (no private addresses, passwords, mailbox)."""
    import zipfile

    seen: dict[str, Any] = {}

    async def fake_explore(
        bp: Any, run_dir: Path, opts: Any, human: Any, progress: Any, cancel: Any
    ) -> Any:
        seen["opts"] = opts
        seen["role"] = bp.role(opts.role).label
        progress.stage("explore", 1)
        progress.log("info", f"login {opts.accounts['manager']['A'].password}")
        with zipfile.ZipFile(bundle_path) as zf:
            for name in zf.namelist():
                if name.startswith("capture/"):
                    target = run_dir / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(zf.read(name))
        from yoriqnoma_schemas import CaptureRun, load_json, save_json

        save_json(run_dir / "blueprint.json", bp)  # as run_explore does

        return load_json(run_dir / "capture" / "capture.json", CaptureRun)

    monkeypatch.setattr(jobs.pipeline, "explore", fake_explore)
    monkeypatch.setattr(jobs.pipeline, "provider_factory", lambda *a: FakeProvider())
    monkeypatch.setattr(
        jobs.pipeline, "fetch_robots", lambda url: __import__("security.robots").robots.Robots()
    )
    (job,) = job_a(user, blueprint_bytes, formats=["html"])
    jobs.pipeline.execute(job.pk)  # ran already on commit; a second call changes nothing
    job.refresh_from_db()

    opts = seen["opts"]
    assert job.status == "done", job.error
    assert opts.allow_private is False and opts.passive is False
    assert opts.mailbox_kind == "mailpit" and opts.mail_domain == "inbox.yoriqnoma.test"
    assert opts.accounts["manager"]["A"].password.get_secret_value() == "Sinov-123"
    assert "Sinov-123" not in repr(opts)
    assert job.stats["flows_total"] >= 1


@pytest.mark.django_db
def test_cancel_and_input(user: User, domain: Domain, blueprint_bytes: bytes) -> None:
    (job,) = job_a(user, blueprint_bytes)
    request = InputRequest.objects.create(job=job, kind="sms_code", message="SMS kodi")
    answer_input(job, request.pk, " 123456 ")
    request.refresh_from_db()
    assert decrypt_text(request.value_enc) == "123456" and request.answered_at
    with pytest.raises(JobError, match="allaqachon"):
        answer_input(job, request.pk, "1")

    cancel_job(job)
    job.refresh_from_db()
    assert job.status == "cancelled" and job.cancel_requested and job.accounts_enc is None
    assert jobs.pipeline.execute(job.pk).status == "cancelled"


@pytest.mark.django_db
def test_cleanup_and_reaper(user: User, domain: Domain, blueprint_bytes: bytes) -> None:
    (job,) = job_a(user, blueprint_bytes)
    from django.core.files.base import ContentFile

    art = Artifact(job=job, name="manual.pdf", size=3, sha256="0" * 64)
    art.file.save("manual.pdf", ContentFile(b"pdf"), save=True)
    path = Path(art.file.path)
    Job.objects.filter(pk=job.pk).update(
        status="done", expires_at=timezone.now() - timedelta(days=1)
    )
    assert cleanup_expired() == 1
    assert not path.exists() and not Artifact.objects.filter(job=job).exists()
    job.refresh_from_db()
    assert Job.objects.filter(pk=job.pk).exists() and not job.blueprint  # row kept for costs

    stuck = Job.objects.create(
        owner=user,
        mode="B",
        url="https://shop.example.uz/",
        role="c",
        budget_usd=1,
        status="exploring",
        started_at=timezone.now() - timedelta(days=1),
    )
    assert reap_stuck_jobs() == 1
    stuck.refresh_from_db()
    assert stuck.status == "failed" and "osilib" in stuck.error


# --- web pages ----------------------------------------------------------------------------


@pytest.mark.django_db
def test_pages_need_login_and_show_only_own_jobs(
    user: User, other_user: User, domain: Domain, blueprint_bytes: bytes
) -> None:
    (job,) = job_a(user, blueprint_bytes)
    anonymous = Client()
    assert anonymous.get(reverse("jobs:list")).status_code == 302
    client = Client()
    client.force_login(user)
    for name, args in [
        ("jobs:list", []),
        ("jobs:new", []),
        ("jobs:detail", [job.pk]),
        ("jobs:status", [job.pk]),
        ("jobs:events", [job.pk]),
    ]:
        assert client.get(reverse(name, args=args)).status_code == 200, name
    stranger = Client()
    stranger.force_login(other_user)
    assert stranger.get(reverse("jobs:detail", args=[job.pk])).status_code == 404
    assert stranger.post(reverse("jobs:cancel", args=[job.pk])).status_code == 404
    page = client.get(reverse("jobs:new")).content.decode()
    assert "haqiqiy odamning ma'lumotlarini yozmang" in page


@pytest.mark.django_db
def test_new_job_form_and_role_options(user: User, domain: Domain, blueprint_bytes: bytes) -> None:
    client = Client()
    client.force_login(user)
    roles = client.post(
        reverse("jobs:roles"), {"blueprint": named(blueprint_bytes, "blueprint.json")}
    )
    html = roles.content.decode()
    assert "administratordan boshqa 3 ta rol" in html
    assert 'value="admin"' in html and "disabled" in html
    bad = client.post(
        reverse("jobs:new"), {"mode": "B", "url": "https://shop.example.uz/", "role_b": "admin"}
    )
    assert bad.status_code == 400 and "adminga" in bad.content.decode()
    ok = client.post(
        reverse("jobs:new"),
        {
            "mode": "A",
            "url": "https://shop.example.uz/",
            "role": ["customer"],
            "formats": ["html"],
            "budget_usd": "2",
            "blueprint": named(blueprint_bytes, "blueprint.json"),
        },
    )
    job = Job.objects.get(owner=user)
    assert ok.status_code == 302 and ok["Location"] == reverse("jobs:detail", args=[job.pk])
    assert job.budget_usd == Decimal("2.00") and job.formats == ["html"]


@pytest.mark.django_db
def test_events_partial_and_downloads(
    user: User, other_user: User, domain: Domain, blueprint_bytes: bytes
) -> None:
    (job,) = job_a(user, blueprint_bytes)
    first = job.events.last()
    assert first is not None
    JobEvent.objects.create(job=job, kind="log", payload={"level": "info", "message": "salom"})
    client = Client()
    client.force_login(user)
    part = client.get(reverse("jobs:events", args=[job.pk]) + f"?after={first.pk}").content.decode()
    assert "salom" in part and 'hx-swap-oob="true"' in part
    from django.core.files.base import ContentFile

    art = Artifact(job=job, name="manual.pdf", size=3, sha256="0" * 64)
    art.file.save("manual.pdf", ContentFile(b"pdf"), save=True)
    response = client.get(reverse("jobs:artifact", args=[job.pk, "manual.pdf"]))
    assert response.status_code == 200 and b"".join(response.streaming_content) == b"pdf"  # type: ignore[attr-defined]
    stranger = Client()
    stranger.force_login(other_user)
    assert stranger.get(reverse("jobs:artifact", args=[job.pk, "manual.pdf"])).status_code == 404


@pytest.mark.django_db
def test_csrf_is_enforced(user: User) -> None:
    client = Client(enforce_csrf_checks=True)
    client.force_login(user)
    assert client.post(reverse("domains:list"), {"host": "shop.example.uz"}).status_code == 403


@pytest.mark.django_db
def test_unverified_domain_gives_passive_explorer_options(user: User, unverified: Domain) -> None:
    (job,) = create_jobs(
        user, JobRequest(mode="B", url="https://unverified.example.uz/", roles=["customer"])
    )
    opts = jobs.pipeline.explore_options(job)
    assert opts.passive is True and opts.allow_private is False


@pytest.mark.django_db
def test_mode_b_without_account_warns_about_staff_roles(user: User, domain: Domain) -> None:
    (job,) = create_jobs(
        user, JobRequest(mode="B", url="https://shop.example.uz/", roles=["manager"])
    )
    assert job.events.filter(kind="log", payload__message__icontains="xodim roli").exists()
    (given,) = create_jobs(
        user,
        JobRequest(mode="B", url="https://shop.example.uz/", roles=["manager"], accounts=ACCOUNTS),
    )
    assert not given.events.filter(kind="log", payload__message__icontains="xodim roli").exists()
