from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from helpdesk.models import Ticket, User


@admin.register(User)
class HelpdeskUserAdmin(UserAdmin):
    """The usual Django user admin plus the help desk's role and phone."""

    fieldsets = (*UserAdmin.fieldsets, ("Yordam markazi", {"fields": ("role", "phone")}))
    add_fieldsets = (
        *UserAdmin.add_fieldsets,
        ("Yordam markazi", {"fields": ("email", "role", "phone")}),
    )
    list_display = ("username", "email", "role", "is_staff")
    list_filter = ("role", "is_staff")


admin.site.register(Ticket)
