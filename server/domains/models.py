from __future__ import annotations

import secrets

from django.conf import settings
from django.db import models


def new_token() -> str:
    return secrets.token_urlsafe(24)


class Domain(models.Model):
    """A site host a server user owns (TZ SEC-9). Unverified hosts get passive jobs only."""

    METHODS = [
        ("wellknown", "/.well-known/yoriqnoma-verify.txt"),
        ("meta", '<meta name="yoriqnoma-verify">'),
        ("dns", "DNS TXT"),
    ]

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="domains"
    )
    host = models.CharField(max_length=253)
    token = models.CharField(max_length=64, default=new_token)
    verified_at = models.DateTimeField(null=True, blank=True)
    method = models.CharField(max_length=16, choices=METHODS, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["host"]
        constraints = [
            models.UniqueConstraint(fields=["owner", "host"], name="unique_domain_per_owner")
        ]

    def __str__(self) -> str:
        return self.host

    @property
    def verified(self) -> bool:
        return self.verified_at is not None

    @property
    def wellknown_url(self) -> str:
        return f"https://{self.host}/.well-known/yoriqnoma-verify.txt"

    @property
    def meta_tag(self) -> str:
        return f'<meta name="yoriqnoma-verify" content="{self.token}">'

    @property
    def dns_record(self) -> str:
        return f"yoriqnoma-verify={self.token}"
