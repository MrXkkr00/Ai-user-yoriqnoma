"""REST API (ARCHITECTURE §7.4): session login + CSRF only, every object visible to its owner.

Another user's domain or job is answered with 404, never 403: its existence is not shown.
"""

from __future__ import annotations

from typing import Any, cast

from django.contrib.auth.models import User
from django.db.models import QuerySet
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from api.serializers import (
    DomainSerializer,
    InputAnswerSerializer,
    JobCreateSerializer,
    JobEventSerializer,
    JobSerializer,
)
from domains.models import Domain
from domains.services import DomainError, add_domain, verify
from jobs.budget import BudgetLimit
from jobs.downloads import download
from jobs.models import Artifact, Job
from jobs.services import JobError, JobRequest, answer_input, cancel_job, create_jobs, events_after


class DomainViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet[Domain],
):
    serializer_class = DomainSerializer

    def get_queryset(self) -> QuerySet[Domain]:
        return Domain.objects.filter(owner=cast(User, self.request.user))

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        try:
            domain = add_domain(cast(User, request.user), str(request.data.get("host", "")))
        except DomainError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(DomainSerializer(domain).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def verify(self, request: Request, pk: str | None = None) -> Response:
        domain = self.get_object()
        try:
            domain = verify(domain)
        except DomainError as exc:
            return Response({"detail": str(exc), "verified": False}, status=400)
        return Response(DomainSerializer(domain).data)


class JobViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet[Job],
):
    serializer_class = JobSerializer

    def get_queryset(self) -> QuerySet[Job]:
        return Job.objects.filter(owner=cast(User, self.request.user)).prefetch_related("artifacts")

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        form = JobCreateSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        data = form.validated_data
        roles = [r.strip() for r in str(data.get("role", "")).split(",") if r.strip()]
        try:
            jobs = create_jobs(
                cast(User, request.user),
                JobRequest(
                    mode=data["mode"],
                    url=data.get("url", ""),
                    environment=data["environment"],
                    language=data.get("language", "uz"),
                    formats=data["formats"],
                    roles=roles,
                    role_label=data.get("role_label", ""),
                    accounts=data.get("accounts", {}),
                    budget_usd=data.get("budget_usd"),
                    source="api",
                    blueprint=data.get("blueprint"),
                    bundle=data.get("bundle"),
                ),
            )
        except (JobError, BudgetLimit) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        body = [
            {"id": j.id, "web_url": JobSerializer(j).data["web_url"], "status": j.status}
            for j in jobs
        ]
        return Response(body[0] if len(body) == 1 else body, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"])
    def events(self, request: Request, pk: str | None = None) -> Response:
        job = self.get_object()
        try:
            after = int(request.query_params.get("after", "0"))
        except ValueError:
            after = 0
        return Response(JobEventSerializer(events_after(job, after), many=True).data)

    @action(detail=True, methods=["post"], url_path="input")
    def input(self, request: Request, pk: str | None = None) -> Response:
        job = self.get_object()
        form = InputAnswerSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        try:
            answer_input(job, form.validated_data["request_id"], form.validated_data["value"])
        except (JobError, job.input_requests.model.DoesNotExist) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"ok": True})

    @action(detail=True, methods=["post"])
    def cancel(self, request: Request, pk: str | None = None) -> Response:
        job = cancel_job(self.get_object())
        return Response({"id": job.pk, "status": job.status, "cancel_requested": True})

    @action(detail=True, methods=["get"], url_path=r"artifacts/(?P<name>[A-Za-z0-9_.\-]+)")
    def artifact(
        self, request: Request, pk: str | None = None, name: str = ""
    ) -> HttpResponse | FileResponse:
        job = self.get_object()
        artifact = get_object_or_404(Artifact, job=job, name=name)
        return download(artifact)
