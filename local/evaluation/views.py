from __future__ import annotations

from collections import defaultdict

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from evaluation.models import EvalRun, EvalSample
from evaluation.services import DEFAULT_GOLDEN, load_golden, start_eval
from settings_app.models import AppSettings
from settings_app.views import installed_models


@require_http_methods(["GET", "POST"])
def eval_view(request: HttpRequest) -> HttpResponse:
    cfg = AppSettings.load()
    if request.method == "POST":
        models = request.POST.getlist("models")
        if not models:
            messages.error(request, "Kamida bitta modelni tanlang.")
        else:
            run = start_eval(models)
            return redirect("eval-detail", run.pk)
    return render(
        request,
        "evaluation/index.html",
        {
            "runs": EvalRun.objects.all()[:20],
            "models": installed_models(cfg.ollama_host),
            "current": cfg.ollama_model,
            "cases": len(load_golden(DEFAULT_GOLDEN)),
        },
    )


def eval_detail(request: HttpRequest, pk: int) -> HttpResponse:
    run = get_object_or_404(EvalRun, pk=pk)
    by_case: dict[str, list[EvalSample]] = defaultdict(list)
    for sample in run.samples.all():
        by_case[sample.case_id].append(sample)
    scores: dict[str, list[int]] = defaultdict(list)
    for sample in run.samples.exclude(score__isnull=True):
        scores[sample.model].append(int(sample.score or 0))
    avg = {m: round(sum(v) / len(v), 2) for m, v in scores.items() if v}
    return render(
        request,
        "evaluation/detail.html",
        {
            "run": run,
            "by_case": dict(by_case),
            "avg": avg,
            "current": AppSettings.load().ollama_model,
        },
    )


@require_POST
def eval_score(request: HttpRequest, pk: int) -> HttpResponse:
    sample = get_object_or_404(EvalSample, pk=request.POST.get("sample"), run_id=pk)
    value = request.POST.get("score", "")
    if value.isdigit() and 1 <= int(value) <= 5:
        sample.score = int(value)
        sample.save(update_fields=["score"])
    return redirect("eval-detail", pk)


@require_POST
def eval_primary(request: HttpRequest, pk: int) -> HttpResponse:
    cfg = AppSettings.load()
    model = request.POST.get("model", "")
    if model:
        cfg.ollama_model = model
        cfg.save(update_fields=["ollama_model"])
        messages.success(request, f"Asosiy model: {model}")
    return redirect("eval-detail", pk)
