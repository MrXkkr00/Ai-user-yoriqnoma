"""Django models, forms and REST serializers read as CODE only (AST): never imported.

Models give entities (owner field, status choices, fields that may hold other people's
data, TZ FR-E10), the user model and its role choices. Forms and serializers give form
fields with labels (translated through the project's gettext catalogue) and rules.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from yoriqnoma_scanner.parsers.base import EntityCandidate
from yoriqnoma_scanner.parsers.sqlalchemy_models import is_pii_name
from yoriqnoma_scanner.pyindex import PyIndex, PyModule, call_name, dotted_name, kwarg
from yoriqnoma_schemas import FormField

Translate = Callable[[str], str]

USER_BASES = {"AbstractUser", "AbstractBaseUser"}
MODEL_BASES = {"Model", *USER_BASES}
GETTEXT = {
    "_",
    "gettext",
    "gettext_lazy",
    "ugettext",
    "ugettext_lazy",
    "pgettext",
    "pgettext_lazy",
    "gettext_noop",
    "lazy_gettext",  # Flask-Babel
    "_l",
    "lazy_pgettext",
}
ABSTRACT_USER_FIELDS: dict[str, tuple[str, int]] = {
    "username": ("text", 150),
    "first_name": ("text", 150),
    "last_name": ("text", 150),
    "email": ("email", 254),
}
OWNER_PREFERRED = ("owner", "user", "author", "created_by", "creator", "customer", "client")
STATUS_NAMES = ("status", "state")
ROLE_FIELDS = ("role", "roles", "user_type", "account_type", "kind", "type")
RELATIONS = {"ForeignKey", "OneToOneField", "ManyToManyField"}
NOT_EDITABLE = {"AutoField", "BigAutoField", "SmallAutoField"}

FIELD_TYPES = {
    "CharField": "text",
    "SlugField": "text",
    "TextField": "textarea",
    "EmailField": "email",
    "URLField": "url",
    "IntegerField": "number",
    "PositiveIntegerField": "number",
    "PositiveSmallIntegerField": "number",
    "PositiveBigIntegerField": "number",
    "SmallIntegerField": "number",
    "BigIntegerField": "number",
    "DecimalField": "number",
    "FloatField": "number",
    "BooleanField": "checkbox",
    "NullBooleanField": "select",
    "DateField": "date",
    "DateTimeField": "date",
    "TimeField": "text",
    "DurationField": "text",
    "UUIDField": "text",
    "GenericIPAddressField": "text",
    "JSONField": "textarea",
    "ForeignKey": "select",
    "OneToOneField": "select",
    "ManyToManyField": "select",
    "FileField": "file",
    "ImageField": "file",
    "ChoiceField": "select",
    "TypedChoiceField": "select",
    "MultipleChoiceField": "select",
    "TypedMultipleChoiceField": "select",
    "ModelChoiceField": "select",
    "ModelMultipleChoiceField": "select",
    "PrimaryKeyRelatedField": "select",
    "SlugRelatedField": "select",
    "RegexField": "text",
    "PhoneNumberField": "tel",
}
WIDGET_TYPES = {
    "PasswordInput": "password",
    "Textarea": "textarea",
    "EmailInput": "email",
    "NumberInput": "number",
    "DateInput": "date",
    "DateTimeInput": "date",
    "CheckboxInput": "checkbox",
    "Select": "select",
    "RadioSelect": "select",
    "SelectMultiple": "select",
    "CheckboxSelectMultiple": "select",
    "FileInput": "file",
    "ClearableFileInput": "file",
    "TextInput": "text",
    "URLInput": "url",
    "HiddenInput": "hidden",
    "MultipleHiddenInput": "hidden",
}
# Fields Django's own forms add; labels are Django's translations, unknown here (css by name).
BUILTIN_FORMS: dict[str, list[tuple[str, str]]] = {
    "UserCreationForm": [("password1", "password"), ("password2", "password")],
    "BaseUserCreationForm": [("password1", "password"), ("password2", "password")],
    "AuthenticationForm": [("username", "text"), ("password", "password")],
    "PasswordChangeForm": [
        ("old_password", "password"),
        ("new_password1", "password"),
        ("new_password2", "password"),
    ],
    "SetPasswordForm": [("new_password1", "password"), ("new_password2", "password")],
    "AdminPasswordChangeForm": [("password1", "password"), ("password2", "password")],
    "PasswordResetForm": [("email", "email")],
}
USER_CREATION_FORMS = {"UserCreationForm", "BaseUserCreationForm"}
MODEL_FORM_BASES = {"ModelForm", "UserCreationForm", "BaseUserCreationForm", "UserChangeForm"}
SERIALIZER_MODEL_BASES = {"ModelSerializer", "HyperlinkedModelSerializer"}


def snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def plural(name: str) -> str:
    if name.endswith("y") and not name.endswith(("ay", "ey", "oy", "uy")):
        return name[:-1] + "ies"
    if name.endswith(("s", "x", "ch", "sh")):
        return name + "es"
    return name + "s"


def capfirst(text: str) -> str:
    return text[:1].upper() + text[1:]


def text_of(
    index: PyIndex, module: PyModule, node: ast.expr | None, translate: Translate, depth: int = 0
) -> str | None:
    """A literal string, a translated ``_("...")`` call, or a constant holding one."""
    if node is None or depth > 3:
        return None
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Call) and dotted_name(node.func).split(".")[-1] in GETTEXT:
        if node.args:
            inner = text_of(index, module, node.args[-1], translate, depth + 1)
            return translate(inner) if inner is not None else None
        return None
    if isinstance(node, ast.Name):
        found = index.resolve_assign(module, node.id)
        if found:
            return text_of(index, found[0], found[1], translate, depth + 1)
    return None


def nested_class(cls: ast.ClassDef, name: str) -> ast.ClassDef | None:
    return next((n for n in cls.body if isinstance(n, ast.ClassDef) and n.name == name), None)


def class_attr(cls: ast.ClassDef, name: str) -> ast.expr | None:
    for node in cls.body:
        if isinstance(node, ast.Assign):
            if any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
                return node.value
        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == name
        ):
            return node.value
    return None


def class_chain(
    index: PyIndex, module: PyModule, cls: ast.ClassDef, depth: int = 0
) -> list[tuple[PyModule, ast.ClassDef]]:
    """The class and its project-local bases, most specific first (a simple MRO)."""
    chain: list[tuple[PyModule, ast.ClassDef]] = [(module, cls)]
    if depth > 6:
        return chain
    for base in cls.bases:
        name = dotted_name(base)
        if not name:
            continue
        found = resolve_dotted_class(index, module, name)
        if found and found[1] is not cls:
            for item in class_chain(index, found[0], found[1], depth + 1):
                if all(item[1] is not c for _, c in chain):
                    chain.append(item)
    return chain


def chain_attr(
    chain: list[tuple[PyModule, ast.ClassDef]], name: str
) -> tuple[PyModule, ast.expr] | None:
    for module, cls in chain:
        value = class_attr(cls, name)
        if value is not None:
            return module, value
    return None


def resolve_dotted_class(
    index: PyIndex, module: PyModule, dotted: str
) -> tuple[PyModule, ast.ClassDef] | None:
    """``Ticket``, ``views.TicketView``, ``Ticket.Status`` -> the class definition."""
    parts = dotted.split(".")
    found = index.resolve(module, parts[0])
    current: tuple[PyModule, ast.ClassDef] | None = None
    if isinstance(found, tuple) and found[1] in found[0].classes:
        current = (found[0], found[0].classes[found[1]])
    elif isinstance(found, PyModule) and len(parts) > 1:
        sub = index.resolve_class(found, parts[1])
        if sub is None:
            return None
        current, parts = sub, parts[1:]
    if current is None:
        return None
    for name in parts[1:]:
        inner = nested_class(current[1], name)
        if inner is None:
            return None
        current = (current[0], inner)
    return current


def choice_members(
    index: PyIndex, module: PyModule, cls: ast.ClassDef, translate: Translate
) -> list[tuple[str, str]]:
    """``CUSTOMER = "customer", _("Mijoz")`` -> ("customer", "Mijoz")."""
    out: list[tuple[str, str]] = []
    for node in cls.body:
        if not (isinstance(node, ast.Assign) and len(node.targets) == 1):
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name) or target.id.startswith("_"):
            continue
        value = node.value
        label: str | None = None
        if isinstance(value, ast.Tuple) and value.elts:
            label = (
                text_of(index, module, value.elts[-1], translate) if len(value.elts) > 1 else None
            )
            value = value.elts[0]
        if isinstance(value, ast.Constant) and isinstance(value.value, str | int):
            out.append((str(value.value), label or target.id.replace("_", " ").title()))
    return out


def choices_of(
    index: PyIndex, module: PyModule, node: ast.expr | None, translate: Translate, depth: int = 0
) -> list[tuple[str, str]]:
    """``Role.choices``, ``ROLE_CHOICES`` or a literal list of pairs -> (value, label)."""
    if node is None or depth > 3:
        return []
    if isinstance(node, ast.Attribute) and node.attr == "choices":
        found = resolve_dotted_class(index, module, dotted_name(node.value))
        return choice_members(index, found[0], found[1], translate) if found else []
    if isinstance(node, ast.Name | ast.Attribute):
        dotted = dotted_name(node)
        found_cls = resolve_dotted_class(index, module, dotted)
        if found_cls:
            return choice_members(index, found_cls[0], found_cls[1], translate)
        if isinstance(node, ast.Name):
            assigned = index.resolve_assign(module, node.id)
            if assigned:
                return choices_of(index, assigned[0], assigned[1], translate, depth + 1)
        return []
    if isinstance(node, ast.List | ast.Tuple):
        out: list[tuple[str, str]] = []
        for item in node.elts:
            if isinstance(item, ast.Tuple | ast.List) and len(item.elts) >= 2:
                key = item.elts[0]
                if isinstance(key, ast.Constant) and isinstance(key.value, str | int):
                    label = text_of(index, module, item.elts[1], translate)
                    out.append((str(key.value), label or str(key.value)))
        return out
    return []


def enum_value(index: PyIndex, module: PyModule, node: ast.expr | None) -> str | None:
    """``Ticket.Status.OPEN`` / ``Status.OPEN`` / ``"open"`` -> "open"."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Attribute):
        found = resolve_dotted_class(index, module, dotted_name(node.value))
        if found:
            for item in found[1].body:
                if (
                    isinstance(item, ast.Assign)
                    and isinstance(item.targets[0], ast.Name)
                    and item.targets[0].id == node.attr
                ):
                    value_node = item.value
                    if isinstance(value_node, ast.Tuple) and value_node.elts:
                        value_node = value_node.elts[0]
                    if isinstance(value_node, ast.Constant):
                        return str(value_node.value)
            return node.attr.lower()
    return None


