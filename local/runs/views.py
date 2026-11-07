from __future__ import annotations

import mimetypes
import os
import subprocess
import sys
from pathlib import Path

from django.contrib import messages
from django.http import FileResponse, Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from projects.forms import NewRunForm
from projects.models import Project
from projects.services import effective_blueprint, role_options
from runs.models import InputRequest, Run
from runs.services import RunError, answer_input, cancel_run, resume_run, run_files, start_run
from settings_app.models import AppSettings


@require_http_methods(["GET", "POST"])
def run_new(request: HttpRequest, pk: int) -> HttpResponse:
    project = get_object_or_404(Project, pk=pk)
    version = project.current_blueprint()
    if version is None:
        messages.error(request, "Avval loyihani skanerlang yoki blueprint yuklang.")
        return redirect("project-detail", pk)
    bp, _ = effective_blueprint(version)
    options = role_options(project, bp)
    choices = [(o.id, o.label) for o in options if o.selectable]
    cfg = AppSettings.load()
    form = NewRunForm(
        request.POST or None, role_choices=choices, initial={"model": cfg.ollama_model}
    )
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        roles = d["roles"] if d["output"] != "blueprint" else [""]
        created: list[Run] = []
        try:
            for role in roles:
                created.append(
                    start_run(
                        project,
                        d["output"],
                        role,
                        d["model"] or cfg.ollama_model,
                        d["formats"] or ["html", "pdf", "docx"],
                    )
                )
        except RunError as exc:
            messages.error(request, str(exc))
            return redirect("run-new", pk)
        if len(created) > 1:
            messages.success(
                request, f"{len(created)} ta ish navbatga qo'yildi (har rol uchun alohida)."
            )
        return redirect("run-detail", created[0].pk)
    usable = [o for o in options if o.selectable]
    return render(
        request,
        "runs/new.html",
        {
            "project": project,
            "form": form,
            "options": options,
            "usable_count": len(usable),
        },
    )


def run_detail(request: HttpRequest, pk: int) -> HttpResponse:
    run = get_object_or_404(Run.objects.select_related("project"), pk=pk)
    return render(request, "runs/detail.html", {"run": run, **_status_ctx(run)})


def run_status(request: HttpRequest, pk: int) -> HttpResponse:
    run = get_object_or_404(Run, pk=pk)
    return render(request, "runs/_status.html", {"run": run, **_status_ctx(run)})


def _status_ctx(run: Run) -> dict[str, object]:
    pending = run.inputs.filter(answered_at__isnull=True).first()
    return {
        "events": list(run.events.order_by("-pk")[:60])[::-1],
        "pending": pending,
        "files": run_files(run) if run.finished else [],
        "stages": Run.STAGES if run.output == "full" else Run.STAGES[:1] + Run.STAGES[3:],
    }


@require_POST
def run_cancel(request: HttpRequest, pk: int) -> HttpResponse:
    cancel_run(get_object_or_404(Run, pk=pk))
    return redirect("run-detail", pk)


@require_POST
def run_resume(request: HttpRequest, pk: int) -> HttpResponse:
    run = get_object_or_404(Run, pk=pk)
    try:
        resume_run(run)
    except RunError as exc:
        messages.error(request, str(exc))
    return redirect("run-detail", pk)


@require_POST
def run_input(request: HttpRequest, pk: int, req_id: int) -> HttpResponse:
    req = get_object_or_404(InputRequest, pk=req_id, run_id=pk)
    value = request.POST.get("value", "").strip()
    if value:
        answer_input(req, value)
    return redirect("run-detail", pk)


def run_file(request: HttpRequest, pk: int, name: str) -> FileResponse:
    """Files of the run folder only (path traversal is refused)."""
    run = get_object_or_404(Run, pk=pk)
    base = Path(run.run_dir).resolve()
    target = (base / name).resolve()
    if not target.is_relative_to(base) or not target.is_file():
        raise Http404("Fayl topilmadi")
    if target.name in {"progress.json"} or target.suffix in {".key"}:
        raise Http404("Fayl topilmadi")
    ctype, _ = mimetypes.guess_type(target.name)
    inline = target.suffix in {".html", ".css", ".js", ".png", ".webp", ".jpg", ".svg"}
    response = FileResponse(
        target.open("rb"),
        content_type=ctype or "application/octet-stream",
        as_attachment=not inline,
        filename=target.name,
    )
    if target.suffix == ".html":
        response["X-Frame-Options"] = "SAMEORIGIN"
    return response


@require_POST
def run_open_folder(request: HttpRequest, pk: int) -> HttpResponse:
    run = get_object_or_404(Run, pk=pk)
    folder = Path(run.run_dir)
    if folder.is_dir():
        if sys.platform == "win32":
            os.startfile(folder)  # noqa: S606
        else:
            subprocess.Popen(["xdg-open", str(folder)])  # noqa: S603, S607
    return redirect("run-detail", pk)
