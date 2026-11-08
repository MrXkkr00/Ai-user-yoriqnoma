"""Slow tests on demo_shop (QM-4..QM-6 without Docker and without Claude).

demo_shop runs as its own process from the local folder; the blueprint for mode A is made
by the local app's scanner in its own process too (as a person would, T25) and uploaded
here. The writer is ``FakeProvider``; the explorer and the scout are real (Playwright).
The test site is on 127.0.0.1, so these tests allow exactly that host
(``YORIQNOMA_PRIVATE_ALLOWLIST``); production never does.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest
from django.contrib.auth.models import User
from django.test import override_settings
from django.utils import timezone

import jobs.pipeline
import scout.discover
from conftest import _local_python
from domains.models import Domain
from jobs.models import Job
from jobs.services import JobRequest, create_jobs
from jobs.tests.samples import named
from yoriqnoma_core.writer.providers import FakeProvider
from yoriqnoma_core.writer.providers.base import LLMRequest, LLMResult

pytestmark = [pytest.mark.slow, pytest.mark.django_db(transaction=True)]


@pytest.fixture
def site(demo_shop: tuple[str, Path], monkeypatch: pytest.MonkeyPatch) -> Any:
    url, var = demo_shop
    original = jobs.pipeline.explore_options

    def options(job: Job) -> Any:
        # demo_shop writes its mail to <var>/mail (no Mailpit on a developer machine)
        return original(job).model_copy(
            update={"mailbox_kind": "dir", "mailbox_target": str(var / "mail")}
        )

    monkeypatch.setattr(jobs.pipeline, "explore_options", options)
    monkeypatch.setattr(scout.discover, "explore_options", options)
    monkeypatch.setattr(jobs.pipeline, "provider_factory", lambda *a: FakeProvider())
    with override_settings(YORIQNOMA_PRIVATE_ALLOWLIST=["127.0.0.1"], YORIQNOMA_SCOUT_MAX_PAGES=30):
        yield url, var


@pytest.fixture
def owner(db: Any) -> User:
    user = User.objects.create_user("egasi", "egasi@example.uz", "Parol-12345!")
    Domain.objects.create(owner=user, host="127.0.0.1", verified_at=timezone.now(), method="dns")
    return user


class ScriptedAgent:
    """Agent answers in order (Claude's place in the test); then gives up."""

    name = "scripted"

    def __init__(self, answers: list[dict[str, Any]]) -> None:
        self.answers = answers
        self.requests: list[LLMRequest] = []

    def capabilities(self) -> set[str]:
        return {"vision", "json_schema"}

    async def generate(self, req: LLMRequest, schema: type[Any]) -> LLMResult[Any]:
        self.requests.append(req)
        data = (
            self.answers.pop(0)
            if self.answers and req.task == "agent_step"
            else (
                {"tool": "give_up", "reason": "tamom"}
                if req.task == "agent_step"
                else {"kind": "other"}
            )
        )
        return LLMResult(
            data=schema.model_validate(data),
            model="scripted",
            input_tokens=1,
            output_tokens=1,
            cost_usd=0.0,
            latency_s=0.0,
        )


def test_mode_b_scout_on_demo_shop(
    site: Any, owner: User, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    url, _ = site
    agent = ScriptedAgent(
        [
            {"tool": "goto", "path": "/app/orders"},
            {
                "tool": "finish_flow",
                "title": "Buyurtmalarni ko'rish",
                "stage": "core",
                "entity": "order",
                "action": "list",
            },
            {"tool": "goto", "path": "/admin/users"},  # refused by the policy
            {"tool": "give_up", "reason": "boshqa vazifa yo'q"},
        ]
    )
    monkeypatch.setattr(scout.discover, "provider_factory", lambda job, kit, progress: agent)
    job = Job.objects.create(
        owner=owner,
        mode="B",
        url=url,
        role="customer",
        role_label="Mijoz",
        budget_usd=1,
        formats=["html"],
    )
    from jobs.sinks import DbThread, JobCancelToken, JobHumanInput, JobProgressSink

    db = DbThread()
    try:
        import asyncio

        bp = asyncio.run(
            scout.discover.discover(
                job,
                tmp_path,
                JobHumanInput(job.pk, db),
                JobProgressSink(job.pk, db),
                JobCancelToken(job.pk, db),
            )
        )
    finally:
        db.close()

    access = {p.path: p.access for p in bp.pages}
    log = [e.payload.get("message") for e in job.events.filter(kind="log")]
    assert access.get("/catalog") == "guest", log
    assert any(p.startswith("/app/") and a == "roles" for p, a in access.items()), (access, log)
    assert not any(p.startswith("/admin") for p in access)  # admin: excluded only
    assert {r.id: r.kind for r in bp.roles}["admin"] == "excluded"
    ids = {f.id for f in bp.flows}
    assert {"customer.register", "customer.login"} <= ids
    agent_flows = [f for f in bp.flows if f.source == "agent"]
    assert agent_flows and agent_flows[0].title == "Buyurtmalarni ko'rish"
    assert all("/admin" not in (s.path or "") for f in bp.flows for s in f.steps)
    som = [r for r in agent.requests if r.task == "agent_step"]
    assert som and all(p.is_relative_to(tmp_path) for r in som for p in r.images)


def _local_blueprint(url: str, out: Path) -> bytes:
    python = _local_python()
    if python is None:
        pytest.skip("the local app's environment is needed to make blueprint.json")
    repo = Path(__file__).resolve().parents[3]
    subprocess.run(
        [
            str(python),
            "-m",
            "yoriqnoma_scanner",
            str(repo / "local" / "fixtures" / "demo_shop"),
            "--base-url",
            url,
            "--out",
            str(out),
        ],
        check=True,
        capture_output=True,
        timeout=300,
    )
    return out.read_bytes()


def test_mode_a_full_pipeline_on_demo_shop(site: Any, owner: User, tmp_path: Path) -> None:
    """QM-4: local blueprint.json uploaded by hand -> explorer -> writer -> renderer."""
    url, _ = site
    blueprint = _local_blueprint(url, tmp_path / "blueprint.json")
    (job,) = create_jobs(
        owner,
        JobRequest(
            mode="A",
            url=url,
            roles=["customer"],
            formats=["html"],
            blueprint=named(blueprint, "blueprint.json"),
        ),
    )
    job.refresh_from_db()
    assert job.status == "done", job.error
    assert job.stats["flows_verified"] >= 0.9 * job.stats["flows_total"]
    assert {"manual-html.zip", "manual.json"} <= set(job.artifacts.values_list("name", flat=True))
    assert job.accounts_enc is None


def test_mode_b_full_pipeline_on_demo_shop(
    site: Any, owner: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mode B without Claude: scout -> explorer -> writer (fake) -> renderer."""
    url, _ = site
    monkeypatch.setattr(scout.discover, "provider_factory", lambda *a: None)
    (job,) = create_jobs(
        owner,
        JobRequest(mode="B", url=url, roles=["customer"], role_label="Mijoz", formats=["html"]),
    )
    job.refresh_from_db()
    assert job.status == "done", job.error
    assert job.stats["flows_verified"] >= 1
    assert "blueprint.json" in set(job.artifacts.values_list("name", flat=True))
