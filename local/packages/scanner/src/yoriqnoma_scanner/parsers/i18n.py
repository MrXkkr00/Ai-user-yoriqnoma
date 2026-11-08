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


_PO_ESCAPES = {"n": "\n", "t": "\t", '"': '"', "\\": "\\"}


def _po_unquote(line: str) -> str:
    body = line.strip()
    if len(body) >= 2 and body[0] == '"' and body[-1] == '"':
        body = body[1:-1]
    out: list[str] = []
    i = 0
    while i < len(body):
        ch = body[i]
        if ch == "\\" and i + 1 < len(body):
            out.append(_PO_ESCAPES.get(body[i + 1], body[i + 1]))
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def read_po(text: str) -> dict[str, str]:
    """A gettext catalogue -> {msgid: msgstr}; untranslated and fuzzy entries are skipped."""
    catalogue: dict[str, str] = {}
    for block in text.replace("\r\n", "\n").split("\n\n"):
        fuzzy = False
        fields: dict[str, str] = {}
        current: str | None = None
        for raw in block.split("\n"):
            line = raw.strip()
            if line.startswith("#,") and "fuzzy" in line:
                fuzzy = True
            if not line or line.startswith("#"):
                continue
            if line.startswith('"') and current is not None:
                fields[current] += _po_unquote(line)
                continue
            key, _, rest = line.partition(" ")
            current = key
            fields[key] = _po_unquote(rest)
        msgid = fields.get("msgid", "")
        msgstr = fields.get("msgstr", fields.get("msgstr[0]", ""))
        if msgid and msgstr and not fuzzy:
            catalogue[msgid] = msgstr
    return catalogue


def po_language(path: Path) -> str:
    """``locale/uz/LC_MESSAGES/django.po`` -> "uz"; ``uz.po`` -> "uz"."""
    parts = [p.lower() for p in path.parts]
    if len(parts) >= 3 and parts[-2] == "lc_messages":
        return parts[-3].replace("_", "-")
    return path.stem.lower().replace("_", "-")


def load_po_catalogue(
    fs: SafeFS, files: list[Path], wanted: str, notes: list[str]
) -> dict[str, str]:
    """Translations of the wanted language (or the best other one) from all .po files."""
    by_lang: dict[str, dict[str, str]] = {}
    for path in files:
        text = fs.read_text(path)
        if text is not None:
            by_lang.setdefault(po_language(path), {}).update(read_po(text))
    lang = pick_language(sorted(by_lang), wanted)
    if lang is None:
        return {}
    if lang != wanted:
        notes.append(f"gettext: «{wanted}» tarjimasi topilmadi, «{lang}» ishlatildi")
    return by_lang[lang]


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