def rules_from(index: PyIndex, module: PyModule, call: ast.Call, kind: str) -> list[str]:
    rules: list[str] = []
    for key, rule in (
        ("min_length", "min"),
        ("max_length", "max"),
        ("min_value", "min"),
        ("max_value", "max"),
    ):
        value = kwarg(call, key)
        if isinstance(value, ast.Constant) and isinstance(value.value, int | float):
            rules.append(f"{rule}:{value.value}")
    if kind == "RegexField" and call.args:
        regex = index.string_constant(module, call.args[0])
        if regex:
            rules.append(f"regex:{regex}")
    validators = kwarg(call, "validators")
    if isinstance(validators, ast.List | ast.Tuple):
        for item in validators.elts:
            rules += _validator_rules(index, module, item)
    return rules


def _validator_rules(index: PyIndex, module: PyModule, node: ast.expr, depth: int = 0) -> list[str]:
    if depth > 3:
        return []
    if isinstance(node, ast.Name):
        found = index.resolve_assign(module, node.id)
        return _validator_rules(index, found[0], found[1], depth + 1) if found else []
    if not isinstance(node, ast.Call):
        return []
    name = call_name(node).split(".")[-1]
    first = node.args[0] if node.args else None
    if name == "RegexValidator":
        regex = index.string_constant(module, first or kwarg(node, "regex"))
        return [f"regex:{regex}"] if regex else []
    rule = {
        "MinLengthValidator": "min",
        "MaxLengthValidator": "max",
        "MinValueValidator": "min",
        "MaxValueValidator": "max",
    }.get(name)
    if rule and isinstance(first, ast.Constant) and isinstance(first.value, int | float):
        return [f"{rule}:{first.value}"]
    return []


