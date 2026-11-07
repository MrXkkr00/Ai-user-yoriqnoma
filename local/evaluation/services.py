"""Model comparison on the golden set (TZ FR-L12).

Each golden case is a captured state (SoM image + elements) with expected keywords and
forbidden words. Per model: schema errors, marker/name errors, keyword coverage,
forbidden words and average time.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from django.conf import settings

from evaluation.models import EvalRun, EvalSample
from settings_app.models import AppSettings
from yoriqnoma_core.text_uz import normalize_uz
from yoriqnoma_core.writer.answers import FlowDescription
from yoriqnoma_core.writer.providers import OllamaProvider
from yoriqnoma_core.writer.providers.base import LLMProvider, LLMRequest, ProviderError
from yoriqnoma_core.writer.tasks import render_prompt
from yoriqnoma_core.writer.validate import check_text, known_set

DEFAULT_GOLDEN = Path(settings.BASE_DIR) / "tests" / "golden"


@dataclass
class GoldenCase:
    id: str
    title: str
    url: str
    steps: list[str]
    elements: list[dict[str, Any]]
    keywords: list[str]
    forbidden: list[str]
    image: Path


def load_golden(folder: Path) -> list[GoldenCase]:
    cases: list[GoldenCase] = []
    for case_file in sorted(folder.glob("*/case.json")):
        data = json.loads(case_file.read_text(encoding="utf-8"))
        cases.append(
            GoldenCase(
                id=case_file.parent.name,
                title=data["title"],
                url=data.get("url", ""),
                steps=data.get("steps", []),
                elements=data.get("elements", []),
                keywords=data.get("expected", {}).get("keywords", []),
                forbidden=data.get("expected", {}).get("forbidden", []),
                image=case_file.parent / "som.png",
            )
        )
    return cases


async def evaluate_case(provider: LLMProvider, case: GoldenCase, role_label: str) -> dict[str, Any]:
    prompt = render_prompt(
        "describe_flow",
        title=case.title,
        project="demo_shop",
        url=case.url,
        steps=case.steps,
        elements=case.elements,
        rules=[],
    )
    system = render_prompt("system", role_label=role_label)
    req = LLMRequest(
        task="describe_flow",
        system=system,
        prompt=prompt,
        images=[case.image] if case.image.is_file() else [],
        max_tokens=800,
    )
    started = time.monotonic()
    try:
        result = await provider.generate(req, FlowDescription)
    except ProviderError as exc:
        return {"schema_error": True, "error": str(exc)[:300], "seconds": 0.0, "text": ""}
    text = " ".join([result.data.purpose, *result.data.notes])
    known = known_set([e["name"] for e in case.elements] + [case.title])
    soft, hard = check_text(text, known, [])
    norm = normalize_uz(text)
    hits = [k for k in case.keywords if normalize_uz(k) in norm]
    bad = [w for w in case.forbidden if normalize_uz(w) in norm]
    return {
        "schema_error": False,
        "marker_errors": len(soft),
        "hard_errors": len(hard),
        "keyword_coverage": round(len(hits) / len(case.keywords), 2) if case.keywords else 1.0,
        "forbidden": bad,
        "seconds": round(time.monotonic() - started, 2),
        "text": text,
    }


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ok = [r for r in rows if not r.get("schema_error")]
    n = max(1, len(rows))
    return {
        "cases": len(rows),
        "schema_errors": sum(1 for r in rows if r.get("schema_error")),
        "marker_errors": sum(int(r.get("marker_errors", 0)) for r in ok),
        "forbidden": sum(len(r.get("forbidden", [])) for r in ok),
        "keyword_coverage": round(sum(float(r.get("keyword_coverage", 0)) for r in ok) / n, 2),
        "avg_seconds": round(sum(float(r.get("seconds", 0)) for r in ok) / max(1, len(ok)), 2),
    }


def run_eval(eval_run: EvalRun, limit: int | None = None) -> EvalRun:
    cfg = AppSettings.load()
    cases = load_golden(Path(eval_run.golden_dir))[:limit]
    eval_run.status = "running"
    eval_run.save(update_fields=["status"])
    summary: dict[str, Any] = {}
    try:
        for model in eval_run.model_names:
            provider = OllamaProvider(host=cfg.ollama_host, model=model, num_ctx=cfg.num_ctx)
            try:
                provider.check()
            except ProviderError as exc:
                summary[model] = {"error": str(exc)}
                continue
            rows = []
            for case in cases:
                row = asyncio.run(evaluate_case(provider, case, "Mijoz"))
                rows.append(row)
                EvalSample.objects.create(
                    run=eval_run,
                    model=model,
                    case_id=case.id,
                    text=row.pop("text", ""),
                    metrics=row,
                )
            summary[model] = summarize(rows)
        eval_run.summary = summary
        eval_run.status = "done"
    except Exception as exc:  # noqa: BLE001 - shown on the page
        eval_run.status = "failed"
        eval_run.error = f"{type(exc).__name__}: {exc}"
    eval_run.save()
    return eval_run


def start_eval(models: list[str], golden_dir: Path | None = None, enqueue: bool = True) -> EvalRun:
    eval_run = EvalRun.objects.create(
        model_names=models, golden_dir=str(golden_dir or DEFAULT_GOLDEN)
    )
    if enqueue:
        from evaluation.tasks import run_eval_task

        run_eval_task(eval_run.pk)
    return eval_run
