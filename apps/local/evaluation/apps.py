from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class EvaluationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "evaluation"
    verbose_name = _("Modellarni solishtirish")
