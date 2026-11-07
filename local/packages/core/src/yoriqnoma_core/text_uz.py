"""One canonical form for Uzbek Latin text in both alphabets.

Some sites (for example kun.uz) write the new alphabet: «Öçiriş» means «O'chirish».
Button and field names are compared after ``normalize_uz`` in the policy engine, the
writer's name check and the HTML search (its JS copy lives in render/templates).
"""

from __future__ import annotations

import re
import unicodedata

APOSTROPHES = "'‘’`ʻʼ´′"
_APOS_RE = re.compile(f"[{re.escape(APOSTROPHES)}]")
NEW_LETTERS = {
    "ö": "o'",
    "ğ": "g'",
    "ş": "sh",
    "ç": "ch",
    "ı": "i",
    "ñ": "ng",
}


def normalize_uz(text: str) -> str:
    """Lower case, one apostrophe, new-alphabet letters as old Latin, single spaces."""
    low = unicodedata.normalize("NFC", text).lower()
    low = "".join(NEW_LETTERS.get(ch, ch) for ch in low)
    low = _APOS_RE.sub("'", low)
    low = re.sub(r"\s+", " ", low)
    return low.strip()


def contains_word(text: str, word: str) -> bool:
    """``word`` (normalised) appears in ``text`` (normalised) at word boundaries."""
    hay = normalize_uz(text)
    needle = normalize_uz(word)
    if not needle:
        return False
    return re.search(rf"(?<![\w']){re.escape(needle)}(?![\w'])", hay) is not None
