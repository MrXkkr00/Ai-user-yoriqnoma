"""Uzbek sentence templates for steps (TZ FR-W2: steps are written by templates, not the LLM).

Button and field names are quoted «...» exactly as on the site, even when the site uses
the new Latin alphabet («Yuboriş»); the sentence around them is ordinary Latin.
"""

from __future__ import annotations

import re

from yoriqnoma_schemas import Step

CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"


def marker_symbol(n: int) -> str:
    return CIRCLED[n - 1] if 1 <= n <= len(CIRCLED) else f"({n})"


def _rule(rules: str | None, key: str) -> str | None:
    match = re.search(rf"(?:^|\|){key}:([^|]+)", rules or "")
    return match.group(1) if match else None


def fill_hint(step: Step) -> str:
    data = step.data or ""
    rules = step.rules
    label = (step.target.label or step.target.name or "") if step.target else ""
    low = label.lower()
    if data in {"fake:password"} or "parol" in low:
        minimum = _rule(rules, "min")
        tail = f" (kamida {minimum} ta belgi)" if minimum and minimum not in {"0", "1"} else ""
        return f"parolingizni{tail}"
    if data == "peer:email":
        return "xabar oluvchining emailini"
    if data == "fake:email" or "email" in low:
        return "email manzilingizni"
    if data == "fake:phone_uz" or "telefon" in low:
        return "telefon raqamingizni +998901234567 ko'rinishida"
    if data == "fake:full_name":
        return "to'liq ismingizni"
    if data == "fake:address" or "manzil" in low:
        return "manzilni"
    if data.startswith("literal:") and data[8:].isdigit():
        lo, hi = _rule(rules, "min"), _rule(rules, "max")
        if lo and hi:
            return f"sonni ({lo} dan {hi} gacha)"
        return "sonni"
    if data == "fake:date":
        return "sanani"
    minimum = _rule(rules, "min")
    if minimum and minimum.isdigit() and int(minimum) > 1:
        return f"matnni (kamida {minimum} ta belgi)"
    return "kerakli ma'lumotni"


def step_sentence(step: Step, marker: int | None, page_label: str | None) -> str | None:
    """One instruction sentence for a step, or None for checks the reader does not do."""
    mark = f" {marker_symbol(marker)}" if marker else ""
    target = step.target
    name = (target.name or target.label or "") if target else ""
    if step.action == "goto":
        if page_label:
            return f"«{page_label}» sahifasini oching."
        path = step.path or "/"
        if "{own:" in path:
            return "Kerakli yozuvni ro'yxatdan tanlab, uning sahifasini oching."
        return (
            f"Saytda {path} sahifasini oching."
            if path != "/"
            else "Saytning bosh sahifasini oching."
        )
    if step.action == "click":
        role = target.role if target else None
        if role == "link":
            return f"«{name}» havolasini bosing{mark}."
        if role == "tab":
            return f"«{name}» yorlig'ini tanlang{mark}."
        if step.confirm:
            return f"Tasdiqlash oynasida «{name}» tugmasini bosing{mark}."
        if name:
            return f"«{name}» tugmasini bosing{mark}."
        return f"Formani yuboring{mark}."
    if step.action == "fill":
        return f"«{name}» maydoniga {fill_hint(step)} kiriting{mark}."
    if step.action == "select":
        return f"«{name}» ro'yxatidan kerakli variantni tanlang{mark}."
    if step.action == "check":
        return f"«{name}» belgisini qo'ying{mark}."
    if step.action == "upload":
        return f"«{name}» orqali faylni yuklang{mark}."
    if step.action == "verify_email":
        if name:
            return f"Emailingizga kelgan 6 xonali kodni «{name}» maydoniga kiriting{mark}."
        return "Emailingizga kelgan xatdagi havolani oching."
    if step.action == "human_input":
        return step.text or "Sayt so'ragan qo'shimcha ma'lumotni kiriting."
    return None  # expect_*, wait_for: checks done by the tool


ROLE_GRANT_SELF = "Bu rolni saytda o'zingiz ro'yxatdan o'tganingizda olasiz."
ROLE_GRANT_ADMIN = "«{label}» rolini sayt administratori beradi."


def role_intro(role_label: str, self_signup: bool) -> str:
    grant = ROLE_GRANT_SELF if self_signup else ROLE_GRANT_ADMIN.format(label=role_label)
    return f"Bu yo'riqnoma «{role_label}» roli uchun yozilgan. {grant}"


EMPTY_SECTION = "Bu saytda bu rol uchun bunday imkoniyat topilmadi."
UNVERIFIED_INTRO = (
    "Quyidagi vazifalarni vosita tekshira olmadi. Ular saytda bo'lishi mumkin, lekin "
    "yo'riqnomaga qadamlari bilan kiritilmadi."
)
PATCHED_NOTE = "Namuna ko'rinish: bu holat sinov uchun ko'rsatilgan."
STOPPED_NOTE = "Vosita bu amalni haqiqiy saytda oxirigacha bajarmadi: tasdiqlash oynasida to'xtadi."
