"""Forms, buttons and links in server-side templates (Django, Jinja, Blade) and Vue templates.

Template syntax is reduced first: translation tags become their text (resolved through
the project's locale), ``{% url 'name' %}`` / ``route('name')`` become markers the stack
parser resolves to a path, a rendered form (``{{ form.as_p }}``) becomes a marker the stack
parser fills from the form class, and every other tag is dropped. The rest is HTML.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from html.parser import HTMLParser

URL_MARK = "__url__:"
FORM_MARK = "yq-form-object"  # a tag name must start with a letter for html.parser

_TRANS = [
    re.compile(r"\{%\s*(?:trans|translate)\s+[\"']([^\"']+)[\"'][^%]*%\}"),
    re.compile(r"\{\{\s*_\(\s*[\"']([^\"']+)[\"']\s*\)\s*\}\}"),
    re.compile(r"\{\{\s*gettext\(\s*[\"']([^\"']+)[\"']\s*\)\s*\}\}"),
    re.compile(r"\{\{\s*__\(\s*[\"']([^\"']+)[\"']\s*\)\s*\}\}"),
    re.compile(r"@lang\(\s*[\"']([^\"']+)[\"']\s*\)"),
    re.compile(r"\{\{\s*\$?t\(\s*[\"']([^\"']+)[\"']\s*\)\s*\}\}"),
]
_URL = [
    re.compile(r"\{%\s*url\s+[\"']([^\"']+)[\"'][^%]*%\}"),  # Django
    re.compile(r"\{\{\s*url_for\(\s*[\"']([^\"']+)[\"'][^}]*\)\s*\}\}"),  # Flask / Jinja
    re.compile(r"\{\{\s*route\(\s*[\"']([^\"']+)[\"'][^}]*\)\s*\}\}"),  # Laravel Blade
]
_FORM_RENDER = re.compile(
    r"\{\{\s*form(?:\.\w+)?\s*\}\}"
    r"|\{%\s*(?:bootstrap_form|crispy)\s+form[^%]*%\}"
    r"|\{\{\s*form\s*\|\s*crispy\s*\}\}"
)
# WTForms: {{ form.email(class_="x") }} or {{ render_field(form.email) }} -> a field placeholder
_WTF_FIELD = re.compile(r"\{\{\s*(?:\w+\(\s*)?form\.(\w+)\s*(?:\(|,|\))[^}]*\}\}")
FIELD_MARK = "yq-field"
_OTHER = re.compile(r"\{%.*?%\}|\{\{.*?\}\}|\{#.*?#\}|<%.*?%>|@\w+(\([^)]*\))?", re.S)
_RULE_ATTRS = (
    ("minlength", "min"),
    ("maxlength", "max"),
    ("min", "min"),
    ("max", "max"),
    ("pattern", "regex"),
)
_SKIP_NAMES = {"csrfmiddlewaretoken", "_token", "csrf_token", "_method"}
_CONTAINERS = {"div", "dialog", "section", "aside"}


def reduce_template(text: str, translate: Callable[[str], str]) -> str:
    for rx in _TRANS:
        text = rx.sub(lambda m: translate(m.group(1)), text)
    for rx in _URL:
        text = rx.sub(lambda m: URL_MARK + m.group(1), text)
    text = _FORM_RENDER.sub(f"<{FORM_MARK}></{FORM_MARK}>", text)
    text = _WTF_FIELD.sub(lambda m: f'<{FIELD_MARK} name="{m.group(1)}"></{FIELD_MARK}>', text)
    return _OTHER.sub("", text)


@dataclass
class TField:
    name: str
    type: str
    el_id: str
    required: bool = False
    rules: list[str] = field(default_factory=list)
    options: list[str] = field(default_factory=list)
    label: str = ""


@dataclass
class TForm:
    method: str
    action: str
    fields: list[TField] = field(default_factory=list)
    submit: str = ""
    renders_form_object: bool = False
    line: int = 0
    modal: str | None = None  # id of the modal or dialog that holds the form
    method_override: str | None = None  # Laravel/Rails hidden ``_method`` field


@dataclass
class TemplateInfo:
    forms: list[TForm] = field(default_factory=list)
    links: list[tuple[str, str]] = field(default_factory=list)  # (href, text)
    buttons: list[str] = field(default_factory=list)  # buttons outside forms
    openers: dict[str, str] = field(default_factory=dict)  # modal id -> opener button text


def _is_modal(tag: str, attrs: dict[str, str]) -> bool:
    if tag == "dialog":
        return True
    classes = attrs.get("class", "").split()
    return "modal" in classes or attrs.get("role") == "dialog"


class _Parser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.info = TemplateInfo()
        self.labels: dict[str, str] = {}
        self.form: TForm | None = None
        self.text_stack: list[tuple[str, list[str], dict[str, str]]] = []
        self.select: TField | None = None
        self.label_wraps: list[TField] = []
        self.containers: list[tuple[str, str | None]] = []  # (tag, modal id)

    def _modal(self) -> str | None:
        return next((m for _, m in reversed(self.containers) if m), None)

    def handle_starttag(self, tag: str, attrs_list: list[tuple[str, str | None]]) -> None:
        attrs = {k: (v if v is not None else "") for k, v in attrs_list}
        if tag in _CONTAINERS:
            modal_id = attrs.get("id") if _is_modal(tag, attrs) else None
            self.containers.append((tag, modal_id or None))
        if tag == FORM_MARK and self.form is not None:
            self.form.renders_form_object = True
        if tag == FIELD_MARK and self.form is not None:
            name = attrs.get("name", "")
            if name and name not in {"hidden_tag", "csrf_token"}:
                # type "" marks a placeholder: the form class gives its type and label
                self.form.fields.append(TField(name=name, type="", el_id=f"id_{name}"))
            self.form.renders_form_object = True
        if tag == "form":
            method = (attrs.get("method") or "get").upper()
            self.form = TForm(
                method=method,
                action=attrs.get("action", ""),
                line=self.getpos()[0],
                modal=self._modal(),
            )
        elif tag in {"input", "select", "textarea"} and self.form is not None:
            self._field(tag, attrs)
        elif tag == "option" and self.select is not None and attrs.get("value"):
            self.select.options.append(attrs["value"])
        if tag in {"label", "button", "a"}:
            self.text_stack.append((tag, [], attrs))

    def _field(self, tag: str, attrs: dict[str, str]) -> None:
        assert self.form is not None
        if tag == "select":
            ftype = "select"
        elif tag == "textarea":
            ftype = "textarea"
        else:
            ftype = attrs.get("type", "text").lower()
        if ftype in {"hidden", "submit", "button", "reset", "image"}:
            if ftype == "hidden" and attrs.get("name") == "_method":
                self.form.method_override = attrs.get("value", "").upper() or None
            if ftype in {"submit", "image"} and not self.form.submit:
                self.form.submit = attrs.get("value", "") or attrs.get("alt", "")
            return
        name = attrs.get("name") or attrs.get("v-model", "") or attrs.get("id", "")
        name = name.removeprefix("form.")
        if not name or name in _SKIP_NAMES:
            return
        rules = [f"{rule}:{attrs[key]}" for key, rule in _RULE_ATTRS if attrs.get(key)]
        tfield = TField(
            name=name,
            type=ftype,
            el_id=attrs.get("id", ""),
            required="required" in attrs,
            rules=rules,
        )
        self.form.fields.append(tfield)
        if self.text_stack and self.text_stack[-1][0] == "label":
            self.label_wraps.append(tfield)
        if tag == "select":
            self.select = tfield

    def handle_endtag(self, tag: str) -> None:
        if tag in _CONTAINERS:
            for i in range(len(self.containers) - 1, -1, -1):
                if self.containers[i][0] == tag:
                    del self.containers[i:]
                    break
        if tag == "select":
            self.select = None
        if tag == "form" and self.form is not None:
            self.info.forms.append(self.form)
            self.form = None
            return
        if not (self.text_stack and self.text_stack[-1][0] == tag):
            return
        name, parts, attrs = self.text_stack.pop()
        text = re.sub(r"\s+", " ", " ".join(parts)).strip()
        if name == "label":
            target = attrs.get("for", "")
            if target:
                self.labels[target] = text
            for wrapped in self.label_wraps:
                wrapped.label = wrapped.label or text
            self.label_wraps = []
        elif name in {"button", "a"} and self._opens_modal(attrs, text):
            pass
        elif name == "button":
            btype = attrs.get("type", "submit").lower()
            if self.form is not None and btype == "submit" and not self.form.submit:
                self.form.submit = text
            elif self.form is None and text:
                self.info.buttons.append(text)
        elif name == "a":
            href = attrs.get("href", "")
            if href and text:
                self.info.links.append((href, text))
        if self.text_stack:
            self.text_stack[-1][1].append(text)

    def _opens_modal(self, attrs: dict[str, str], text: str) -> bool:
        toggle = attrs.get("data-bs-toggle") or attrs.get("data-toggle") or ""
        target = attrs.get("data-bs-target") or attrs.get("data-target") or ""
        if toggle != "modal" and not target.startswith("#"):
            return False
        target = target or attrs.get("href", "")
        if target.startswith("#") and text:
            self.info.openers.setdefault(target[1:], text)
            return True
        return False

    def handle_data(self, data: str) -> None:
        if self.text_stack:
            self.text_stack[-1][1].append(data)


def parse_template(text: str, translate: Callable[[str], str] | None = None) -> TemplateInfo:
    reduced = reduce_template(text, translate or (lambda s: s))
    parser = _Parser()
    try:
        parser.feed(reduced)
        parser.close()
    except Exception:  # noqa: BLE001 - broken markup: keep what was read
        pass
    for form in parser.info.forms:
        for f in form.fields:
            if not f.label:
                f.label = parser.labels.get(f.el_id) or parser.labels.get(f"id_{f.name}", "")
    return parser.info
