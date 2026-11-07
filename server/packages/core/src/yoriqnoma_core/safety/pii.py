"""Personal data detection (TZ FR-E10, SEC-7).

``find_pii`` finds emails, Uzbek phones, card numbers (Luhn), passports, JSHSHIR (PINFL),
labelled names and addresses. Values the tool generated (``test_values``) and values kept
as public (organization and published content, ``public_values``) are ignored.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit

PIIKind = Literal["email", "phone", "card", "passport", "pinfl", "name", "address"]

EMAIL_RE = re.compile(
    r"(?<![\w.+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}"
)
PHONE_RE = re.compile(
    r"(?<![\w+])(?:"
    r"\+?998[\s\-()]*\d{2}[\s\-)]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}"  # +998 90 123 45 67
    r"|\(?\d{2}\)?[\s\-]\d{3}[\s\-]\d{2}[\s\-]\d{2}"  # 90 123-45-67 (separators required)
    r")(?!\d)"
)
CARD_RE = re.compile(r"(?<!\d)(?:\d[ \-]?){15}\d(?!\d)")
PINFL_RE = re.compile(r"(?<!\d)\d{14}(?!\d)")
PASSPORT_RE = re.compile(r"(?<![A-Z])[A-Z]{2}\s?\d{7}(?!\d)")
_NAME_WORD = r"[A-ZА-ЯЁЎҚҒҲÖÇŞĞ][\w'ʻ’`-]+"
NAME_LABEL_RE = re.compile(
    r"(?i:\b(?:ism(?:i)?|f\.?\s?i\.?\s?sh\.?|familiya|mijoz|qabul\s*qiluvchi|jo'natuvchi|"
    r"muallif|фио|имя|получатель|name|full\s*name|customer|recipient))\s*[:\-–]\s*"
    rf"({_NAME_WORD}(?:\s+{_NAME_WORD}){{0,2}})"
)
ADDRESS_LABEL_RE = re.compile(
    r"(?i:\b(?:manzil(?:i)?|yashash\s*joyi|адрес|address))\s*[:\-–]\s*([^\n|;\"]{5,80})"
)
NAME_HEADERS = {
    "ism",
    "ismi",
    "f.i.sh",
    "f.i.sh.",
    "fish",
    "familiya",
    "ism familiya",
    "to'liq ism",
    "mijoz",
    "xaridor",
    "qabul qiluvchi",
    "muallif",
    "foydalanuvchi",
    "фио",
    "имя",
    "клиент",
    "покупатель",
    "name",
    "full name",
    "customer",
    "client",
    "author",
    "recipient",
}
PII_FIELD_RE = re.compile(
    r"(^|_)(full_?name|first_?name|last_?name|middle_?name|fio|customer_?name|author_?name|"
    r"user_?name|other_?name|sender_?name|recipient_?name|email|e_?mail|phone|tel|mobile|"
    r"address|card(_?number)?|passport|pinfl|jshshir|birth_?date|birthday|avatar(_?url)?|"
    r"photo(_?url)?)($|_)",
    re.I,
)
NOT_PII_FIELDS = {"email_verified", "notify_email", "phone_verified", "product_name", "username"}


@dataclass(frozen=True)
class PIIMatch:
    kind: PIIKind
    value: str
    start: int
    end: int


def luhn_ok(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def normalize_value(kind: str, value: str) -> str:
    """Canonical form used to compare values (email lower, phone digits, names folded)."""
    if kind == "email":
        return value.strip().lower()
    if kind in {"phone", "card", "pinfl"}:
        digits = re.sub(r"\D", "", value)
        return digits[-9:] if kind == "phone" else digits
    if kind == "passport":
        return re.sub(r"\s", "", value).upper()
    return re.sub(r"\s+", " ", value).strip().casefold()


def _ignore_set(values: Iterable[str]) -> set[str]:
    out: set[str] = set()
    for value in values:
        if not value:
            continue
        out.add(value.strip().casefold())
        out.add(re.sub(r"\s+", " ", value).strip().casefold())
        digits = re.sub(r"\D", "", value)
        if len(digits) >= 9:
            out.add(digits[-9:])
            out.add(digits)
    return out


def find_pii(text: str, ignore: Iterable[str] = ()) -> list[PIIMatch]:
    """Personal values in ``text``, minus ignored (generated or public) values."""
    if not text:
        return []
    skip = _ignore_set(ignore)
    found: list[PIIMatch] = []
    taken: list[tuple[int, int]] = []

    def add(kind: PIIKind, value: str, start: int, end: int) -> None:
        if any(not (end <= a or start >= b) for a, b in taken):
            return
        norm = normalize_value(kind, value)
        if norm in skip or value.strip().casefold() in skip:
            return
        taken.append((start, end))
        found.append(PIIMatch(kind, value, start, end))

    for m in EMAIL_RE.finditer(text):
        add("email", m.group(0), m.start(), m.end())
    for m in CARD_RE.finditer(text):
        digits = re.sub(r"\D", "", m.group(0))
        if len(digits) == 16 and luhn_ok(digits):
            add("card", m.group(0), m.start(), m.end())
    for m in PINFL_RE.finditer(text):
        add("pinfl", m.group(0), m.start(), m.end())
    for m in PHONE_RE.finditer(text):
        digits = re.sub(r"\D", "", m.group(0))
        if len(digits) in (9, 12):
            add("phone", m.group(0).strip(), m.start(), m.end())
    for m in PASSPORT_RE.finditer(text):
        add("passport", m.group(0), m.start(), m.end())
    for m in NAME_LABEL_RE.finditer(text):
        add("name", m.group(1), m.start(1), m.end(1))
    for m in ADDRESS_LABEL_RE.finditer(text):
        add("address", m.group(1).strip(), m.start(1), m.start(1) + len(m.group(1).strip()))
    return sorted(found, key=lambda x: x.start)


def mask_text(text: str, matches: list[PIIMatch] | None = None) -> str:
    """Replace found values with a mask (fallback and log use)."""
    matches = find_pii(text) if matches is None else matches
    out = text
    for m in sorted(matches, key=lambda x: x.start, reverse=True):
        out = out[: m.start] + "•••" + out[m.end :]
    return out


def is_pii_field(name: str) -> bool:
    """A JSON / form field name that may hold a person's data."""
    low = name.lower()
    if low in NOT_PII_FIELDS:
        return False
    return bool(PII_FIELD_RE.search(low))


def is_name_header(text: str) -> bool:
    """Table column header of a person-name column («Ism», «F.I.Sh», «Mijoz», «ФИО»...)."""
    low = re.sub(r"\s+", " ", text.replace("ʻ", "'").replace("’", "'")).strip().casefold()
    return low.rstrip(":") in NAME_HEADERS


def site_host(base_url: str) -> str:
    host = (urlsplit(base_url).hostname or "").lower()
    return host.removeprefix("www.")


def is_site_email(email: str, base_url: str) -> bool:
    """Email on the site's own domain or a subdomain: organization data, kept as is."""
    host = site_host(base_url)
    domain = email.rsplit("@", 1)[-1].lower().removeprefix("www.")
    if not host or not domain:
        return False
    return domain == host or domain.endswith("." + host) or host.endswith("." + domain)
