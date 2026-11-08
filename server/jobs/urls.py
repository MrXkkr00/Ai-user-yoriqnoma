from django.urls import path

from jobs import views

app_name = "jobs"

urlpatterns = [
    path("", views.job_list, name="list"),
    path("new/", views.job_new, name="new"),
    path("new/roles/", views.job_roles, name="roles"),
    path("<int:pk>/", views.job_detail, name="detail"),
    path("<int:pk>/status/", views.job_status, name="status"),
    path("<int:pk>/events/", views.job_events, name="events"),
    path("<int:pk>/cancel/", views.job_cancel, name="cancel"),
    path("<int:pk>/input/<int:request_id>/", views.job_input, name="input"),
    path("<int:pk>/files/<str:name>", views.artifact_download, name="artifact"),
]
