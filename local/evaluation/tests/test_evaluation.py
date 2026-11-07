from __future__ import annotations

import asyncio

import pytest
from django.test import Client

from evaluation.models import EvalRun, EvalSample
from evaluation.services import DEFAULT_GOLDEN, evaluate_case, load_golden, summarize
from settings_app.models import AppSettings
from yoriqnoma_core.writer.providers import FakeProvider


def test_golden_set_has_20_to_30_cases() -> None:
    cases = load_golden(DEFAULT_GOLDEN)

    assert 20 <= len(cases) <= 30
    assert all(c.image.is_file() and c.elements and c.keywords for c in cases)


def test_metrics_with_fake_provider() -> None:
    case = load_golden(DEFAULT_GOLDEN)[0]
    row = asyncio.run(evaluate_case(FakeProvider(), case, "Mijoz"))

    assert row["schema_error"] is False and row["forbidden"] == []
    summary = summarize([row, {"schema_error": True}])
    assert summary["cases"] == 2 and summary["schema_errors"] == 1


@pytest.mark.django_db
def test_eval_pages_score_and_primary_model(client: Client) -> None:
    run = EvalRun.objects.create(
        model_names=["a", "b"],
        golden_dir=str(DEFAULT_GOLDEN),
        status="done",
        summary={"a": {"cases": 1}, "b": {"cases": 1}},
    )
    sample = EvalSample.objects.create(run=run, model="a", case_id="01", text="matn")

    assert client.get("/eval/").status_code == 200
    assert client.get(f"/eval/{run.pk}/").status_code == 200
    client.post(f"/eval/{run.pk}/score/", {"sample": sample.pk, "score": "4"})
    sample.refresh_from_db()
    assert sample.score == 4
    client.post(f"/eval/{run.pk}/primary/", {"model": "b"})
    assert AppSettings.load().ollama_model == "b"


@pytest.mark.llm
@pytest.mark.django_db
def test_eval_with_real_models() -> None:
    from evaluation.services import run_eval, start_eval

    run = run_eval(start_eval(["gemma4:26b", "qwen3.6:27b"], enqueue=False), limit=3)

    assert run.status == "done"
    assert run.summary["gemma4:26b"]["cases"] == 3
