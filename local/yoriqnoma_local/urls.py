from django.urls import path

from yoriqnoma_local import views

urlpatterns = [
    path("", views.home, name="home"),
    path("system-status/", views.system_status, name="system-status"),
]
