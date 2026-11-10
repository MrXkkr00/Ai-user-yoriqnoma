"""Forms seen on a page: fields, rules, submit button, what the form is for.

``FORMS_JS`` reads every visible form from the DOM (names, types, labels and the browser's
own constraints: required, minlength, maxlength, pattern, min, max). Values typed by other
people are never read. ``classify`` tells login, sign-up and search forms from the rest.
"""

from __future__ import annotations

import re
from typing import Any

from yoriqnoma_core.text_uz import normalize_uz
from yoriqnoma_schemas import Form, FormField, Step, Target

FORMS_JS = r"""
() => {
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
  };
  const labelOf = (el) => {
    if (el.id) {
      const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (l) return l.innerText.trim();
    }
    const wrap = el.closest('label');
    if (wrap) return wrap.innerText.trim();
    return el.getAttribute('aria-label') || el.getAttribute('placeholder') || '';
  };
  const out = [];
  const roots = Array.from(document.querySelectorAll('form'));
  roots.forEach((form, index) => {
    if (!visible(form)) return;
    const fields = [];
    form.querySelectorAll('input, select, textarea').forEach((el) => {
      const type = (el.tagName === 'SELECT') ? 'select'
        : (el.tagName === 'TEXTAREA') ? 'textarea' : (el.type || 'text').toLowerCase();
      if (['hidden', 'submit', 'button', 'reset', 'image'].includes(type)) return;
      if (!visible(el) && type !== 'radio' && type !== 'checkbox') return;
      fields.push({
        name: el.name || el.id || '',
        type,
        label: labelOf(el).slice(0, 120),
        required: !!el.required,
        minlength: el.minLength > 0 ? el.minLength : null,
        maxlength: el.maxLength > 0 && el.maxLength < 100000 ? el.maxLength : null,
        pattern: el.getAttribute('pattern'),
        min: el.getAttribute('min'),
        max: el.getAttribute('max'),
        options: el.tagName === 'SELECT'
          ? Array.from(el.options).map(o => o.text.trim()).filter(Boolean).slice(0, 20)
          : (type === 'radio' ? [el.value] : null),
        message: el.validationMessage || '',
      });
    });
    const submit = form.querySelector(
      'button[type=submit], input[type=submit], button:not([type])');
    out.push({
      index,
      id: form.id || '',
      action: form.getAttribute('action') || '',
      method: (form.getAttribute('method') || 'get').toLowerCase(),
      submit: submit ? (submit.innerText || submit.value || '').trim().slice(0, 80) : '',
      fields,
    });
  });
  return out;
}
"""

LOGIN_WORDS = ("kirish", "login", "log in", "sign in", "signin", "войти", "вход", "kiriş")
REGISTER_WORDS = (
    "ro'yxatdan",
    "royxatdan",
    "register",
    "sign up",
    "signup",
    "create account",
    "регистрац",
    "зарегистр",
    "hisob yaratish",
)
SEARCH_WORDS = ("qidir", "search", "поиск", "izla")
ROLE_FIELD = re.compile(r"(^|_)(role|type|account_?type|user_?type|kind)$", re.I)


def _has(text: str, words: tuple[str, ...]) -> bool:
    norm = normalize_uz(text)
    return any(normalize_uz(w) in norm for w in words)


def classify(raw: dict[str, Any], page_path: str = "") -> str:
    """ "login", "register", "search" or "other"."""
    fields = raw.get("fields", [])
    types = [f.get("type") for f in fields]
    passwords = types.count("password")
    text = " ".join([raw.get("submit", ""), raw.get("action", ""), page_path])
    if passwords >= 2 or (passwords == 1 and _has(text, REGISTER_WORDS)):
        return "register"
    if passwords == 1:
        return "login"
    if len(fields) <= 2 and (_has(text, SEARCH_WORDS) or "search" in types):
        return "search"
    return "other"