def _merge_rules(rules: list[str]) -> str | None:
    merged: dict[str, str] = {}
    for rule in rules:
        key, _, value = rule.partition(":")
        merged[key] = value
    return "|".join(f"{k}:{v}" for k, v in merged.items()) or None


@dataclass
class ModelField:
    name: str
    kind: str
    type: str
    label: str | None
    required: bool
    rules: list[str] = field(default_factory=list)
    choices: list[tuple[str, str]] = field(default_factory=list)
    related: str | None = None  # target class name, "user" for the auth user model
    default: ast.expr | None = None
    editable: bool = True

    def form_field(self, label: str | None = None, widget: str | None = None) -> FormField:
        ftype = widget or self.type
        return FormField(
            name=self.name,
            label=label or self.label,
            type=ftype,
            required=self.required and ftype != "checkbox",
            rules=_merge_rules(self.rules),
            options=[v for v, _ in self.choices] or None,
        )


@dataclass
class DjangoModel:
    name: str
    module: PyModule
    cls: ast.ClassDef
    app_label: str
    fields: dict[str, ModelField] = field(default_factory=dict)
    is_user: bool = False
    abstract: bool = False

    @property
    def entity(self) -> str:
        return snake(self.name)


class DjangoModels:
    """Every model of the project, the user model, and readers for forms and serializers."""

    def __init__(self, index: PyIndex, translate: Translate, auth_user_model: str | None) -> None:
        self.index = index
        self.translate = translate
        self.models: dict[str, DjangoModel] = {}
        self.user_model: DjangoModel | None = None
        for module in index.modules.values():
            for cname, cls in module.classes.items():
                if cls not in module.tree.body and nested_class_owner(module, cls):
                    continue  # nested Status/Role/Meta classes are not models
                bases = index.class_bases(module, cls)
                if not bases & MODEL_BASES:
                    continue
                self.models[cname] = self._model(module, cname, cls, bases)
        wanted = (auth_user_model or "").split(".")[-1]
        users = [m for m in self.models.values() if m.is_user and not m.abstract]
        self.user_model = (
            self.models.get(wanted) if wanted in self.models else (users[0] if users else None)
        )
        if self.user_model is not None:
            self.user_model.is_user = True

    # --- models -----------------------------------------------------------------

    def _model(
        self, module: PyModule, cname: str, cls: ast.ClassDef, bases: set[str]
    ) -> DjangoModel:
        rel = PurePosixPath(module.rel)
        app = rel.parts[-2] if len(rel.parts) > 1 else rel.stem
        meta = nested_class(cls, "Meta")
        abstract = False
        if meta is not None:
            value = class_attr(meta, "abstract")
            abstract = isinstance(value, ast.Constant) and value.value is True
        model = DjangoModel(
            name=cname,
            module=module,
            cls=cls,
            app_label=app,
            is_user=bool(bases & USER_BASES),
            abstract=abstract,
        )
        if "AbstractUser" in bases:
            for fname, (ftype, max_len) in ABSTRACT_USER_FIELDS.items():
                model.fields[fname] = ModelField(
                    fname, "CharField", ftype, None, fname == "username", [f"max:{max_len}"]
                )
        for base_module, base_cls in reversed(class_chain(self.index, module, cls)[1:]):
            for fname, mf in self._own_fields(base_module, base_cls).items():
                model.fields[fname] = mf
        model.fields.update(self._own_fields(module, cls))
        return model

    def _own_fields(self, module: PyModule, cls: ast.ClassDef) -> dict[str, ModelField]:
        out: dict[str, ModelField] = {}
        for node in cls.body:
            target: ast.expr | None = None
            value: ast.expr | None = None
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                target, value = node.targets[0], node.value
            elif isinstance(node, ast.AnnAssign):
                target, value = node.target, node.value
            if not (isinstance(target, ast.Name) and isinstance(value, ast.Call)):
                continue
            kind = call_name(value).split(".")[-1]
            if not (kind.endswith("Field") or kind in RELATIONS):
                continue
            out[target.id] = self._field(module, target.id, kind, value)
        return out

    def _field(self, module: PyModule, name: str, kind: str, call: ast.Call) -> ModelField:
        related: str | None = None
        label_node = kwarg(call, "verbose_name")
        if kind in RELATIONS:
            related = self._related(module, call.args[0] if call.args else kwarg(call, "to"))
        elif label_node is None and call.args:
            label_node = call.args[0]
        label = text_of(self.index, module, label_node, self.translate)
        blank = kwarg(call, "blank")
        editable = kwarg(call, "editable")
        auto = any(
            isinstance(kwarg(call, k), ast.Constant) and kwarg(call, k).value is True  # type: ignore[union-attr]
            for k in ("auto_now", "auto_now_add", "primary_key")
        )
        choices = choices_of(self.index, module, kwarg(call, "choices"), self.translate)
        ftype = "select" if choices else FIELD_TYPES.get(kind, "text")
        rules = rules_from(self.index, module, call, kind)
        return ModelField(
            name=name,
            kind=kind,
            type=ftype,
            label=capfirst(label) if label else None,
            required=not (isinstance(blank, ast.Constant) and blank.value is True)
            and kind != "BooleanField",
            rules=rules,
            choices=choices,
            related=related,
            default=kwarg(call, "default"),
            editable=not auto
            and kind not in NOT_EDITABLE
            and not (isinstance(editable, ast.Constant) and editable.value is False),
        )

    def _related(self, module: PyModule, node: ast.expr | None) -> str | None:
        if node is None:
            return None
        text = dotted_name(node) or (
            node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else ""
        )
        if isinstance(node, ast.Call) and call_name(node).endswith("get_user_model"):
            return "user"
        if not text:
            return None
        if text.endswith("AUTH_USER_MODEL") or text in {"auth.User", "User"}:
            return "user"
        return text.split(".")[-1]

    def is_user_relation(self, mf: ModelField) -> bool:
        return mf.related == "user" or (
            self.user_model is not None and mf.related == self.user_model.name
        )

    def entities(self) -> list[EntityCandidate]:
        out: list[EntityCandidate] = []
        for model in self.models.values():
            if model.abstract:
                continue
            table = plural(model.entity)
            meta = nested_class(model.cls, "Meta")
            if meta is not None:
                db_table = class_attr(meta, "db_table")
                if isinstance(db_table, ast.Constant) and isinstance(db_table.value, str):
                    table = db_table.value
            cand = EntityCandidate(
                name=model.entity,
                table=table,
                source=model.module.src(model.cls),
                fields=list(model.fields),
            )
            owners = [n for n, f in model.fields.items() if self.is_user_relation(f)]
            cand.owner_field = next((n for n in OWNER_PREFERRED if n in owners), None) or (
                owners[0] if owners else None
            )
            for fname, mf in model.fields.items():
                if mf.kind in RELATIONS or mf.type == "checkbox":
                    continue
                if is_pii_name(fname, "users" if model.is_user else table):
                    cand.pii_fields.append(fname)
                if fname in STATUS_NAMES and mf.choices and cand.status_field is None:
                    cand.status_field = fname
                    cand.statuses = [v for v, _ in mf.choices]
            out.append(cand)
        return out

    def status_labels(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for model in self.models.values():
            for fname in STATUS_NAMES:
                mf = model.fields.get(fname)
                if mf is not None:
                    for value, label in mf.choices:
                        out.setdefault(f"status.{value}", label)
        return out

    def user_roles(self) -> tuple[list[tuple[str, str]], str | None, str | None]:
        """Role choices of the user model, the role field name and its default value."""
        holders = [self.user_model] if self.user_model is not None else []
        holders += [  # a profile model linked one-to-one to the user
            m
            for m in self.models.values()
            if m is not self.user_model
            and any(
                f.kind == "OneToOneField" and self.is_user_relation(f) for f in m.fields.values()
            )
        ]
        for model in holders:
            for fname in ROLE_FIELDS:
                mf = model.fields.get(fname)
                if mf is not None and mf.choices:
                    default = enum_value(self.index, model.module, mf.default)
                    return mf.choices, fname, default
        return [], None, None

    def role_source(self) -> str:
        choices, fname, _ = self.user_roles()
        for model in self.models.values():
            if fname and fname in model.fields and model.fields[fname].choices == choices:
                return model.module.src(model.cls)
        return "django.contrib.auth"

    def model_of(self, module: PyModule, node: ast.expr | None) -> DjangoModel | None:
        """``model = Ticket`` / ``queryset = Ticket.objects...`` -> the model."""
        if node is None:
            return None
        name = dotted_name(node)
        if not name and isinstance(node, ast.Call):
            for sub in ast.walk(node):
                if isinstance(sub, ast.Attribute) and sub.attr == "objects":
                    name = dotted_name(sub.value)
                    break
        if not name:
            return None
        if name.endswith(".objects"):
            name = name[: -len(".objects")]
        found = resolve_dotted_class(self.index, module, name)
        if found and found[1].name in self.models:
            return self.models[found[1].name]
        last = name.split(".")[-1]
        if last in {"User"} and self.user_model is not None:
            return self.user_model
        return self.models.get(last)

    # --- forms ------------------------------------------------------------------

    def form_fields(self, module: PyModule, cls: ast.ClassDef) -> list[FormField]:
        chain = class_chain(self.index, module, cls)
        bases = self.index.class_bases(module, cls) | {cls.name}
        fields: dict[str, FormField] = {}
        meta = next(
            ((m, inner) for m, c in chain if (inner := nested_class(c, "Meta")) is not None), None
        )
        if bases & MODEL_FORM_BASES:
            self._model_form_fields(meta, bases, fields)
        for base in (*USER_CREATION_FORMS, *BUILTIN_FORMS):
            if base in bases:
                for fname, ftype in BUILTIN_FORMS.get(base, []):
                    fields.setdefault(
                        fname, FormField(name=fname, label=None, type=ftype, required=True)
                    )
        for base_module, base_cls in reversed(chain):
            for fname, ff in self._declared(base_module, base_cls, form=True).items():
                fields[fname] = ff
        return [f for f in fields.values() if f.type != "hidden"]

    def serializer_fields(self, module: PyModule, cls: ast.ClassDef) -> list[FormField]:
        chain = class_chain(self.index, module, cls)
        bases = self.index.class_bases(module, cls)
        fields: dict[str, FormField] = {}
        meta = next(
            ((m, inner) for m, c in chain if (inner := nested_class(c, "Meta")) is not None), None
        )
        if bases & SERIALIZER_MODEL_BASES and meta is not None:
            read_only = _const_list(class_attr(meta[1], "read_only_fields"))
            self._model_form_fields(meta, bases, fields, skip=set(read_only) | {"id", "pk"})
        for base_module, base_cls in reversed(chain):
            for fname, ff in self._declared(base_module, base_cls, form=False).items():
                fields[fname] = ff
        return [f for f in fields.values() if f.type != "hidden"]

    def _model_form_fields(
        self,
        meta: tuple[PyModule, ast.ClassDef] | None,
        bases: set[str],
        fields: dict[str, FormField],
        skip: set[str] | None = None,
    ) -> None:
        model: DjangoModel | None = None
        names: list[str] = []
        labels: dict[str, str] = {}
        widgets: dict[str, str] = {}
        exclude: set[str] = set(skip or ())
        if meta is not None:
            mmod, mcls = meta
            model = self.model_of(mmod, class_attr(mcls, "model"))
            raw = class_attr(mcls, "fields")
            if isinstance(raw, ast.Constant) and raw.value == "__all__" and model is not None:
                names = [n for n, f in model.fields.items() if f.editable]
            else:
                names = _const_list(raw)
            exclude |= set(_const_list(class_attr(mcls, "exclude")))
            labels = self._str_dict(mmod, class_attr(mcls, "labels"))
            widget_map = class_attr(mcls, "widgets")
            if isinstance(widget_map, ast.Dict):
                for k, v in zip(widget_map.keys, widget_map.values, strict=False):
                    if isinstance(k, ast.Constant) and isinstance(k.value, str):
                        widget = (dotted_name(v) or call_name(v)).split(".")[-1]
                        if widget in WIDGET_TYPES:
                            widgets[k.value] = WIDGET_TYPES[widget]
        if model is None and bases & USER_CREATION_FORMS:
            model = self.user_model
            names = names or ["username"]
        for fname in names:
            if fname in exclude:
                continue
            mf = model.fields.get(fname) if model is not None else None
            if mf is None:
                fields[fname] = FormField(
                    name=fname, label=labels.get(fname), type="text", required=True
                )
                continue
            fields[fname] = mf.form_field(labels.get(fname), widgets.get(fname))

    def _str_dict(self, module: PyModule, node: ast.expr | None) -> dict[str, str]:
        out: dict[str, str] = {}
        if isinstance(node, ast.Dict):
            for k, v in zip(node.keys, node.values, strict=False):
                if isinstance(k, ast.Constant) and isinstance(k.value, str) and v is not None:
                    text = text_of(self.index, module, v, self.translate)
                    if text:
                        out[k.value] = text
        return out

    def _declared(self, module: PyModule, cls: ast.ClassDef, form: bool) -> dict[str, FormField]:
        out: dict[str, FormField] = {}
        for node in cls.body:
            if not (isinstance(node, ast.Assign) and len(node.targets) == 1):
                continue
            target = node.targets[0]
            call = node.value
            if not (isinstance(target, ast.Name) and isinstance(call, ast.Call)):
                continue
            kind = call_name(call).split(".")[-1]
            if not (kind.endswith("Field") or kind in {"CurrentUserDefault"}):
                continue
            if kind in {"HiddenField", "SerializerMethodField", "ReadOnlyField"}:
                continue
            read_only = kwarg(call, "read_only")
            if isinstance(read_only, ast.Constant) and read_only.value is True:
                continue
            widget_node = kwarg(call, "widget")
            widget = (dotted_name(widget_node) or call_name(widget_node)).split(".")[-1]
            ftype = WIDGET_TYPES.get(widget) or FIELD_TYPES.get(kind, "text")
            style = kwarg(call, "style")
            if isinstance(style, ast.Dict) and "password" in ast.unparse(style):
                ftype = "password"
            if "password" in target.id and ftype == "text":
                ftype = "password"
            label = text_of(self.index, module, kwarg(call, "label"), self.translate)
            required_node = kwarg(call, "required")
            required = not (
                isinstance(required_node, ast.Constant) and required_node.value is False
            )
            choices = choices_of(self.index, module, kwarg(call, "choices"), self.translate)
            if choices and ftype == "text":
                ftype = "select"
            out[target.id] = FormField(
                name=target.id,
                label=label if form or label else None,
                type=ftype,
                required=required and ftype != "checkbox",
                rules=_merge_rules(rules_from(self.index, module, call, kind)),
                options=[v for v, _ in choices] or None,
            )
        return out


def nested_class_owner(module: PyModule, cls: ast.ClassDef) -> bool:
    """True when ``cls`` is defined inside another class of the module."""
    for top in module.tree.body:
        if isinstance(top, ast.ClassDef) and cls in top.body:
            return True
    return False


def _const_list(node: ast.expr | None) -> list[str]:
    if isinstance(node, ast.List | ast.Tuple):
        return [
            e.value for e in node.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)
        ]
    return []
