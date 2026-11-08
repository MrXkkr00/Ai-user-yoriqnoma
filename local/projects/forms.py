from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from django import forms

from projects.models import Project

if TYPE_CHECKING:
    _ProjectFormBase = forms.ModelForm[Project]
else:
    _ProjectFormBase = forms.ModelForm


class ProjectForm(_ProjectFormBase):
    class Meta:
        model = Project
        fields = [
            "name",
            "source_dir",
            "base_url",
            "environment",
            "mailbox_kind",
            "mailbox_target",
            "language",
        ]
        labels = {
            "name": "Loyiha nomi",
            "source_dir": "Kod papkasi (ixtiyoriy)",
            "base_url": "Sayt manzili (base URL)",
            "environment": "Muhit",
            "mailbox_kind": "Pochta",
            "mailbox_target": "Pochta papkasi yoki Mailpit manzili",
            "language": "Til",
        }
        help_texts = {
            "source_dir": "Masalan: D:\\loyihalar\\mening-saytim. Bo'sh bo'lsa, blueprint.json "
            "ni qo'lda yuklaysiz.",
            "mailbox_target": "Papka: sayt xatlarni .eml qilib yozadigan joy. Mailpit: "
            "http://127.0.0.1:8025",
        }

    def clean_source_dir(self) -> str:
        value = str(self.cleaned_data.get("source_dir") or "").strip()
        if value and not Path(value).is_dir():
            raise forms.ValidationError("Bunday papka topilmadi")
        return value

    def clean_base_url(self) -> str:
        value = str(self.cleaned_data["base_url"]).strip()
        if not value.startswith(("http://", "https://")):
            raise forms.ValidationError("Manzil http:// yoki https:// bilan boshlanishi kerak")
        return value


class AccountForm(forms.Form):
    role = forms.CharField(label="Rol", max_length=60)
    alias = forms.ChoiceField(label="Akkaunt", choices=[("A", "A"), ("B", "B")])
    login = forms.CharField(label="Login yoki email", max_length=200)
    password = forms.CharField(label="Parol", widget=forms.PasswordInput, max_length=200)


class UploadBlueprintForm(forms.Form):
    file = forms.FileField(label="blueprint.json")


class NewRunForm(forms.Form):
    OUTPUTS = [
        ("full", "To'liq yo'riqnoma (lokal, Ollama)"),
        ("blueprint", "Blueprint (server A uchun)"),
        ("bundle", "Bundle (server A' uchun)"),
    ]
    roles = forms.MultipleChoiceField(
        label="Rol", required=False, widget=forms.CheckboxSelectMultiple
    )
    output = forms.ChoiceField(
        label="Natija turi", choices=OUTPUTS, widget=forms.RadioSelect, initial="full"
    )
    model = forms.CharField(label="Model", required=False)
    formats = forms.MultipleChoiceField(
        label="Formatlar",
        required=False,
        widget=forms.CheckboxSelectMultiple,
        choices=[
            ("html", "HTML"),
            ("pdf", "PDF"),
            ("docx", "DOCX"),
            ("tour", "Interaktiv tur (Driver.js)"),
            ("gif", "GIF (har vazifa uchun)"),
        ],
        initial=["html", "pdf", "docx"],
    )

    def __init__(self, *args: Any, role_choices: list[tuple[str, str]], **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        roles = self.fields["roles"]
        assert isinstance(roles, forms.MultipleChoiceField)
        roles.choices = role_choices

    def clean(self) -> dict[str, Any]:
        data = super().clean() or {}
        if data.get("output") != "blueprint" and not data.get("roles"):
            raise forms.ValidationError("Kamida bitta rolni tanlang")
        return data
