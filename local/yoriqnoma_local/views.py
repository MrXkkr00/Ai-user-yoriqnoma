from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from projects.models import Project
from settings_app.models import AppSettings
from yoriqnoma_local.health import all_checks


@require_GET
def home(request: HttpRequest) -> HttpResponse:
    """Projects and the system status panel."""
    return render(request, "home.html", {"projects": Project.objects.all()})


@require_GET
def system_status(request: HttpRequest) -> HttpResponse:
    """HTMX partial: Ollama, model, Playwright (TZ FR-L11)."""
    cfg = AppSettings.load()
    return render(
        request,
        "partials/system_status.html",
        {"checks": all_checks(cfg.ollama_host, cfg.ollama_model)},
    )
