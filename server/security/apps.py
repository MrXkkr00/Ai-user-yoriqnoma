from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class SecurityConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "security"
    verbose_name = _("Xavfsizlik")

    def ready(self) -> None:
        from security import checks  # noqa: F401  (registers the system checks)
