"""Start-up checks with a clear Uzbek fix for each problem (TZ FR-L11)."""

from __future__ import annotations

import urllib.request
from dataclasses import dataclass
from pathlib import Path

from yoriqnoma_core.writer.providers import OllamaProvider
from yoriqnoma_core.writer.providers.base import ProviderError


@dataclass
class Check:
    name: str
    ok: bool
    message: str
    fix: str = ""


def check_ollama(host: str, model: str) -> list[Check]:
    provider = OllamaProvider(host=host, model=model)
    try:
        models = provider.installed_models()
    except ProviderError as exc:
        return [
            Check("Ollama", False, str(exc), "Ollama dasturini ishga tushiring (ollama serve).")
        ]
    out = [Check("Ollama", True, f"ishlayapti ({host}), {len(models)} ta model o'rnatilgan")]
    if model not in models and f"{model}:latest" not in models:
        out.append(
            Check("Model", False, f"«{model}» o'rnatilmagan", f"Terminalda: ollama pull {model}")
        )
        return out
    try:
        vision = "vision" in provider.capabilities()
    except ProviderError as exc:
        return [*out, Check("Model", False, str(exc))]
    out.append(
        Check(
            "Model",
            vision,
            f"«{model}»"
            + (" rasmlarni ko'radi" if vision else " rasmlarni ko'rmaydi (vision yo'q)"),
            "" if vision else "Vision imkoniyati bor model tanlang (gemma4:26b).",
        )
    )
    return out


def check_playwright() -> Check:
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            path = Path(pw.chromium.executable_path)
    except Exception as exc:  # noqa: BLE001 - any failure means "not ready"
        return Check(
            "Playwright",
            False,
            f"ishga tushmadi: {exc}",
            "Terminalda: uv run playwright install chromium",
        )
    if not path.exists():
        return Check(
            "Playwright",
            False,
            "Chromium o'rnatilmagan",
            "Terminalda: uv run playwright install chromium",
        )
    return Check("Playwright", True, "Chromium o'rnatilgan")


def check_url(url: str) -> Check:
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:  # noqa: S310 - user's own site
            return Check("Sayt", True, f"{url} ochildi ({resp.status})")
    except OSError as exc:
        return Check(
            "Sayt",
            False,
            f"{url} ochilmadi: {exc}",
            "Sayt ishlayotganini va manzil to'g'ri ekanini tekshiring.",
        )


def all_checks(host: str, model: str) -> list[Check]:
    return [*check_ollama(host, model), check_playwright()]
