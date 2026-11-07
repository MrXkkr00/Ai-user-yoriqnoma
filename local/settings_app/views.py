from __future__ import annotations

from typing import TYPE_CHECKING

from django import forms
from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from settings_app.models import AppSettings
from yoriqnoma_local.health import check_ollama

if TYPE_CHECKING:
    _SettingsFormBase = forms.ModelForm[AppSettings]
else:
    _SettingsFormBase = forms.ModelForm


class SettingsForm(_SettingsFormBase):
    class Meta:
        model = AppSettings
        fields = ["ollama_host", "ollama_model", "num_ctx", "language"]
        labels = {
            "ollama_host": "Ollama manzili",
            "ollama_model": "Model",
            "num_ctx": "Kontekst hajmi (num_ctx)",
            "language": "Til",
        }

    def clean_num_ctx(self) -> int:
        value = int(self.cleaned_data["num_ctx"])
        if not 4096 <= value <= 131072:
            raise forms.ValidationError("4096 dan 131072 gacha bo'lsin (tavsiya: 16384–32768)")
        return value


def installed_models(host: str) -> list[str]:
    from yoriqnoma_core.writer.providers import OllamaProvider
    from yoriqnoma_core.writer.providers.base import ProviderError

    try:
        return OllamaProvider(host=host).installed_models()
    except ProviderError:
        return []


@require_http_methods(["GET", "POST"])
def settings_view(request: HttpRequest) -> HttpResponse:
    cfg = AppSettings.load()
    form = SettingsForm(request.POST or None, instance=cfg)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Sozlamalar saqlandi.")
        return redirect("settings")
    return render(
        request, "settings.html", {"form": form, "models": installed_models(cfg.ollama_host)}
    )


@require_POST
def settings_test(request: HttpRequest) -> HttpResponse:
    cfg = AppSettings.load()
    checks = check_ollama(cfg.ollama_host, cfg.ollama_model)
    return render(request, "partials/checks.html", {"checks": checks})