def rules_of(field: dict[str, Any]) -> str | None:
    """Rules in the blueprint's own notation: lengths for text, bounds for numbers."""
    rules = []
    if field.get("type") == "number":
        if field.get("min") not in (None, ""):
            rules.append(f"min:{field['min']}")
        if field.get("max") not in (None, ""):
            rules.append(f"max:{field['max']}")
    else:
        if field.get("minlength"):
            rules.append(f"min:{field['minlength']}")
        if field.get("maxlength"):
            rules.append(f"max:{field['maxlength']}")
    if field.get("pattern"):
        rules.append(f"regex:{field['pattern']}")
    return "|".join(rules) or None


def merge_fields(fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Radio buttons of one group become one field with options."""
    out: list[dict[str, Any]] = []
    by_name: dict[str, dict[str, Any]] = {}
    for f in fields:
        if f["type"] == "radio" and f["name"] in by_name:
            by_name[f["name"]]["options"] = (by_name[f["name"]].get("options") or []) + (
                f.get("options") or []
            )
            continue
        item = dict(f)
        out.append(item)
        if item["name"]:
            by_name[item["name"]] = item
    return out


def to_form(raw: dict[str, Any], page_path: str, form_id: str) -> Form:
    fields = [
        FormField(
            name=f["name"] or f"field{i}",
            label=f.get("label") or None,
            type=f["type"],
            required=bool(f.get("required")),
            rules=rules_of(f),
            options=f.get("options") or None,
        )
        for i, f in enumerate(merge_fields(raw.get("fields", [])))
    ]
    submit = raw.get("submit") or ""
    target = Target(role="button", name=submit) if submit else Target(css="form button")
    api = None
    if raw.get("method") == "post" and raw.get("action"):
        api = f"POST {raw['action']}"
    return Form(id=form_id, page_path=page_path, fields=fields, submit=target, api=api)


def data_kind(field: FormField) -> str:
    """The fake data a field gets ("fake:email" ...)."""
    name = normalize_uz(f"{field.name} {field.label or ''}")
    if field.type == "email" or "email" in name or "pochta" in name:
        return "fake:email"
    if field.type == "password" or "parol" in name or "password" in name:
        return "fake:password"
    if field.type == "tel" or "phone" in name or "telefon" in name:
        return "fake:phone_uz"
    if field.type in {"select", "radio"}:
        return "fake:option"
    if field.type == "number":
        return "fake:number"
    if field.type == "date":
        return "fake:date"
    if "username" in name or "login" in name or "foydalanuvchi nomi" in name:
        return "fake:username"
    if any(w in name for w in ("first", "ism")) and "familiya" not in name:
        return (
            "fake:first_name" if "full" not in name and "to'liq" not in name else "fake:full_name"
        )
    if any(w in name for w in ("last", "familiya", "surname")):
        return "fake:last_name"
    if any(w in name for w in ("name", "f.i.sh", "fio", "имя")):
        return "fake:full_name"
    if any(w in name for w in ("address", "manzil", "адрес")):
        return "fake:address"
    return "fake:text"


def fill_steps(form: Form, *, login: bool = False) -> list[Step]:
    steps: list[Step] = []
    for field in form.fields:
        if field.type in {"checkbox"}:
            if field.required:
                steps.append(Step(action="check", target=_target(field)))
            continue
        if field.type == "file":
            continue
        kind = data_kind(field)
        if login and kind not in {"fake:email", "fake:password"}:
            kind = "fake:username" if field.type != "password" else "fake:password"
        if field.type in {"select", "radio"}:
            steps.append(Step(action="select", target=_target(field), data=kind))
        else:
            steps.append(Step(action="fill", target=_target(field), data=kind, rules=field.rules))
    return steps


def _target(field: FormField) -> Target:
    if field.label:
        return Target(label=field.label)
    return Target(css=f'[name="{field.name}"]')


def signup_roles(raw: dict[str, Any]) -> list[str]:
    """Role choices offered on a sign-up form ("Men sotuvchiman / xaridorman")."""
    out: list[str] = []
    for f in raw.get("fields", []):
        if f["type"] in {"select", "radio"} and ROLE_FIELD.search(f.get("name") or ""):
            out.extend(o for o in (f.get("options") or []) if o)
    return out
