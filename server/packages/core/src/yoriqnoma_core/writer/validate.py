"""Checks of LLM text (TZ FR-W3): names in «...» exist on the page, no personal data, no admin.

Names are compared after ``normalize_uz``, so «Yuborish» matches a site button «Yuboriş».
"""

from __future__ import annotations

import difflib
import re
from collections.abc import Iterable

from yoriqnoma_core.safety.pii import find_pii
from yoriqnoma_core.text_uz import normalize_uz

QUOTED = re.compile(r"«([^»]{1,80})»")
ADMIN = re.compile(r"\b(admin\w*|administrator\w*|superadmin|админ\w*)\b", re.I)
# What a small model leaks into a text field: tags (</intro>, <tasks>), markdown, code fences.
MARKUP = re.compile(r"</?[A-Za-z][A-Za-z0-9_-]*(?:\s[^<>]*)?/?>|```|\*\*|^#{1,6}\s", re.M)
LIST_ONE = re.compile(r"(?:^|\s)1[.)]\s+\S")
LIST_TWO = re.compile(r"(?:^|\s)2[.)]\s+\S")
RECORD_NO = re.compile(r"#\d+")
HEADING_NO = re.compile(r"(?:^|[.!?]\s+)\d{1,2}\.\s+[A-ZÀ-ÝО-Я«]")


def quoted_names(text: str) -> list[str]:
    return [m.strip() for m in QUOTED.findall(text)]


def known_set(names: Iterable[str]) -> set[str]:
    return {normalize_uz(n) for n in names if n and n.strip()}


def name_matches(name: str, known: set[str]) -> bool:
    norm = normalize_uz(name)
    if not norm or norm in known:
        return True
    for k in known:
        if len(norm) >= 4 and (norm in k or k in norm):
            return True
        if difflib.SequenceMatcher(None, norm, k).ratio() >= 0.85:
            return True
    return False


def check_text(
    text: str,
    known: set[str],
    ignore: Iterable[str],
    allow_admin_word: bool = False,
) -> tuple[list[str], list[str]]:
    """(soft errors, hard errors). Hard errors (personal data, admin) must never be kept."""
    soft: list[str] = []
    hard: list[str] = []
    for name in quoted_names(text):
        if not name_matches(name, known):
            soft.append(f"«{name}» nomi sahifada topilmadi")
    pii = find_pii(text, ignore)
    if pii:
        hard.append("matnda shaxsiy ma'lumot bor: " + ", ".join(sorted({m.kind for m in pii})))
    if not allow_admin_word and ADMIN.search(text):
        hard.append("matnda administrator yoki admin qismi tilga olingan")
    format_soft, format_hard = format_problems(text)
    return soft + format_soft, hard + format_hard


def format_problems(text: str) -> tuple[list[str], list[str]]:
    """(soft, hard) problems of the shape of a text: leaked markup and run-on lists.

    Markup and a numbered list squeezed into one paragraph are never kept (a template
    sentence is used instead); a record number («#4») is asked again and then flagged.
    """
    soft: list[str] = []
    hard: list[str] = []
    if MARKUP.search(text):
        hard.append("matnda teg yoki markdown belgilari bor (faqat oddiy gaplar yozing)")
    if chr(10) in text.strip() or chr(13) in text.strip():
        hard.append("matn bir necha abzasdan iborat (bitta abzasga yozing)")
    if HEADING_NO.search(text):
        hard.append("matnda bo'lim sarlavhasi yoki nomerli band bor (oddiy gaplar yozing)")
    if LIST_ONE.search(text) and LIST_TWO.search(text):
        hard.append("matnda nomerlangan ro'yxat bor (oddiy gaplar bilan yozing)")
    if RECORD_NO.search(text):
        soft.append("aniq yozuv raqami (#...) yozmang: «buyurtma» deb umumiy yozing")
    return soft, hard
