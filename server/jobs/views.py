"""Job pages (ARCHITECTURE §7.5): list, new job, live job page (HTMX polling every 2 s)."""

from __future__ import annotations

from typing import Any, cast

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.http import FileResponse, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from domains.models import Domain
from jobs import budget
from jobs.downloads import download
from jobs.models import Artifact, Job
from jobs.services import (
    DEFAULT_FORMATS,
    FORMATS,
    JobError,
    JobRequest,
    answer_input,
    cancel_job,
    create_jobs,
    events_after,
    open_request,
    parse_budget,
    role_cards,
)
from jobs.uploads import UploadError, read_blueprint

STAGES = [
    ("preflight", "Tekshiruv"),
    ("scouting", "Razvedka"),
    ("exploring", "Saytni o'rganish"),
    ("writing", "Yozish"),
    ("rendering", "Tayyorlash"),
    ("done", "Tayyor"),
]
FORMAT_LABELS = {
    "html": "HTML",
    "pdf": "PDF",
    "docx": "DOCX",
    "tour": "Interaktiv tur",
    "gif": "GIF",
}


def _owned(request: HttpRequest, pk: int) -> Job:
    return get_object_or_404(Job, pk=pk, owner=cast(User, request.user))


@login_required
def job_list(request: HttpRequest) -> HttpResponse:
    jobs = Job.objects.filter(owner=cast(User, request.user))[:100]
    spent = budget.usage(cast(User, request.user))
    return render(
        request, "jobs/list.html", {"jobs": jobs, "spent": spent, "limits": budget.limits()}
    )


def _accounts_from(post: Any) -> dict[str, dict[str, dict[str, str]]]:
    accounts: dict[str, dict[str, dict[str, str]]] = {}
    target = [r for r in post.getlist("role") if r]
    for alias in ("A", "B"):
        login = post.get(f"login_{alias}", "").strip()
        password = post.get(f"password_{alias}", "")
        if login or password:
            for role in target or [post.get("role_b", "").strip()]:
                accounts.setdefault(role, {})[alias] = {"login": login, "password": password}
    helper = post.get("helper_role", "").strip()
    if helper:
        login = post.get("helper_login", "").strip()
        password = post.get("helper_password", "")
        if login or password:
            accounts.setdefault(helper, {})["A"] = {"login": login, "password": password}
    return accounts


@login_required
@require_http_methods(["GET", "POST"])
def job_new(request: HttpRequest) -> HttpResponse:
    context: dict[str, Any] = {
        "formats": [(f, FORMAT_LABELS[f]) for f in FORMATS],
        "default_formats": DEFAULT_FORMATS,
        "domains": Domain.objects.filter(owner=cast(User, request.user)),
        "data": request.POST,
    }
    if request.method == "POST":
        mode = request.POST.get("mode", "")
        roles = [r for r in request.POST.getlist("role") if r]
        if mode == "B":
            roles = [request.POST.get("role_b", "")]
        try:
            jobs = create_jobs(
                cast(User, request.user),
                JobRequest(
                    mode=mode,
                    url=request.POST.get("url", ""),
                    environment=request.POST.get("environment", "staging"),
                    formats=request.POST.getlist("formats"),
                    roles=roles,
                    role_label=request.POST.get("role_label", ""),
                    accounts=_accounts_from(request.POST),
                    budget_usd=parse_budget(request.POST.get("budget_usd")),
                    blueprint=request.FILES.get("blueprint"),
                    bundle=request.FILES.get("bundle"),
                ),
            )
        except (JobError, budget.BudgetLimit) as exc:
            context["error"] = str(exc)
            return render(request, "jobs/new.html", context, status=400)
        if len(jobs) > 1:
            messages.success(request, f"{len(jobs)} ta ish yaratildi (har rol uchun alohida).")
            return redirect("jobs:list")
        return redirect("jobs:detail", pk=jobs[0].pk)
    return render(request, "jobs/new.html", context)


@login_required
@require_POST
def job_roles(request: HttpRequest) -> HttpResponse:
    """Role options from an uploaded blueprint (HTMX, before the job is created)."""
    upload = request.FILES.get("blueprint")
    if upload is None:
        return render(request, "jobs/_roles.html", {"error": "blueprint.json tanlanmagan"})
    try:
        bp = read_blueprint(upload)
    except UploadError as exc:
        return render(request, "jobs/_roles.html", {"error": str(exc)})
    cards = role_cards(bp)
    count = sum(1 for c in cards if c["selectable"])
    return render(
        request,
        "jobs/_roles.html",
        {"cards": cards, "count": count, "base_url": str(bp.base_url), "project": bp.project},
    )


def _detail_context(job: Job) -> dict[str, Any]:
    reached = [s for s, _ in STAGES]
    current = job.status if job.status in reached else ""
    return {
        "job": job,
        "stages": STAGES
        if job.mode in {"B", "A_PLUS_B"}
        else [s for s in STAGES if s[0] != "scouting"],
        "current": current,
        "pending": open_request(job) if job.status == "waiting_input" else None,
        "artifacts": list(job.artifacts.all()) if job.status == "done" else [],
    }


@login_required
def job_detail(request: HttpRequest, pk: int) -> HttpResponse:
    job = _owned(request, pk)
    context = _detail_context(job)
    events = events_after(job, 0, limit=500)
    context["events"] = events
    context["last_event"] = events[-1].pk if events else 0
    return render(request, "jobs/detail.html", context)


@login_required
def job_status(request: HttpRequest, pk: int) -> HttpResponse:
    return render(request, "jobs/_status.html", _detail_context(_owned(request, pk)))


@login_required
def job_events(request: HttpRequest, pk: int) -> HttpResponse:
    job = _owned(request, pk)
    try:
        after = int(request.GET.get("after", "0"))
    except ValueError:
        after = 0
    events = events_after(job, after)
    last = events[-1].pk if events else after
    return render(request, "jobs/_events.html", {"job": job, "events": events, "last": last})


@login_required
@require_POST
def job_cancel(request: HttpRequest, pk: int) -> HttpResponse:
    cancel_job(_owned(request, pk))
    return redirect("jobs:detail", pk=pk)


@login_required
@require_POST
def job_input(request: HttpRequest, pk: int, request_id: int) -> HttpResponse:
    job = _owned(request, pk)
    try:
        answer_input(job, request_id, request.POST.get("value", ""))
    except (JobError, job.input_requests.model.DoesNotExist) as exc:
        messages.error(request, str(exc))
    return redirect("jobs:detail", pk=pk)


@login_required
def artifact_download(request: HttpRequest, pk: int, name: str) -> HttpResponse | FileResponse:
    job = _owned(request, pk)
    artifact = get_object_or_404(Artifact, job=job, name=name)
    return download(artifact)
