"""Jobs of the server app (ARCHITECTURE §7.2): one job writes one manual for one role."""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models

ACTIVE = ("queued", "preflight", "scouting", "exploring", "writing", "rendering", "waiting_input")
FINISHED = ("done", "failed", "cancelled")


def upload_path(instance: Job, filename: str) -> str:
    """Uploads go under a random folder name: never the user's own file name in a path."""
    suffix = ".zip" if filename.lower().endswith(".zip") else ".json"
    kind = "bundle" if suffix == ".zip" else "blueprint"
    return f"uploads/{instance.owner_id}/{uuid.uuid4().hex}/{kind}{suffix}"


def artifact_path(instance: Artifact, filename: str) -> str:
    return f"jobs/{instance.job_id}/{instance.name}"


class Job(models.Model):
    MODES = [
        ("A", "A — blueprint va URL"),
        ("A_PRIME", "A' — bundle (ichki tarmoqdagi sayt)"),
        ("B", "B — faqat URL"),
        ("A_PLUS_B", "A+B — blueprint va razvedka"),
    ]
    STATUSES = [
        ("queued", "Navbatda"),
        ("preflight", "Tekshiruv"),
        ("scouting", "Razvedka"),
        ("exploring", "Saytni o'rganish"),
        ("writing", "Yozish"),
        ("rendering", "Tayyorlash"),
        ("waiting_input", "Javob kutilmoqda"),
        ("done", "Tayyor"),
        ("failed", "Xato"),
        ("cancelled", "Bekor qilindi"),
    ]
    ENVIRONMENTS = [("staging", "Staging (sinov)"), ("production", "Production")]
    SOURCES = [("web", "Veb"), ("api", "API")]

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="jobs"
    )
    domain = models.ForeignKey(
        "domains.Domain", null=True, blank=True, on_delete=models.SET_NULL, related_name="jobs"
    )
    mode = models.CharField(max_length=10, choices=MODES)
    url = models.URLField(max_length=500)
    environment = models.CharField(max_length=12, choices=ENVIRONMENTS, default="staging")
    language = models.CharField(max_length=8, default="uz")
    formats = models.JSONField(default=list)
    role = models.CharField(max_length=64)  # target role (TZ FR-RL3)
    role_label = models.CharField(max_length=120, blank=True)
    status = models.CharField(max_length=16, choices=STATUSES, default="queued")
    progress_done = models.IntegerField(default=0)
    progress_total = models.IntegerField(default=0)
    budget_usd = models.DecimalField(max_digits=8, decimal_places=2)
    cost_usd = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    tokens_in = models.BigIntegerField(default=0)
    tokens_out = models.BigIntegerField(default=0)
    accounts_enc = models.BinaryField(null=True, blank=True)  # Fernet; removed when finished
    blueprint = models.FileField(upload_to=upload_path, null=True, blank=True, max_length=255)
    bundle = models.FileField(upload_to=upload_path, null=True, blank=True, max_length=255)
    passive = models.BooleanField(default=False)  # unverified domain (TZ SEC-9)
    source = models.CharField(max_length=4, choices=SOURCES, default="web")
    error = models.TextField(blank=True)
    cancel_requested = models.BooleanField(default=False)
    stats = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["owner", "created_at"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self) -> str:
        return f"#{self.pk} {self.mode} {self.role}"

    @property
    def finished(self) -> bool:
        return self.status in FINISHED

    @property
    def mode_label(self) -> str:
        return dict(self.MODES).get(self.mode, self.mode)

    @property
    def percent(self) -> int:
        if not self.progress_total:
            return 0
        return min(100, int(100 * self.progress_done / self.progress_total))


class JobEvent(models.Model):
    KINDS = [
        ("status", "Holat"),
        ("progress", "Jarayon"),
        ("log", "Log"),
        ("need_input", "Javob kerak"),
        ("artifact", "Natija"),
        ("cost", "Narx"),
    ]

    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="events")
    at = models.DateTimeField(auto_now_add=True)
    kind = models.CharField(max_length=12, choices=KINDS)
    payload = models.JSONField(default=dict)

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.job_id}:{self.kind}"


class InputRequest(models.Model):
    KINDS = [("sms_code", "SMS kodi"), ("captcha", "Captcha"), ("confirm", "Tasdiqlash")]

    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="input_requests")
    kind = models.CharField(max_length=12, choices=KINDS)
    message = models.TextField()
    value_enc = models.BinaryField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    answered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.job_id}:{self.kind}"


class Artifact(models.Model):
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="artifacts")
    name = models.CharField(max_length=120)
    label = models.CharField(max_length=120, blank=True)
    file = models.FileField(upload_to=artifact_path, max_length=255)
    size = models.BigIntegerField(default=0)
    sha256 = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        constraints = [models.UniqueConstraint(fields=["job", "name"], name="unique_artifact_name")]

    def __str__(self) -> str:
        return f"{self.job_id}/{self.name}"
