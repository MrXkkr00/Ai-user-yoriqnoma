from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _


class User(AbstractUser):
    class Role(models.TextChoices):
        CUSTOMER = "customer", _("Mijoz")
        SUPPORT = "support", _("Operator")
        ADMIN = "admin", _("Administrator")

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.CUSTOMER)
    phone = models.CharField(_("Telefon"), max_length=20, blank=True)


class Ticket(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", _("Ochiq")
        ANSWERED = "answered", _("Javob berilgan")
        CLOSED = "closed", _("Yopilgan")
        ARCHIVED = "archived", _("Arxivlangan")

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="tickets"
    )
    subject = models.CharField(_("Mavzu"), max_length=120)
    body = models.TextField(_("Murojaat matni"))
    contact_phone = models.CharField(_("Aloqa telefoni"), max_length=20)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.subject


class Reply(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="replies")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    text = models.TextField(_("Javob"))
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.text[:40]
