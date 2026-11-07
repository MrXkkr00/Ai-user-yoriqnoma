from __future__ import annotations

from django.db import models


class AppSettings(models.Model):
    """Single row with the local app's settings (Ollama connection and default model)."""

    ollama_host = models.URLField(default="http://127.0.0.1:11434")
    ollama_model = models.CharField(max_length=100, default="gemma4:26b")
    num_ctx = models.IntegerField(default=24576)
    language = models.CharField(max_length=8, default="uz")

    class Meta:
        verbose_name = "Sozlamalar"

    def __str__(self) -> str:
        return f"Ollama {self.ollama_host} ({self.ollama_model})"

    @classmethod
    def load(cls) -> AppSettings:
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
