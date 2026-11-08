"""Flask: routes, blueprints, guards, WTForms and Jinja templates (TZ FR-S3, FR-S4, T29).

Read with the stdlib ast, never imported. ``Flask(...)`` and ``Blueprint(..., url_prefix=)``
plus ``register_blueprint(url_prefix=)`` give full paths; ``@bp.route`` / ``@bp.get`` give
methods. Guards come from decorators (Flask-Login, Flask-Security, flask-jwt-extended,
project decorators), ``before_request`` hooks and checks in the body. Flask views look like
Django function views, so templates, components and route output are shared with the
Django parser. Entities come from the SQLAlchemy parser.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field

from yoriqnoma_scanner.detect import ProjectInfo
from yoriqnoma_scanner.fs_guard import SafeFS
from yoriqnoma_scanner.parsers.base import GuardInfo, ParseResult
from yoriqnoma_scanner.parsers.django_models import (
    FIELD_TYPES,
    capfirst,
    class_chain,
    enum_value,
    resolve_dotted_class,
    snake,
    text_of,
)
from yoriqnoma_scanner.parsers.django_routes import (
    DjangoParser,
    DjangoSettings,
    UrlEntry,
    ViewInfo,
    django_route,
    join_url,
)
from yoriqnoma_scanner.parsers.i18n import load_po_catalogue
from yoriqnoma_scanner.parsers.pyviews import (
    ROLE_ATTRS,
    FuncDef,
    _is_admin_word,
    _path_verb,
    _strings,
)
from yoriqnoma_scanner.pyindex import ENUM_BASES, PyIndex, PyModule, call_name, dotted_name, kwarg
from yoriqnoma_schemas import FormField

HTTP_DECORATORS = {"get", "post", "put", "patch", "delete"}
AUTH_DECORATORS = {"login_required", "fresh_login_required", "jwt_required", "auth_required"}
ROLE_DECORATORS = {"roles_required", "roles_accepted", "role_required", "has_role"}
IGNORED = {
    "cache",
    "cached",
    "limit",
    "limiter",
    "csrf_exempt",
    "cross_origin",
    "wraps",
    "staticmethod",
    "classmethod",
    "property",
    "doc",
    "response",
    "input",
    "output",
}
WTF_TYPES = {
    **FIELD_TYPES,
    "StringField": "text",
    "PasswordField": "password",
    "EmailField": "email",
    "TextAreaField": "textarea",
    "SelectField": "select",
    "SelectMultipleField": "select",
    "RadioField": "select",
    "IntegerField": "number",
    "DecimalField": "number",
    "FloatField": "number",
    "BooleanField": "checkbox",
    "DateField": "date",
    "DateTimeField": "date",
    "DateTimeLocalField": "date",
    "FileField": "file",
    "MultipleFileField": "file",
    "TelField": "tel",
    "URLField": "url",
    "HiddenField": "hidden",
    "SubmitField": "submit",
}
WTF_REQUIRED = {"DataRequired", "InputRequired"}


@dataclass
class FlaskBlueprint:
    name: str
    prefix: str
    module: PyModule
    var: str
    mounts: list[str] = field(default_factory=list)  # prefixes from register_blueprint


class FlaskParser(DjangoParser):
    name = "flask"

    def applies(self, project: ProjectInfo) -> bool:
        return "flask" in project.stacks

    def parse(self, project: ProjectInfo, fs: SafeFS) -> ParseResult:
        self.fs = fs
        self.index = PyIndex(fs, project.python_files)
        self.result = ParseResult(notes=[f"flask: {e}" for e in self.index.errors])
        self.settings = DjangoSettings()
        self.catalogue = load_po_catalogue(fs, project.po_files, self.language, self.result.notes)
        self.templates = self._template_index(project.template_files)
        self.url_names: dict[str, str] = {}
        self.layouts: set[str] = set()
        self._group_roles: dict[str, str] = {}
        self._signup_default = self._user_role_default()

        blueprints = self._blueprints()
        entries: list[tuple[UrlEntry, FuncDef, FlaskBlueprint | None, list[str]]] = []
        for module in self.index.modules.values():
            for func in [n for n in ast.walk(module.tree) if isinstance(n, FuncDef)]:
                for deco in func.decorator_list:
                    route = self._route(module, deco, blueprints)
                    if route is None:
                        continue
                    bp, path, methods, endpoint = route
                    for prefix in (bp.mounts or [bp.prefix]) if bp else [""]:
                        full = join_url(prefix, django_route(path))
                        name = endpoint or func.name
                        key = f"{bp.name}.{name}" if bp else name
                        self.url_names.setdefault(key, full)
                        entry = UrlEntry(
                            full, key, module, ast.Name(id=func.name), module.src(func)
                        )
                        entries.append((entry, func, bp, methods))
        hooks = self._before_request_guards(blueprints)
        for entry, view_func, bp, methods in entries:
            info = self._flask_view(entry, view_func, bp, methods)
            info.guards += hooks.get(bp.var if bp else "", []) + hooks.get("__app__", [])
            self._add_routes(entry, info)
        self._emit_layouts()
        self._collect_flask_roles()
        return self.result

    # --- blueprints and routes ------------------------------------------------------

    def _blueprints(self) -> dict[tuple[str, str], FlaskBlueprint]:
        found: dict[tuple[str, str], FlaskBlueprint] = {}
        for module in self.index.modules.values():
            for var, value in module.assigns.items():
                if (
                    not isinstance(value, ast.Call)
                    or call_name(value).split(".")[-1] != "Blueprint"
                ):
                    continue
                name = self.index.string_constant(module, value.args[0] if value.args else None)
                prefix = self.index.string_constant(module, kwarg(value, "url_prefix")) or ""
                found[(module.name, var)] = FlaskBlueprint(name or var, prefix, module, var)
        for module in self.index.modules.values():
            for node in ast.walk(module.tree):
                if not (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "register_blueprint"
                    and node.args
                ):
                    continue
                bp = self._bp_ref(module, node.args[0], found)
                if bp is None:
                    continue
                mount = self.index.string_constant(module, kwarg(node, "url_prefix"))
                parent = self._bp_ref(module, node.func.value, found)
                base = (parent.mounts or [parent.prefix]) if parent else [""]
                for p in base:
                    bp.mounts.append(join_url(p, mount if mount is not None else bp.prefix))
        return found

    def _bp_ref(
        self, module: PyModule, node: ast.expr, found: dict[tuple[str, str], FlaskBlueprint]
    ) -> FlaskBlueprint | None:
        dotted = dotted_name(node)
        if not dotted:
            return None
        parts = dotted.split(".")
        resolved = self.index.resolve(module, parts[0])
        if isinstance(resolved, tuple):
            return found.get((resolved[0].name, resolved[1]))
        if isinstance(resolved, PyModule) and len(parts) > 1:
            return found.get((resolved.name, parts[-1]))
        return found.get((module.name, parts[0]))

    def _route(
        self, module: PyModule, deco: ast.expr, blueprints: dict[tuple[str, str], FlaskBlueprint]
    ) -> tuple[FlaskBlueprint | None, str, list[str], str | None] | None:
        if not (isinstance(deco, ast.Call) and isinstance(deco.func, ast.Attribute)):
            return None
        verb = deco.func.attr
        if verb != "route" and verb not in HTTP_DECORATORS:
            return None
        owner = deco.func.value
        bp = self._bp_ref(module, owner, blueprints)
        if bp is None and not self._is_app(module, owner):
            return None
        path = self.index.string_constant(
            module, deco.args[0] if deco.args else kwarg(deco, "rule")
        )
        if path is None:
            return None
        methods = (
            [m.upper() for m in _strings(kwarg(deco, "methods"))] or ["GET"]
            if verb == "route"
            else [verb.upper()]
        )
        endpoint = self.index.string_constant(module, kwarg(deco, "endpoint"))
        return bp, path, methods, endpoint

    def _is_app(self, module: PyModule, node: ast.expr) -> bool:
        name = dotted_name(node)
        found = self.index.resolve_assign(module, name.split(".")[0]) if name else None
        return bool(found and call_name(found[1]).split(".")[-1] in {"Flask", "APIFlask"})

    def _before_request_guards(
        self, blueprints: dict[tuple[str, str], FlaskBlueprint]
    ) -> dict[str, list[GuardInfo]]:
        """``@bp.before_request`` checks apply to every route of the blueprint."""
        out: dict[str, list[GuardInfo]] = {}
        for module in self.index.modules.values():
            for func in [n for n in ast.walk(module.tree) if isinstance(n, FuncDef)]:
                for deco in func.decorator_list:
                    target = deco.func if isinstance(deco, ast.Call) else deco
                    if not (isinstance(target, ast.Attribute) and target.attr == "before_request"):
                        continue
                    bp = self._bp_ref(module, target.value, blueprints)
                    key = bp.var if bp else "__app__"
                    guards = self._body_guards(module, func)
                    for inner in func.decorator_list:
                        if inner is not deco:
                            guards += self._flask_decorator(module, inner)[0]
                    out.setdefault(key, []).extend(guards)
        return out

    # --- views ------------------------------------------------------------------------

    def _flask_view(
        self, entry: UrlEntry, func: FuncDef, bp: FlaskBlueprint | None, methods: list[str]
    ) -> ViewInfo:
        module = entry.module
        guards: list[GuardInfo] = []
        for deco in func.decorator_list:
            guards += self._flask_decorator(module, deco)[0]
        guards += self._body_guards(module, func)
        if self._owned([func]):
            guards.append(GuardInfo("ownership", "egalik tekshiruvi", module.src(func)))
        template = self._render_template_flask(module, func)
        form_cls = self._wtf_form(module, func)
        fields, submit = self._wtf_fields(*form_cls) if form_cls else (None, None)
        entity, read = self._flask_read(module, func)
        write = _path_verb(entry.path) if entity and read == "view" else None
        sets, requires = self._status_logic(module, [func])
        return ViewInfo(
            id=f"{module.name}.{func.name}",
            source=module.src(func),
            methods=methods,
            guards=guards,
            template=template,
            form_fields=fields,
            entity=entity,
            read_action=read,
            write_action=write,
            status_sets=sets,
            status_requires=requires,
            creates_user_role=self._flask_created_role(module, func),
            downloads=self._downloads(func)
            or any(call_name(n).endswith("send_file") for n in ast.walk(func)),
            renders=template is not None,
            submit_label=submit,
        )

    def _flask_decorator(
        self, module: PyModule, deco: ast.expr
    ) -> tuple[list[GuardInfo], list[str] | None]:
        name = (call_name(deco) or dotted_name(deco)).split(".")[-1]
        src = module.src(deco)
        expr = ast.unparse(deco)
        if name in HTTP_DECORATORS or name == "route" or name in IGNORED:
            return [], None
        if name in AUTH_DECORATORS:
            return [GuardInfo("auth", expr, src)], None
        if name in ROLE_DECORATORS and isinstance(deco, ast.Call):
            roles = [v for a in deco.args if (v := enum_value(self.index, module, a))]
            roles += [s for a in deco.args for s in _strings(a) if s not in roles]
            if roles:
                admin = any(_is_admin_word(r) for r in roles)
                return [GuardInfo("role", expr, src, roles, admin=admin)], None
            return [GuardInfo("unknown", expr, src)], None
        if name in {"permission_required", "permissions_required", "permissions_accepted"}:
            return [GuardInfo("unknown", expr, src)], None
        if any(w in name.lower() for w in ("admin", "superuser", "staff")):
            return [GuardInfo("role", expr, src, ["admin"], admin=True)], None
        target = deco.func if isinstance(deco, ast.Call) else deco
        found = self._resolve_function(module, target)
        args = list(deco.args) if isinstance(deco, ast.Call) else []
        if found is not None:
            guard = self._guard_function(found[0], found[1], args, module, expr, src)
            return ([guard] if guard else []), None
        low = name.lower()
        if any(w in low for w in ("login", "auth", "token")):
            return [GuardInfo("auth", expr, src)], None
        if any(w in low for w in ("role", "perm", "group", "require", "allowed", "only")):
            return [GuardInfo("unknown", expr, src)], None
        return [], None

    def _render_template_flask(self, module: PyModule, func: FuncDef) -> str | None:
        for node in ast.walk(func):
            if isinstance(node, ast.Call) and call_name(node).split(".")[-1] == "render_template":
                value = self.index.string_constant(
                    module, node.args[0] if node.args else kwarg(node, "template_name_or_list")
                )
                if value:
                    return value
        return None

    def _wtf_form(self, module: PyModule, func: FuncDef) -> tuple[PyModule, ast.ClassDef] | None:
        for node in ast.walk(func):
            if not isinstance(node, ast.Call):
                continue
            name = dotted_name(node.func)
            if not name or not name.split(".")[-1][:1].isupper():
                continue
            found = resolve_dotted_class(self.index, module, name)
            if found and self.index.class_bases(*found) & {"FlaskForm", "Form", "BaseForm"}:
                return found
        return None

    def _wtf_fields(
        self, module: PyModule, cls: ast.ClassDef
    ) -> tuple[list[FormField], str | None]:
        """WTForms fields of a form class (bases first) and the submit button label."""
        fields: dict[str, FormField] = {}
        submit: str | None = None
        for mod, klass in reversed(class_chain(self.index, module, cls)):
            for node in klass.body:
                if not (isinstance(node, ast.Assign) and len(node.targets) == 1):
                    continue
                target, call = node.targets[0], node.value
                if not (isinstance(target, ast.Name) and isinstance(call, ast.Call)):
                    continue
                kind = call_name(call).split(".")[-1]
                ftype = WTF_TYPES.get(kind)
                if ftype is None:
                    continue
                label_node = call.args[0] if call.args else kwarg(call, "label")
                label = text_of(self.index, mod, label_node, self.translate)
                if ftype == "submit":
                    submit = label or submit
                    continue
                if ftype == "hidden":
                    continue
                rules: list[str] = []
                required = False
                validators = call.args[1] if len(call.args) > 1 else kwarg(call, "validators")
                items = validators.elts if isinstance(validators, ast.List | ast.Tuple) else []
                for item in items:
                    vname = call_name(item).split(".")[-1] or dotted_name(item).split(".")[-1]
                    if vname in WTF_REQUIRED:
                        required = True
                    elif vname in {"Length", "NumberRange"} and isinstance(item, ast.Call):
                        for key in ("min", "max"):
                            value = kwarg(item, key)
                            if isinstance(value, ast.Constant) and isinstance(
                                value.value, int | float
                            ):
                                rules.append(f"{key}:{value.value}")
                    elif vname == "Regexp" and isinstance(item, ast.Call) and item.args:
                        regex = self.index.string_constant(mod, item.args[0])
                        if regex:
                            rules.append(f"regex:{regex}")
                    elif vname == "Email" and ftype == "text":
                        ftype = "email"
                options: list[str] = []
                choices = kwarg(call, "choices")
                if isinstance(choices, ast.List | ast.Tuple):
                    for item in choices.elts:
                        first = item.elts[0] if isinstance(item, ast.Tuple) and item.elts else item
                        if isinstance(first, ast.Constant):
                            options.append(str(first.value))
                fields[target.id] = FormField(
                    name=target.id,
                    label=capfirst(label) if label else None,
                    type=ftype,
                    required=required and ftype != "checkbox",
                    rules="|".join(rules) or None,
                    options=options or None,
                )
        return list(fields.values()), submit

    def _flask_read(self, module: PyModule, func: FuncDef) -> tuple[str | None, str | None]:
        """``Order.query.get_or_404(id)`` -> ("order", "view"); ``.all()`` -> "list"."""
        listed: str | None = None
        for node in ast.walk(func):
            if not isinstance(node, ast.Call):
                continue
            name = call_name(node).split(".")[-1]
            if name in {"get_or_404", "first_or_404"} and call_name(node).startswith("db."):
                model = self._model_name(module, node.args[0] if node.args else None)
                if model:
                    return model, "view"
            for sub in ast.walk(node.func):
                if isinstance(sub, ast.Attribute) and sub.attr == "query":
                    model = self._model_name(module, sub.value)
                    if model is None:
                        break
                    if name in {"get_or_404", "first_or_404", "get", "first", "one", "one_or_404"}:
                        return model, "view"
                    listed = listed or model
                    break
            if name == "select" and node.args:  # db.select(Order)
                model = self._model_name(module, node.args[0])
                listed = listed or model
        return (listed, "list") if listed else (None, None)

    def _model_name(self, module: PyModule, node: ast.expr | None) -> str | None:
        if node is None:
            return None
        found = resolve_dotted_class(self.index, module, dotted_name(node))
        if found is None:
            return None
        bases = self.index.class_bases(*found)
        if "Model" not in bases and "Base" not in bases and "DeclarativeBase" not in bases:
            return None
        if bases & {"UserMixin"} or found[1].name.lower() in {"user", "users"}:
            return None
        return snake(found[1].name)

    def _flask_created_role(self, module: PyModule, func: FuncDef) -> str | None:
        creates_user = False
        for node in ast.walk(func):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Attribute) and target.attr in ROLE_ATTRS:
                        value = enum_value(self.index, module, node.value)
                        if value is not None:
                            return value
            elif isinstance(node, ast.Call):
                cls = resolve_dotted_class(self.index, module, dotted_name(node.func))
                if cls is not None and (
                    cls[1].name.lower() == "user" or "UserMixin" in self.index.class_bases(*cls)
                ):
                    creates_user = True
                    for kw in node.keywords:
                        if kw.arg in ROLE_ATTRS:
                            value = enum_value(self.index, module, kw.value)
                            if value is not None:
                                return value
        return (self._signup_default or "user") if creates_user else None

    # --- roles ------------------------------------------------------------------------

    def _user_role_default(self) -> str | None:
        for module in self.index.modules.values():
            for cls in module.classes.values():
                if cls.name.lower() != "user" and "UserMixin" not in self.index.class_bases(
                    module, cls
                ):
                    continue
                for node in cls.body:
                    target: ast.expr
                    if isinstance(node, ast.AnnAssign):
                        target, value = node.target, node.value
                    elif isinstance(node, ast.Assign):
                        target, value = node.targets[0], node.value
                    else:
                        continue
                    if not (isinstance(target, ast.Name) and target.id in ROLE_ATTRS):
                        continue
                    if isinstance(value, ast.Call):
                        default = kwarg(value, "default")
                        resolved = enum_value(self.index, module, default)
                        if resolved:
                            return resolved
        return None

    def _collect_flask_roles(self) -> None:
        for module in self.index.modules.values():
            for cname, cls in module.classes.items():
                if (
                    "role" not in cname.lower()
                    or not self.index.class_bases(module, cls) & ENUM_BASES
                ):
                    continue
                for node in cls.body:
                    if (
                        isinstance(node, ast.Assign)
                        and isinstance(node.targets[0], ast.Name)
                        and isinstance(node.value, ast.Constant)
                    ):
                        self.result.role_values.setdefault(str(node.value.value), module.src(cls))
        for gid, group in self._group_roles.items():
            self.result.role_values.setdefault(gid, "groups")
            self.result.role_labels.setdefault(gid, group)
        signup = {r.creates_user_role for r in self.result.routes if r.creates_user_role}
        authed = any(g.kind in {"auth", "ownership"} for r in self.result.routes for g in r.guards)
        roles = {g for r in self.result.routes for gd in r.guards for g in gd.roles}
        if not self.result.role_values and not roles - {"admin"} and (authed or signup):
            self.result.role_values.setdefault("user", "flask_login (kirgan foydalanuvchi)")
        for role in signup:
            self.result.role_values.setdefault(role, "ro'yxatdan o'tish")
