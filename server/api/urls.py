from django.urls import include, path
from rest_framework.routers import DefaultRouter

from api.views import DomainViewSet, JobViewSet

app_name = "api"

router = DefaultRouter()
router.register("domains", DomainViewSet, basename="domain")
router.register("jobs", JobViewSet, basename="job")

urlpatterns = [path("", include(router.urls))]
