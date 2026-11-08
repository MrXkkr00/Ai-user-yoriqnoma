"""DRF serializers (ARCHITECTURE §7.4). Secrets (passwords, tokens of others) never leave."""

from __future__ import annotations

import json
from typing import Any

from django.urls import reverse
from rest_framework import serializers

from domains.models import Domain
from jobs.models import Artifact, Job, JobEvent


class DomainSerializer(serializers.ModelSerializer[Domain]):
    methods = serializers.SerializerMethodField()

    class Meta:
        model = Domain
        fields = ["id", "host", "token", "verified_at", "method", "methods", "created_at"]
        read_only_fields = ["id", "token", "verified_at", "method", "methods", "created_at"]

    def get_methods(self, obj: Domain) -> dict[str, str]:
        return {
            "wellknown": f"{obj.wellknown_url} faylida: {obj.token}",
            "meta": obj.meta_tag,
            "dns": f'TXT {obj.host} "{obj.dns_record}"',
        }


class ArtifactSerializer(serializers.ModelSerializer[Artifact]):
    url = serializers.SerializerMethodField()

    class Meta:
        model = Artifact
        fields = ["name", "label", "size", "sha256", "url"]

    def get_url(self, obj: Artifact) -> str:
        return reverse("api:job-artifact", kwargs={"pk": obj.job_id, "name": obj.name})


class JobSerializer(serializers.ModelSerializer[Job]):
    artifacts = ArtifactSerializer(many=True, read_only=True)
    web_url = serializers.SerializerMethodField()
    progress = serializers.SerializerMethodField()

    class Meta:
        model = Job
        fields = [
            "id",
            "mode",
            "url",
            "environment",
            "language",
            "formats",
            "role",
            "role_label",
            "status",
            "progress",
            "passive",
            "budget_usd",
            "cost_usd",
            "tokens_in",
            "tokens_out",
            "error",
            "stats",
            "source",
            "created_at",
            "started_at",
            "finished_at",
            "expires_at",
            "artifacts",
            "web_url",
        ]
        read_only_fields = fields

    def get_web_url(self, obj: Job) -> str:
        return reverse("jobs:detail", kwargs={"pk": obj.pk})

    def get_progress(self, obj: Job) -> dict[str, int]:
        return {"done": obj.progress_done, "total": obj.progress_total, "percent": obj.percent}


class JobCreateSerializer(serializers.Serializer[dict[str, Any]]):
    mode = serializers.ChoiceField(choices=["A", "A_PRIME", "B", "A_PLUS_B"])
    url = serializers.CharField(required=False, allow_blank=True, max_length=500)
    environment = serializers.ChoiceField(choices=["staging", "production"], default="staging")
    language = serializers.CharField(required=False, default="uz", max_length=8)
    formats = serializers.CharField(required=False, default="html,pdf,docx")
    role = serializers.CharField(required=False, allow_blank=True, max_length=300)
    role_label = serializers.CharField(required=False, allow_blank=True, max_length=120)
    accounts = serializers.CharField(required=False, allow_blank=True)
    blueprint = serializers.FileField(required=False)
    bundle = serializers.FileField(required=False)
    budget_usd = serializers.DecimalField(
        required=False, max_digits=8, decimal_places=2, allow_null=True
    )

    def validate_accounts(self, value: str) -> dict[str, Any]:
        if not value:
            return {}
        try:
            data = json.loads(value)
        except json.JSONDecodeError as exc:
            raise serializers.ValidationError("accounts JSON bo'lishi kerak") from exc
        if not isinstance(data, dict):
            raise serializers.ValidationError("accounts: {rol: {A: {login, password}}}")
        return data

    def validate_formats(self, value: str) -> list[str]:
        return [f.strip() for f in value.split(",") if f.strip()]


class JobEventSerializer(serializers.ModelSerializer[JobEvent]):
    class Meta:
        model = JobEvent
        fields = ["id", "at", "kind", "payload"]


class InputAnswerSerializer(serializers.Serializer[dict[str, Any]]):
    request_id = serializers.IntegerField()
    value = serializers.CharField(max_length=200)
