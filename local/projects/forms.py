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
            "mode",
            "source_dir",
            "base_url",
            "environment",
            "mailbox_kind",
            "mailbox_target",
            "language",
        ]
        labels = {
            "name": "Loyiha nomi",
            "mode": "Sizda nima bor?",
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

    admin_login = forms.CharField(
        label="Admin login (email yoki foydalanuvchi nomi)", required=False, max_length=200
    )
    admin_password = forms.CharField(
        label="Admin paroli",
        required=False,
        max_length=200,
        widget=forms.PasswordInput(render_value=False),
        help_text="Faqat test foydalanuvchilarni yaratish va ish tugagach o'chirish uchun. "
        "Shifrlanib saqlanadi. Tahrirlashda bo'sh qoldirsangiz, eskisi qoladi.",
    )
    admin_path = forms.CharField(
        label="Admin panel manzili (ixtiyoriy)",
        required=False,
        max_length=200,
        help_text="Masalan: /admin/ (Django) yoki /admin/users",
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["mode"].widget = forms.RadioSelect(choices=Project.MODES)
        if self.instance.pk:
            self.fields["admin_login"].initial = self.instance.admin_login
            self.fields["admin_path"].initial = self.instance.admin_path

    def clean(self) -> dict[str, Any]:
        data = super().clean() or {}
        mode = data.get("mode", "code")
        if mode in {"code", "code_admin"} and not data.get("source_dir"):
            self.add_error("source_dir", "Bu rejimda kod papkasi kerak")
        if mode in {"code_admin", "admin"}:
            if not data.get("admin_login"):
                self.add_error("admin_login", "Bu rejimda admin login kerak")
            has_old = bool(self.instance.pk and self.instance.admin_password_enc)
            if not data.get("admin_password") and not has_old:
                self.add_error("admin_password", "Bu rejimda admin paroli kerak")
        return data

    def save(self, commit: bool = True) -> Project:
        from yoriqnoma_local.keys import encrypt

        project: Project = super().save(commit=False)
        project.admin_login = str(self.cleaned_data.get("admin_login") or "").strip()
        project.admin_path = str(self.cleaned_data.get("admin_path") or "").strip()
        password = str(self.cleaned_data.get("admin_password") or "")
        if password:
            project.admin_password_enc = encrypt(password)
        if project.mode == "code":
            project.admin_login, project.admin_password_enc = "", None
        if commit:
            project.save()
        return project

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
