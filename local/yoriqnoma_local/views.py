from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET


@require_GET
def home(request: HttpRequest) -> HttpResponse:
    """Landing page. T19 turns it into the project list with the system status panel."""
    return render(request, "home.html")


@require_GET
def system_status(request: HttpRequest) -> HttpResponse:
    """HTMX partial for the status panel. Real health checks arrive in T18."""
    return render(request, "partials/system_status.html")
