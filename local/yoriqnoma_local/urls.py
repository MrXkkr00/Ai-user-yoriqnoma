from django.urls import path

from evaluation import views as eval_views
from projects import views as project_views
from runs import views as run_views
from settings_app import views as settings_views
from yoriqnoma_local import views

urlpatterns = [
    path("", views.home, name="home"),
    path("system-status/", views.system_status, name="system-status"),
    path("projects/new/", project_views.project_new, name="project-new"),
    path("projects/<int:pk>/", project_views.project_detail, name="project-detail"),
    path("projects/<int:pk>/edit/", project_views.project_edit, name="project-edit"),
    path("projects/<int:pk>/scan/", project_views.project_scan, name="project-scan"),
    path("projects/<int:pk>/blueprint/", project_views.blueprint_view, name="blueprint"),
    path(
        "projects/<int:pk>/blueprint/upload/",
        project_views.blueprint_upload,
        name="blueprint-upload",
    ),
    path(
        "projects/<int:pk>/blueprint/override/",
        project_views.blueprint_override,
        name="blueprint-override",
    ),
    path("projects/<int:pk>/accounts/", project_views.account_add, name="account-add"),
    path(
        "projects/<int:pk>/accounts/<int:account_id>/delete/",
        project_views.account_delete,
        name="account-delete",
    ),
    path("projects/<int:pk>/runs/new/", run_views.run_new, name="run-new"),
    path("runs/<int:pk>/", run_views.run_detail, name="run-detail"),
    path("runs/<int:pk>/status/", run_views.run_status, name="run-status"),
    path("runs/<int:pk>/cancel/", run_views.run_cancel, name="run-cancel"),
    path("runs/<int:pk>/resume/", run_views.run_resume, name="run-resume"),
    path("runs/<int:pk>/input/<int:req_id>/", run_views.run_input, name="run-input"),
    path("runs/<int:pk>/files/<path:name>", run_views.run_file, name="run-file"),
    path("runs/<int:pk>/open-folder/", run_views.run_open_folder, name="run-open-folder"),
    path("settings/", settings_views.settings_view, name="settings"),
    path("settings/test/", settings_views.settings_test, name="settings-test"),
    path("eval/", eval_views.eval_view, name="eval"),
    path("eval/<int:pk>/", eval_views.eval_detail, name="eval-detail"),
    path("eval/<int:pk>/score/", eval_views.eval_score, name="eval-score"),
    path("eval/<int:pk>/primary/", eval_views.eval_primary, name="eval-primary"),
]
