"""Locale files -> flat key/text dictionary; t('a.b') calls -> text (TZ FR-S3)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from yoriqnoma_scanner.detect import ProjectInfo
from yoriqnoma_scanner.fs_guard import SafeFS
from yoriqnoma_scanner.parsers.base import ParseResult

PREFERRED = ("uz", "uz-latn", "uz_latn", "uz-uz", "en", "ru")


def flatten(data: Any, prefix: str = "") -> dict[str, str]:
    out: dict[str, str] = {}
    if isinstance(data, dict):
        for key, value in data.items():
            full = f"{prefix}.{key}" if prefix else str(key)
            out.update(flatten(value, full))
    elif isinstance(data, str):
        out[prefix] = data
    elif isinstance(data, int | float) and not isinstance(data, bool):
        out[prefix] = str(data)
    return out


def language_of(path: Path) -> str:
    stem = path.stem.lower()
    if stem in {"translation", "messages", "common", "index"}:
        return path.parent.name.lower()
    return stem


def pick_language(available: list[str], wanted: str = "uz") -> str | None:
    if wanted in available:
        return wanted
    for lang in PREFERRED:
        if lang in available:
            return lang
    return available[0] if available else None


class I18nParser:
    name = "i18n"

    def __init__(self, language: str = "uz") -> None:
        self.language = language

    def applies(self, project: ProjectInfo) -> bool:
        return bool(project.locales)

    def parse(self, project: ProjectInfo, fs: SafeFS) -> ParseResult:
        by_lang: dict[str, dict[str, str]] = {}
        result = ParseResult()
        for path in project.locales:
            text = fs.read_text(path)
            if text is None:
                continue
            try:
                data = json.loads(text)
            except json.JSONDecodeError as exc:
                result.notes.append(f"{fs.rel(path)}: JSON xatosi ({exc.msg})")
                continue
            by_lang.setdefault(language_of(path), {}).update(flatten(data))
        lang = pick_language(sorted(by_lang), self.language)
        if lang:
            result.i18n = by_lang[lang]
            if lang != self.language:
                result.notes.append(
                    f"i18n: «{self.language}» tili topilmadi, «{lang}» matnlari ishlatildi"
                )
        return result
