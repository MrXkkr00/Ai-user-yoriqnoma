from __future__ import annotations

from django.db import models

from projects.models import BlueprintVersion, Project


class Run(models.Model):
    OUTPUTS = [
        ("full", "To'liq yo'riqnoma"),
        ("blueprint", "Blueprint (server A uchun)"),
        ("bundle", "Bundle (server A' uchun)"),
    ]
    STATUSES = [
        ("queued", "Navbatda"),
        ("running", "Bajarilmoqda"),
        ("waiting_input", "Ma'lumot kutilmoqda"),
        ("done", "Tayyor"),
        ("failed", "Xato"),
        ("cancelled", "Bekor qilindi"),
    ]
    STAGES = [
        ("explore", "Saytni o'rganish"),
        ("write", "Matn yozish"),
        ("render", "Fayllar tayyorlash"),
        ("package", "Paketlash"),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="runs")
    blueprint = models.ForeignKey(BlueprintVersion, on_delete=models.PROTECT, related_name="runs")
    role = models.CharField(max_length=60, blank=True)
    output = models.CharField(max_length=20, choices=OUTPUTS, default="full")
    status = models.CharField(max_length=20, choices=STATUSES, default="queued")
    stage = models.CharField(max_length=20, choices=STAGES, blank=True)
    progress_done = models.IntegerField(default=0)
    progress_total = models.IntegerField(default=0)
    model = models.CharField(max_length=100, blank=True)
    formats = models.JSONField(default=list, blank=True)
    run_dir = models.CharField(max_length=500)
    stats = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True)
    cancel_requested = models.BooleanField(default=False)
    # update of an earlier result (T30): changelog against it, same fakes
    previous = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="updates"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Run {self.pk} ({self.output}, {self.role or '-'})"

    @property
    def finished(self) -> bool:
        return self.status in {"done", "failed", "cancelled"}

    @property
    def percent(self) -> int:
        if not self.progress_total:
            return 0
        return min(100, int(100 * self.progress_done / self.progress_total))


class RunEvent(models.Model):
    run = models.ForeignKey(Run, on_delete=models.CASCADE, related_name="events")
    at = models.DateTimeField(auto_now_add=True)
    level = models.CharField(max_length=10, default="info")
    stage = models.CharField(max_length=20, blank=True)
    message = models.TextField()

    class Meta:
        ordering = ["at", "pk"]

    def __str__(self) -> str:
        return f"[{self.level}] {self.message[:60]}"


class InputRequest(models.Model):
    KINDS = [("sms_code", "SMS kodi"), ("captcha", "Captcha"), ("confirm", "Tasdiqlash")]

    run = models.ForeignKey(Run, on_delete=models.CASCADE, related_name="inputs")
    kind = models.CharField(max_length=20, choices=KINDS)
    message = models.TextField()
    value_enc = models.BinaryField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    answered_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"{self.kind}: {self.message[:60]}"
