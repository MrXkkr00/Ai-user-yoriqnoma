from __future__ import annotations

from django import forms
from django.contrib.auth.forms import UserCreationForm, UsernameField
from django.contrib.auth.models import User


class RegisterForm(UserCreationForm[User]):
    email = forms.EmailField(label="Email", required=True)

    class Meta:
        model = User
        field_classes = {"username": UsernameField}
        fields = ("username", "email")
        labels = {"username": "Foydalanuvchi nomi"}

    def clean_email(self) -> str:
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Bu email bilan hisob allaqachon bor")
        return str(email)
