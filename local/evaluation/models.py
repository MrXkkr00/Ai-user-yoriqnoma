from __future__ import annotations

from django.db import models


class EvalRun(models.Model):
    """Comparison of Ollama models on the golden set (TZ FR-L12)."""

    STATUSES = [
        ("queued", "Navbatda"),
        ("running", "Bajarilmoqda"),
        ("done", "Tayyor"),
        ("failed", "Xato"),
    ]

    created_at = models.DateTimeField(auto_now_add=True)
    model_names = models.JSONField(default=list)
    golden_dir = models.CharField(max_length=500)
    status = models.CharField(max_length=20, choices=STATUSES, default="queued")
    summary = models.JSONField(default=dict, blank=True)  # model -> metrics
    error = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Eval {self.pk}: {', '.join(self.model_names)}"


class EvalSample(models.Model):
    run = models.ForeignKey(EvalRun, on_delete=models.CASCADE, related_name="samples")
    model = models.CharField(max_length=100)
    case_id = models.CharField(max_length=100)
    task = models.CharField(max_length=40, default="describe_flow")
    text = models.TextField(blank=True)
    metrics = models.JSONField(default=dict)
    score = models.PositiveSmallIntegerField(null=True, blank=True)  # 1-5, by a person

    class Meta:
        ordering = ["case_id", "model"]

    def __str__(self) -> str:
        return f"{self.model} / {self.case_id}"
