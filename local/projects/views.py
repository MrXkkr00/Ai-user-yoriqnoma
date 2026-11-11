from __future__ import annotations

from typing import Any

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from projects.forms import AccountForm, ProjectForm, UploadBlueprintForm
from projects.models import Project, ProjectAccount
from projects.services import (
    BlueprintError,
    delete_project,
    effective_blueprint,
    raw_blueprint,
    role_options,
    scan_project,
    set_account,
    set_override,
    unique_slug,
    upload_blueprint,
)

TABS = [
    ("roles", "Rollar"),
    ("pages", "Sahifalar"),
    ("entities", "Obyektlar va statuslar"),
    ("flows", "Flow'lar"),
    ("excluded", "Chiqarib tashlanganlar"),
    ("report", "Skan hisoboti"),
]


@require_http_methods(["GET", "POST"])
def project_new(request: HttpRequest) -> HttpResponse:
    form = ProjectForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        project = form.save(commit=False)
        project.slug = unique_slug(project.name)
        project.save()
        messages.success(request, "Loyiha yaratildi. Endi «Tekshirish» tugmasini bosing.")
        return redirect("project-detail", project.pk)
    return render(request, "projects/form.html", {"form": form, "project": None})


@require_http_methods(["GET", "POST"])
def project_edit(request: HttpRequest, pk: int) -> HttpResponse:
    project = get_object_or_404(Project, pk=pk)
    form = ProjectForm(request.POST or None, instance=project)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Saqlandi.")
        return redirect("project-detail", project.pk)
    return render(request, "projects/form.html", {"form": form, "project": project})


def project_check(request: HttpRequest, pk: int) -> HttpResponse:
    """The «Tekshirish» panel (HTMX polling while the admin check runs)."""
    project = get_object_or_404(Project, pk=pk)
    return render(request, "projects/_check.html", {"project": project})


def project_detail(request: HttpRequest, pk: int) -> HttpResponse:
    project = get_object_or_404(Project, pk=pk)
    version = project.current_blueprint()
    roles: list[Any] = []
    if version is not None:
        bp, _ = effective_blueprint(version)
        roles = role_options(project, bp)
    return render(
        request,
        "projects/detail.html",
        {
            "project": project,
            "version": version,
            "roles": roles,
            "runs": project.runs.all()[:20],
            "accounts": project.accounts.all(),
            "account_form": AccountForm(),
            "upload_form": UploadBlueprintForm(),
        },
    )


@require_POST
def project_scan(request: HttpRequest, pk: int) -> HttpResponse:
    project = get_object_or_404(Project, pk=pk)
    if project.uses_admin:
        # the admin is checked in a browser: in the worker, the page polls the result
        from runs.tasks import check_project_task

        Project.objects.filter(pk=pk).update(check_state="running", check_error="")
        check_project_task(project.pk)
        return redirect("project-detail", pk)
    try:
        version = scan_project(project)
    except (BlueprintError, ValueError, NotADirectoryError) as exc:
        messages.error(request, f"Skanerlab bo'lmadi: {exc}")
        return redirect("project-detail", pk)
    messages.success(request, f"Skan tugadi: {version.stats.get('flows', 0)} ta flow topildi.")
    return redirect("blueprint", pk)


@require_POST
def blueprint_upload(request: HttpRequest, pk: int) -> HttpResponse:
    project = get_object_or_404(Project, pk=pk)
    form = UploadBlueprintForm(request.POST, request.FILES)
    if form.is_valid():
        try:
            upload_blueprint(project, form.cleaned_data["file"].read())
            messages.success(request, "Blueprint yuklandi.")
        except BlueprintError as exc:
            messages.error(request, str(exc))
    return redirect("project-detail", pk)


@require_POST
def account_add(request: HttpRequest, pk: int) -> HttpResponse:
    project = get_object_or_404(Project, pk=pk)
    form = AccountForm(request.POST)
    if form.is_valid():
        d = form.cleaned_data
        set_account(project, d["role"], d["alias"], d["login"], d["password"])
        messages.success(request, f"«{d['role']}» uchun {d['alias']} akkaunt saqlandi.")
    else:
        messages.error(request, "Akkaunt ma'lumotlari to'liq emas.")
    return redirect("project-detail", pk)


@require_POST
def account_delete(request: HttpRequest, pk: int, account_id: int) -> HttpResponse:
    get_object_or_404(ProjectAccount, pk=account_id, project_id=pk).delete()
    return redirect("project-detail", pk)


def blueprint_view(request: HttpRequest, pk: int) -> HttpResponse:
    project = get_object_or_404(Project, pk=pk)
    version = project.current_blueprint()
    if version is None:
        messages.error(request, "Avval loyihani skanerlang yoki blueprint yuklang.")
        return redirect("project-detail", pk)
    tab = request.GET.get("tab", "roles")
    raw = raw_blueprint(version)
    bp, notes = effective_blueprint(version)
    report = ""
    if tab == "report" and version.report_path:
        try:
            with open(version.report_path, encoding="utf-8") as fh:
                report = fh.read()
        except OSError:
            report = "Hisobot fayli topilmadi."
    kept_flows = {f.id for f in bp.flows}
    kept_pages = {p.path for p in bp.pages}
    overrides = version.overrides or {}
    ctx = {
        "project": project,
        "version": version,
        "tab": tab,
        "tabs": TABS,
        "raw": raw,
        "bp": bp,
        "notes": notes,
        "report": report,
        "kept_flows": kept_flows,
        "kept_pages": kept_pages,
        "renames": overrides.get("rename_flows", {}),
        "excluded_pages": set(overrides.get("exclude_pages", [])),
        "excluded_flows": set(overrides.get("exclude_flows", [])),
        "stats": version.stats,
    }
    return render(request, "projects/blueprint.html", ctx)


@require_POST
def blueprint_override(request: HttpRequest, pk: int) -> HttpResponse:
    project = get_object_or_404(Project, pk=pk)
    version = project.current_blueprint()
    if version is None:
        return HttpResponse("Blueprint yo'q", status=400)
    kind = request.POST.get("kind", "")
    key = request.POST.get("key", "")
    value: Any = request.POST.get("value", "")
    if kind in {"exclude_pages", "exclude_flows"}:
        value = value == "1"
    try:
        set_override(version, kind, key, value)
    except Exception as exc:  # noqa: BLE001 - shown to the user
        return HttpResponse(f"Xato: {exc}", status=400)
    if request.headers.get("HX-Request"):
        response = HttpResponse("")
        response["HX-Refresh"] = "true"
        return response
    return redirect(f"/projects/{pk}/blueprint/?tab={request.POST.get('tab', 'flows')}")


@require_POST
def project_delete(request: HttpRequest, pk: int) -> HttpResponse:
    from runs.services import DeleteBlocked

    project = get_object_or_404(Project, pk=pk)
    try:
        delete_project(project)
    except DeleteBlocked as exc:
        messages.error(request, str(exc))
        return redirect("project-detail", pk)
    messages.success(request, f"«{project.name}» loyihasi va uning fayllari o'chirildi.")
    return redirect("home")
