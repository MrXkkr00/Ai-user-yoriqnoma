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
    return soft, hard
