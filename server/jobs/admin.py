from django.contrib import admin

from jobs.models import Artifact, InputRequest, Job, JobEvent


@admin.register(Job)
class JobAdmin(admin.ModelAdmin[Job]):
    list_display = ["id", "owner", "mode", "role", "status", "cost_usd", "created_at"]
    list_filter = ["mode", "status", "passive"]
    search_fields = ["url", "role", "owner__username"]
    # passwords and uploads are never shown to operators
    exclude = ["accounts_enc"]
    readonly_fields = ["cost_usd", "tokens_in", "tokens_out", "started_at", "finished_at"]


@admin.register(JobEvent)
class JobEventAdmin(admin.ModelAdmin[JobEvent]):
    list_display = ["id", "job", "kind", "at"]
    list_filter = ["kind"]


@admin.register(InputRequest)
class InputRequestAdmin(admin.ModelAdmin[InputRequest]):
    list_display = ["id", "job", "kind", "created_at", "answered_at"]
    exclude = ["value_enc"]


@admin.register(Artifact)
class ArtifactAdmin(admin.ModelAdmin[Artifact]):
    list_display = ["id", "job", "name", "size", "created_at"]
