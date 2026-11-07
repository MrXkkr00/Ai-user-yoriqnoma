from __future__ import annotations

from django.db import models


class Project(models.Model):
    ENVIRONMENTS = [("staging", "Staging (sinov)"), ("production", "Production (ishchi sayt)")]
    MAILBOXES = [("dir", "Papka (.eml fayllar)"), ("mailpit", "Mailpit")]

    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=120, unique=True)
    source_dir = models.CharField(max_length=500, blank=True)
    base_url = models.URLField()
    environment = models.CharField(max_length=20, choices=ENVIRONMENTS, default="staging")
    mailbox_kind = models.CharField(max_length=20, choices=MAILBOXES, default="dir")
    mailbox_target = models.CharField(max_length=500, blank=True)
    language = models.CharField(max_length=8, default="uz")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.name

    def current_blueprint(self) -> BlueprintVersion | None:
        return self.blueprints.filter(is_current=True).order_by("-created_at").first()


class ProjectAccount(models.Model):
    """A test account for one role, given by the site owner (TZ FR-RL4)."""

    ALIASES = [("A", "A"), ("B", "B")]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="accounts")
    role = models.CharField(max_length=60)
    alias = models.CharField(max_length=1, choices=ALIASES, default="A")
    login = models.CharField(max_length=200)
    password_enc = models.BinaryField()  # Fernet, key in var/secret.key

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["project", "role", "alias"], name="one_account_per_alias"
            )
        ]

    def __str__(self) -> str:
        return f"{self.role}:{self.alias} ({self.login})"


class BlueprintVersion(models.Model):
    SOURCES = [("scan", "Skan"), ("upload", "Yuklangan")]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="blueprints")
    created_at = models.DateTimeField(auto_now_add=True)
    scanner_version = models.CharField(max_length=40, blank=True)
    source = models.CharField(max_length=10, choices=SOURCES, default="scan")
    path = models.CharField(max_length=500)
    report_path = models.CharField(max_length=500, blank=True)
    # {"exclude_pages": [...], "exclude_flows": [...], "rename_flows": {...}}
    overrides = models.JSONField(default=dict, blank=True)
    stats = models.JSONField(default=dict, blank=True)
    is_current = models.BooleanField(default=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.project.slug} @ {self.created_at:%Y-%m-%d %H:%M}"
