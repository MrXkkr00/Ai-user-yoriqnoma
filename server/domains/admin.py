from django.contrib import admin

from domains.models import Domain


@admin.register(Domain)
class DomainAdmin(admin.ModelAdmin[Domain]):
    list_display = ["host", "owner", "verified_at", "method", "created_at"]
    list_filter = ["method"]
    search_fields = ["host", "owner__username"]
