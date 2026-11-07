from django.contrib import admin
from django.urls import path

# Django admin is for server operators (staff only) and lives at /ops/, not /admin/
# (TZ FR-SV8). The REST API (/api/) and web pages arrive in T22-T24.
urlpatterns = [
    path("ops/", admin.site.urls),
]
