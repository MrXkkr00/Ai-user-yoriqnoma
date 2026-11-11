from django.contrib import admin
from django.http import HttpRequest, HttpResponse
from django.urls import include, path
from django.views.generic import RedirectView, TemplateView

# Django admin is for server operators (staff only) and lives at /ops/, not /admin/
# (TZ FR-SV8). Web pages: accounts, domains, jobs. REST API: /api/ (session only).
admin.site.site_header = "AI user yo'riqnoma — operatorlar"
admin.site.site_title = "Operatorlar"


def healthz(request: HttpRequest) -> HttpResponse:
    """For container healthchecks: no login, no database, only «the web process answers»."""
    return HttpResponse("ok", content_type="text/plain")


urlpatterns = [
    path("healthz", healthz, name="healthz"),
    path("", RedirectView.as_view(pattern_name="jobs:list", permanent=False), name="home"),
    path("about/", TemplateView.as_view(template_name="about.html"), name="about"),
    path("accounts/", include("accounts.urls")),
    path("domains/", include("domains.urls")),
    path("jobs/", include("jobs.urls")),
    path("api/", include("api.urls")),
    path("ops/", admin.site.urls),
]
