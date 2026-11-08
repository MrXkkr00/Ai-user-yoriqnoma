from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.core.validators import RegexValidator
from django.utils.translation import gettext_lazy as _

from helpdesk.models import Ticket, User

PHONE = RegexValidator(r"^\+998\d{9}$", _("Telefon +998XXXXXXXXX ko'rinishida bo'lsin"))


class SignUpForm(UserCreationForm):
    phone = forms.CharField(label=_("Telefon"), validators=[PHONE])

    class Meta:
        model = User
        fields = ["username", "email", "phone"]


class TicketForm(forms.ModelForm):
    contact_phone = forms.CharField(label=_("Aloqa telefoni"), validators=[PHONE])

    class Meta:
        model = Ticket
        fields = ["subject", "body", "contact_phone"]


class ReplyForm(forms.Form):
    text = forms.CharField(label=_("Javob"), widget=forms.Textarea, min_length=2, max_length=2000)


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "phone"]
