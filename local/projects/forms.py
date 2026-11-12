from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from django import forms

from projects.models import Project
from yoriqnoma_core.safety.sso import invalid_entries, parse_hosts
from yoriqnoma_local.keys import encrypt

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
            "sso_hosts",
            "environment",
            "mailbox_kind",
            "mailbox_target",
            "language",
        ]
        labels = {
            "name": "Loyiha nomi",
            "mode": "Sizda nima bor?",
            "source_dir": "Kod papkasi",
            "base_url": "Sayt manzili (base URL)",
            "sso_hosts": "Kirish (SSO) domeni (ixtiyoriy)",
            "environment": "Muhit",
            "mailbox_kind": "Pochta (ixtiyoriy)",
            "mailbox_target": "Pochta papkasi yoki Mailpit manzili (ixtiyoriy)",
            "language": "Til",
        }
        help_texts = {
            "source_dir": "Loyiha kodi turgan papka, masalan: D:/loyihalar/mening-saytim. "
            "Vosita kodni faqat o'qiydi (maxfiy fayllarsiz): sahifalar, rollar va vazifalarni "
            "undan oladi.",
            "sso_hosts": "Sayt kirish uchun boshqa domenga o'tsa (masalan, auth.sayt.uz), "
            "o'sha domenni yozing; bir nechta bo'lsa, vergul bilan. Faqat shu domenlarga "
            "kirish so'rovlari ruxsat etiladi va parol faqat sayt hamda shu domenlarga yuboriladi.",
            "mailbox_target": "Faqat sayt ro'yxatdan o'tishda email tasdiqlashni so'rasa "
            "kerak; bo'sh qolsa, tasdiqlash xatlari o'qilmaydi. "
            "Papka: sayt xatlarni .eml qilib yozadigan joy. Mailpit: "
            "http://127.0.0.1:8025",
        }

    # an address typed without "http(s)://" is read as https (the Django 6.0 default)
    base_url = forms.URLField(label="Sayt manzili (base URL)", assume_scheme="https")
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
        help_text="Masalan: /admin/ (Django) yoki /admin/users. Bo'sh qolsa, vosita panelni "
        "o'zi qidiradi: odatiy manzillarni sinaydi, so'ng admin sifatida saytga kirib "
        "uning havolalaridan topadi.",
    )

    account_role = forms.CharField(
        label="Rol nomi",
        required=False,
        max_length=60,
        help_text="Yo'riqnoma shu rol uchun yoziladi, masalan: Menejer, Sotuvchi, Mijoz.",
    )
    account_login = forms.CharField(
        label="Shu rol egasining logini", required=False, max_length=200
    )
    account_password = forms.CharField(
        label="Shu rol egasining paroli",
        required=False,
        max_length=200,
        widget=forms.PasswordInput(render_value=False),
        help_text="Shifrlanib saqlanadi. Tahrirlashda bo'sh qoldirsangiz, eskisi qoladi. "
        "Vosita shu akkaunt bilan saytga kirib, unga ochiq havolalarning hammasini ko'radi.",
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["mode"].widget = forms.RadioSelect(choices=Project.MODES)
        self.fields["mailbox_kind"].required = False
        self.fields["mailbox_target"].required = False
        if self.instance.pk:
            self.fields["admin_login"].initial = self.instance.admin_login
            self.fields["admin_path"].initial = self.instance.admin_path
            self.fields["account_role"].initial = self.instance.account_role
            given = self.instance.accounts.filter(alias="A").first()
            if given is not None:
                self.fields["account_login"].initial = given.login

    def clean(self) -> dict[str, Any]:
        data = super().clean() or {}
        mode = data.get("mode", "code")
        if not data.get("mailbox_kind"):
            data["mailbox_kind"] = "dir"
        if mode in {"code", "code_admin"} and not data.get("source_dir"):
            self.add_error("source_dir", "Bu rejimda kod papkasi kerak")
        if mode in {"code_admin", "admin"}:
            if not data.get("admin_login"):
                self.add_error("admin_login", "Bu rejimda admin login kerak")
            has_old = bool(self.instance.pk and self.instance.admin_password_enc)
            if not data.get("admin_password") and not has_old:
                self.add_error("admin_password", "Bu rejimda admin paroli kerak")
        if mode == "account":
            self._clean_account(data)
        return data

    def _clean_account(self, data: dict[str, Any]) -> None:
        from yoriqnoma_core.provision.base import classify_role

        name = str(data.get("account_role") or "").strip()
        if not name:
            self.add_error("account_role", "Bu rejimda rol nomi kerak")
        elif classify_role(name, name, "forma", "role").kind != "role":
            self.add_error(
                "account_role",
                "Administrator va adminga o'xshash rollar uchun yo'riqnoma yozilmaydi",
            )
        if not data.get("account_login"):
            self.add_error("account_login", "Bu rejimda rol egasining logini kerak")
        has_old = bool(self.instance.pk and self.instance.accounts.filter(alias="A").exists())
        if not data.get("account_password") and not has_old:
            self.add_error("account_password", "Bu rejimda rol egasining paroli kerak")

    def save(self, commit: bool = True) -> Project:
        from yoriqnoma_local.keys import encrypt

        project: Project = super().save(commit=False)
        project.admin_login = str(self.cleaned_data.get("admin_login") or "").strip()
        project.admin_path = str(self.cleaned_data.get("admin_path") or "").strip()
        password = str(self.cleaned_data.get("admin_password") or "")
        if password:
            project.admin_password_enc = encrypt(password)
        if project.mode in {"code", "account"}:
            project.admin_login, project.admin_password_enc = "", None
        project.account_role = (
            str(self.cleaned_data.get("account_role") or "").strip()
            if project.mode == "account"
            else ""
        )
        if commit:
            project.save()
            if project.mode == "account":
                self._save_account(project)
        return project

    def _save_account(self, project: Project) -> None:
        from projects.models import ProjectAccount
        from yoriqnoma_core.provision.base import role_id

        role = role_id(project.account_role)
        old = project.accounts.filter(alias="A").first()  # any role: the password may stay
        project.accounts.exclude(role=role, alias="A").delete()  # one role, one account
        password = str(self.cleaned_data.get("account_password") or "")
        login = str(self.cleaned_data.get("account_login") or "").strip()
        enc = old.password_enc if (not password and old is not None) else encrypt(password)
        ProjectAccount.objects.update_or_create(
            project=project, role=role, alias="A", defaults={"login": login, "password_enc": enc}
        )

    def clean_source_dir(self) -> str:
        value = str(self.cleaned_data.get("source_dir") or "").strip()
        if value and not Path(value).is_dir():
            raise forms.ValidationError("Bunday papka topilmadi")
        return value

    def clean_sso_hosts(self) -> str:
        value = str(self.cleaned_data.get("sso_hosts") or "").strip()
        bad = invalid_entries(value)
        if bad:
            raise forms.ValidationError(
                "Domen nomi noto'g'ri: " + ", ".join(bad) + ". Masalan: auth.sayt.uz"
            )
        return ", ".join(parse_hosts(value))

    def clean_name(self) -> str:
        name = str(self.cleaned_data["name"]).strip()
        same = Project.objects.filter(name__iexact=name)
        if self.instance.pk:
            same = same.exclude(pk=self.instance.pk)
        if same.exists():
            raise forms.ValidationError("Bunday nomli loyiha bor: boshqa nom bering")
        return name

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
