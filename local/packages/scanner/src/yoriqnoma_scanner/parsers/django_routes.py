"""Django and Django REST framework: urls, views, guards and templates (TZ FR-S3, FR-S4).

Read with the stdlib ast, never imported. ``urls.py`` chains (``path`` / ``re_path`` /
``include``, ``app_name`` namespaces, DRF routers) give full paths. Views give guards
(decorators, mixins, permission classes, checks in the body), the methods they handle,
status changes and the entity they show or change. Templates give forms, buttons, links
and the navigation. Unclear guards stay ``unknown`` and are excluded (default-deny).
"""

from __future__ import annotations

import ast
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from yoriqnoma_scanner.detect import ProjectInfo
from yoriqnoma_scanner.fs_guard import SafeFS
from yoriqnoma_scanner.parsers.base import (
    ActionBinding,
    ComponentInfo,
    GuardInfo,
    LinkInfo,
    NavItem,
    ParseResult,
    RouteCandidate,
)
from yoriqnoma_scanner.parsers.django_models import (
    USER_CREATION_FORMS,
    DjangoModel,
    DjangoModels,
    chain_attr,
    class_chain,
    enum_value,
    resolve_dotted_class,
    snake,
)
from yoriqnoma_scanner.parsers.html_forms import URL_MARK, TemplateInfo, TForm, parse_template
from yoriqnoma_scanner.parsers.i18n import load_po_catalogue
from yoriqnoma_scanner.parsers.pyviews import (
    ADMIN_FLAGS,
    ROLE_ATTRS,
    WRITE_METHODS,
    PyViewChecks,
    _is_admin_word,
    _path_verb,
    _strings,
    _user_expr,
)
from yoriqnoma_scanner.pyindex import PyIndex, PyModule, call_name, dotted_name, kwarg
from yoriqnoma_schemas import Form, FormField, Target

FuncDef = ast.FunctionDef | ast.AsyncFunctionDef
AttrGetter = Callable[[str], "tuple[PyModule, ast.expr] | None"]


METHOD_DECORATORS = {"require_POST": ["POST"], "require_GET": ["GET"], "require_safe": ["GET"]}
AUTH_DECORATORS = {"login_required"}
IGNORED_DECORATORS = {
    "csrf_exempt",
    "csrf_protect",
    "ensure_csrf_cookie",
    "requires_csrf_token",
    "never_cache",
    "cache_page",
    "cache_control",
    "vary_on_headers",
    "vary_on_cookie",
    "atomic",
    "non_atomic_requests",
    "sensitive_post_parameters",
    "sensitive_variables",
    "xframe_options_exempt",
    "xframe_options_sameorigin",
    "xframe_options_deny",
    "gzip_page",
    "condition",
    "etag",
    "last_modified",
    "wraps",
    "authentication_classes",
    "throttle_classes",
    "renderer_classes",
    "parser_classes",
    "schema",
    "extend_schema",
    "swagger_auto_schema",
    "staticmethod",
    "classmethod",
    "property",
}

# Generic class-based views, most specific first: (base, entity action, methods, suffix).
GENERIC_VIEWS: list[tuple[str, str | None, list[str], str | None]] = [
    ("DeleteView", "delete", ["GET", "POST"], "_confirm_delete"),
    ("UpdateView", "update", ["GET", "POST"], "_form"),
    ("CreateView", "create", ["GET", "POST"], "_form"),
    ("FormView", None, ["GET", "POST"], None),
    ("DetailView", "view", ["GET"], "_detail"),
    ("ListView", "list", ["GET"], "_list"),
    ("ArchiveIndexView", "list", ["GET"], "_archive"),
    ("TemplateView", None, ["GET"], None),
    ("RedirectView", None, [], None),
]
# django.contrib.auth views: (account action, default template, methods, form, guest page).
AUTH_VIEWS: dict[str, tuple[str, str | None, list[str], str | None, bool]] = {
    "LoginView": ("login", "registration/login.html", ["GET", "POST"], "AuthenticationForm", True),
    "LogoutView": ("logout", None, ["POST"], None, True),
    "PasswordChangeView": (
        "password_change",
        "registration/password_change_form.html",
        ["GET", "POST"],
        "PasswordChangeForm",
        False,
    ),
    "PasswordResetView": (
        "password_reset",
        "registration/password_reset_form.html",
        ["GET", "POST"],
        "PasswordResetForm",
        True,
    ),
}
AUTH_SKIPPED = {
    "PasswordChangeDoneView",
    "PasswordResetDoneView",
    "PasswordResetConfirmView",
    "PasswordResetCompleteView",
}
AUTH_URLS = [  # django.contrib.auth.urls
    ("login/", "login", "LoginView"),
    ("logout/", "logout", "LogoutView"),
    ("password_change/", "password_change", "PasswordChangeView"),
    ("password_change/done/", "password_change_done", "PasswordChangeDoneView"),
    ("password_reset/", "password_reset", "PasswordResetView"),
    ("password_reset/done/", "password_reset_done", "PasswordResetDoneView"),
    ("reset/<uidb64>/<token>/", "password_reset_confirm", "PasswordResetConfirmView"),
    ("reset/done/", "password_reset_complete", "PasswordResetCompleteView"),
]
# django-allauth: (route, url name, action, template, fields used when no project template).
ALLAUTH_URLS: list[tuple[str, str, str, str, list[tuple[str, str]]]] = [
    (
        "login/",
        "account_login",
        "login",
        "account/login.html",
        [("login", "text"), ("password", "password")],
    ),
    (
        "signup/",
        "account_signup",
        "signup",
        "account/signup.html",
        [("email", "email"), ("password1", "password"), ("password2", "password")],
    ),
    ("logout/", "account_logout", "logout", "account/logout.html", []),
    (
        "password/reset/",
        "account_reset_password",
        "password_reset",
        "account/password_reset.html",
        [("email", "email")],
    ),
]
BUILTIN_FORM_FIELDS = {
    "AuthenticationForm": [("username", "text"), ("password", "password")],
    "PasswordChangeForm": [
        ("old_password", "password"),
        ("new_password1", "password"),
        ("new_password2", "password"),
    ],
    "PasswordResetForm": [("email", "email")],
}

# Django REST framework.
DRF_VIEWSETS = {
    "ModelViewSet": ["list", "create", "retrieve", "update", "partial_update", "destroy"],
    "ReadOnlyModelViewSet": ["list", "retrieve"],
    "GenericViewSet": [],
    "ViewSet": [],
    "ViewSetMixin": [],
}
DRF_MIXINS = {
    "ListModelMixin": ["list"],
    "CreateModelMixin": ["create"],
    "RetrieveModelMixin": ["retrieve"],
    "UpdateModelMixin": ["update", "partial_update"],
    "DestroyModelMixin": ["destroy"],
}
VIEWSET_ACTIONS = {  # action: (method, on the detail route, entity action)
    "list": ("GET", False, "list"),
    "create": ("POST", False, "create"),
    "retrieve": ("GET", True, "view"),
    "update": ("PUT", True, "update"),
    "partial_update": ("PATCH", True, "update"),
    "destroy": ("DELETE", True, "delete"),
}
DRF_GENERICS: dict[str, dict[str, str]] = {  # base: method -> entity action
    "ListCreateAPIView": {"GET": "list", "POST": "create"},
    "RetrieveUpdateDestroyAPIView": {
        "GET": "view",
        "PUT": "update",
        "PATCH": "update",
        "DELETE": "delete",
    },
    "RetrieveUpdateAPIView": {"GET": "view", "PUT": "update", "PATCH": "update"},
    "RetrieveDestroyAPIView": {"GET": "view", "DELETE": "delete"},
    "ListAPIView": {"GET": "list"},
    "CreateAPIView": {"POST": "create"},
    "RetrieveAPIView": {"GET": "view"},
    "UpdateAPIView": {"PUT": "update", "PATCH": "update"},
    "DestroyAPIView": {"DELETE": "delete"},
}
DRF_API_BASES = {"APIView", "GenericAPIView", *DRF_GENERICS}
PERFORM_HOOKS = {
    "create": "perform_create",
    "update": "perform_update",
    "partial_update": "perform_update",
    "destroy": "perform_destroy",
}
DRF_PERMS = {
    "AllowAny": "",
    "IsAuthenticated": "auth",
    "IsAuthenticatedOrReadOnly": "auth_write",
    "IsAdminUser": "admin",
    "DjangoModelPermissions": "unknown",
    "DjangoModelPermissionsOrAnonReadOnly": "unknown",
    "DjangoObjectPermissions": "unknown",
}

_DJANGO_PARAM = re.compile(r"<(?:\w+:)?(\w+)>")
_INCLUDE = re.compile(r"\{%\s*include\s+[\"']([^\"']+)[\"'][^%]*%\}")
_EXTENDS = re.compile(r"\{%\s*extends\s+[\"']([^\"']+)[\"']\s*%\}")


def django_route(route: str) -> str:
    """``tickets/<int:pk>/`` -> ``tickets/:pk/``."""
    return _DJANGO_PARAM.sub(lambda m: ":" + m.group(1), route)


def regex_route(regex: str) -> str:
    """``^support/(?P<pk>\\d+)/reply/$`` -> ``support/:pk/reply/``."""
    text = regex.removeprefix("^").removesuffix("$").removesuffix("\\Z")
    text = re.sub(r"\(\?P<(\w+)>[^)]*\)", r":\1", text)
    text = re.sub(r"\([^)]*\)", ":arg", text)
    return text.replace("\\", "").replace("?", "")


def join_url(prefix: str, part: str) -> str:
    if not prefix:
        return "/" + part.lstrip("/")
    return "/" + (prefix.strip("/") + "/" + part.lstrip("/")).lstrip("/")


@dataclass
class DjangoSettings:
    root_urlconf: str | None = None
    auth_user_model: str | None = None
    login_required_default: bool = False
    drf_permissions: list[str] = field(default_factory=lambda: ["AllowAny"])
    language: str | None = None


@dataclass
class UrlEntry:
    path: str
    name: str | None
    module: PyModule
    view: ast.expr
    source: str
    builtin: str | None = None  # "admin", "auth:LoginView", "allauth:signup"


@dataclass
class ResolvedView:
    module: PyModule
    node: FuncDef | ast.ClassDef | None  # None: a Django class (TemplateView, LoginView...)
    builtin: str | None = None
    kwargs: dict[str, ast.expr] = field(default_factory=dict)  # as_view(...) arguments
    wrappers: list[ast.expr] = field(default_factory=list)  # login_required(view) in urls


@dataclass
class ViewInfo:
    id: str
    source: str
    methods: list[str]
    guards: list[GuardInfo]
    template: str | None = None
    form_fields: list[FormField] | None = None
    builtin_fields: bool = False  # form fields known only from Django's own form
    entity: str | None = None
    read_action: str | None = None
    write_action: str | None = None
    status_sets: list[tuple[str, str]] = field(default_factory=list)
    status_requires: list[str] = field(default_factory=list)
    creates_user_role: str | None = None
    downloads: bool = False
    renders: bool = True  # GET answers with an HTML page
    request_model: str | None = None
    public: bool = False  # open even under LoginRequiredMiddleware (login page...)
    submit_label: str | None = None  # WTForms SubmitField label when the template has none


class DjangoParser(PyViewChecks):
    name = "django"

    def __init__(self, language: str = "uz") -> None:
        self.language = language

    def applies(self, project: ProjectInfo) -> bool:
        return "django" in project.stacks

    # --- entry ------------------------------------------------------------------

    def parse(self, project: ProjectInfo, fs: SafeFS) -> ParseResult:
        self.fs = fs
        self.index = PyIndex(fs, project.python_files)
        self.result = ParseResult(notes=[f"django: {e}" for e in self.index.errors])
        self.settings = self._read_settings()
        self.catalogue = load_po_catalogue(
            fs, project.po_files, self.settings.language or self.language, self.result.notes
        )
        self.models = DjangoModels(self.index, self.translate, self.settings.auth_user_model)
        self.templates = self._template_index(project.template_files)
        self.url_names: dict[str, str] = {}
        self.layouts: set[str] = set()
        self._seen_urls: set[tuple[str, str]] = set()
        self._group_roles: dict[str, str] = {}

        entries: list[UrlEntry] = []
        for root in self._url_roots():
            self._walk(root, self._patterns(root), "", None, 0, entries)
        for entry in entries:
            self._emit(entry)
        self._emit_layouts()
        self._collect_roles()
        self.result.entities = self.models.entities()
        self.result.i18n.update(self.models.status_labels())
        return self.result

    def translate(self, text: str) -> str:
        return self.catalogue.get(text) or text

    # --- settings and templates ---------------------------------------------------

    def _read_settings(self) -> DjangoSettings:
        settings = DjangoSettings()
        for module in self.index.modules.values():
            assigns = module.assigns
            if "INSTALLED_APPS" not in assigns and "ROOT_URLCONF" not in assigns:
                continue
            settings.root_urlconf = settings.root_urlconf or self.index.string_constant(
                module, assigns.get("ROOT_URLCONF")
            )
            settings.auth_user_model = settings.auth_user_model or self.index.string_constant(
                module, assigns.get("AUTH_USER_MODEL")
            )
            settings.language = settings.language or self.index.string_constant(
                module, assigns.get("LANGUAGE_CODE")
            )
            if any("LoginRequiredMiddleware" in m for m in _strings(assigns.get("MIDDLEWARE"))):
                settings.login_required_default = True
            drf = assigns.get("REST_FRAMEWORK")
            if isinstance(drf, ast.Dict):
                for key, value in zip(drf.keys, drf.values, strict=False):
                    if (
                        isinstance(key, ast.Constant)
                        and key.value == "DEFAULT_PERMISSION_CLASSES"
                        and value is not None
                    ):
                        settings.drf_permissions = [s.split(".")[-1] for s in _strings(value)]
        if settings.language:
            settings.language = settings.language.lower().replace("_", "-")
        return settings

    def _template_index(self, files: list[Path]) -> dict[str, Path]:
        """Template name ("helpdesk/home.html") -> file, for every ``templates/`` folder."""
        out: dict[str, Path] = {}
        for path in files:
            parts = PurePosixPath(self.fs.rel(path)).parts
            for i in range(len(parts) - 1, -1, -1):
                if parts[i] in {"templates", "jinja2"}:
                    out.setdefault("/".join(parts[i + 1 :]), path)
                    break
        return out

    def _template_text(self, name: str, depth: int = 0) -> str | None:
        path = self.templates.get(name)
        if path is None or depth > 3:
            return None
        text = self.fs.read_text(path)
        if text is None:
            return None

        def include(match: re.Match[str]) -> str:
            return self._template_text(match.group(1), depth + 1) or ""

        return _INCLUDE.sub(include, text)

    def _template(self, name: str | None) -> tuple[TemplateInfo, str] | None:
        if not name:
            return None
        text = self._template_text(name)
        if text is None:
            return None
        parent = _EXTENDS.search(text)
        while parent and parent.group(1) not in self.layouts:
            self.layouts.add(parent.group(1))
            parent_text = self._template_text(parent.group(1)) or ""
            parent = _EXTENDS.search(parent_text)
        return parse_template(text, self.translate), self.fs.rel(self.templates[name])

    # --- urls -------------------------------------------------------------------

    def _url_roots(self) -> list[PyModule]:
        if self.settings.root_urlconf:
            root = self.index.find_module(self.settings.root_urlconf)
            if root is not None:
                return [root]
            self.result.notes.append(f"ROOT_URLCONF «{self.settings.root_urlconf}» topilmadi")
        url_modules = [
            m
            for m in self.index.modules.values()
            if m.name.split(".")[-1] == "urls" and "urlpatterns" in m.assigns
        ]
        included: set[str] = set()
        for module in url_modules:
            for node in ast.walk(module.tree):
                if isinstance(node, ast.Call) and call_name(node).endswith("include"):
                    included.update(_strings(node.args[0] if node.args else None))
        return [m for m in url_modules if not any(m.name.endswith(x) for x in included)]

    def _patterns(self, module: PyModule) -> list[ast.expr]:
        items: list[ast.expr] = []

        def flatten(node: ast.expr) -> None:
            if isinstance(node, ast.List | ast.Tuple):
                for el in node.elts:
                    if isinstance(el, ast.Starred):
                        flatten(el.value)
                    else:
                        items.append(el)
            elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
                flatten(node.left)
                flatten(node.right)
            elif isinstance(node, ast.Call) and call_name(node).endswith("i18n_patterns"):
                lang = self.settings.language or "en"
                items.append(
                    ast.Call(
                        func=ast.Name(id="path"),
                        args=[ast.Constant(f"{lang}/"), ast.List(elts=list(node.args))],
                        keywords=[],
                    )
                )
                self.result.notes.append(
                    f"{module.rel}: i18n_patterns — yo'llar «/{lang}/» prefiksi bilan olindi"
                )
            elif isinstance(node, ast.Attribute | ast.Name):
                items.append(node)

        for node in module.tree.body:
            if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "urlpatterns" for t in node.targets
            ):
                flatten(node.value)
            elif (
                isinstance(node, ast.AugAssign)
                and isinstance(node.target, ast.Name)
                and node.target.id == "urlpatterns"
            ):
                flatten(node.value)
        return items

    def _walk(
        self,
        module: PyModule,
        items: list[ast.expr],
        prefix: str,
        namespace: str | None,
        depth: int,
        out: list[UrlEntry],
    ) -> None:
        if depth > 8:
            return
        app_name = self.index.string_constant(module, module.assigns.get("app_name"))
        ns = namespace if namespace is not None else app_name
        for el in items:
            if isinstance(el, ast.Attribute) and el.attr == "urls":
                self._router(module, el.value, prefix)
                continue
            if isinstance(el, ast.List):  # inline list from i18n_patterns
                self._walk(module, list(el.elts), prefix, ns, depth + 1, out)
                continue
            if not isinstance(el, ast.Call):
                continue
            fname = call_name(el).split(".")[-1]
            if fname not in {"path", "re_path", "url"} or len(el.args) < 2:
                continue
            route = self.index.string_constant(module, el.args[0])
            if route is None:
                self.result.notes.append(f"{module.src(el)}: yo'l satri aniqlanmadi")
                continue
            sub = django_route(route) if fname == "path" else regex_route(route)
            full = join_url(prefix, sub)
            view = el.args[1]
            src = module.src(el)
            name = self.index.string_constant(module, kwarg(el, "name"))
            if isinstance(view, ast.List):
                self._walk(module, list(view.elts), full, ns, depth + 1, out)
            elif isinstance(view, ast.Call) and call_name(view).split(".")[-1] == "include":
                self._include(module, view, full, depth, out)
            elif dotted_name(view).endswith("site.urls"):
                out.append(UrlEntry(full, None, module, view, src, builtin="admin"))
            elif isinstance(view, ast.Attribute) and view.attr == "urls":
                self._router(module, view.value, full)
            else:
                qualified = f"{ns}:{name}" if ns and name else name
                if qualified:
                    self.url_names.setdefault(qualified, full)
                if name:
                    self.url_names.setdefault(name, full)
                out.append(UrlEntry(full, qualified, module, view, src))

    def _include(
        self, module: PyModule, call: ast.Call, prefix: str, depth: int, out: list[UrlEntry]
    ) -> None:
        arg = call.args[0] if call.args else None
        namespace = self.index.string_constant(module, kwarg(call, "namespace"))
        src = module.src(call)
        if isinstance(arg, ast.Tuple) and arg.elts:
            namespace = namespace or self.index.string_constant(
                module, arg.elts[1] if len(arg.elts) > 1 else None
            )
            arg = arg.elts[0]
        target = self.index.string_constant(module, arg)
        if target == "django.contrib.auth.urls":
            for route, name, view in AUTH_URLS:
                full = join_url(prefix, django_route(route))
                key = f"{namespace}:{name}" if namespace else name
                self.url_names.setdefault(key, full)
                out.append(UrlEntry(full, key, module, call, src, builtin=f"auth:{view}"))
            return
        if target and target.startswith("allauth"):
            for route, name, action, _tpl, _fields in ALLAUTH_URLS:
                full = join_url(prefix, route)
                self.url_names.setdefault(name, full)
                out.append(UrlEntry(full, name, module, call, src, builtin=f"allauth:{action}"))
            return
        if target in {"rest_framework.urls"}:
            return
        if target is not None:
            child = self.index.find_module(target)
            if child is None:
                self.result.notes.append(f"{src}: include('{target}') moduli topilmadi")
                return
            if (child.name, prefix) in self._seen_urls:
                return
            self._seen_urls.add((child.name, prefix))
            self._walk(child, self._patterns(child), prefix, namespace, depth + 1, out)
            return
        if isinstance(arg, ast.List):
            self._walk(module, list(arg.elts), prefix, namespace, depth + 1, out)
        elif isinstance(arg, ast.Attribute) and arg.attr == "urls":
            self._router(module, arg.value, prefix)
        elif isinstance(arg, ast.Name):
            found = self.index.resolve(module, arg.id)
            if isinstance(found, PyModule):
                self._walk(found, self._patterns(found), prefix, namespace, depth + 1, out)
            elif isinstance(found, tuple) and found[1] in found[0].assigns:
                value = found[0].assigns[found[1]]
                items = list(value.elts) if isinstance(value, ast.List | ast.Tuple) else []
                self._walk(found[0], items, prefix, namespace, depth + 1, out)
        else:
            self.result.notes.append(f"{src}: include() argumenti tushunilmadi")

    # --- views ------------------------------------------------------------------

    def _resolve_view(
        self, module: PyModule, node: ast.expr, depth: int = 0
    ) -> ResolvedView | None:
        if depth > 4:
            return None
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "as_view":
                kwargs = {k.arg: k.value for k in node.keywords if k.arg}
                cls_name = dotted_name(func.value)
                found = resolve_dotted_class(self.index, module, cls_name)
                if found:
                    return ResolvedView(found[0], found[1], kwargs=kwargs)
                return ResolvedView(module, None, builtin=cls_name.split(".")[-1], kwargs=kwargs)
            if node.args:  # login_required(view) / permission_required("x")(view)
                inner = self._resolve_view(module, node.args[0], depth + 1)
                if inner is not None:
                    inner.wrappers.append(node.func if isinstance(node.func, ast.Call) else func)
                    return inner
            return None
        dotted = dotted_name(node)
        if not dotted:
            return None
        parts = dotted.split(".")
        found_any = self.index.resolve(module, parts[0])
        target_module: PyModule | None = None
        symbol = parts[-1]
        if isinstance(found_any, PyModule) and len(parts) > 1:
            target_module = found_any
        elif isinstance(found_any, tuple) and len(parts) == 1:
            target_module, symbol = found_any
        if target_module is None:
            return None
        fn = self.index.resolve_function(target_module, symbol)
        if fn is not None:
            return ResolvedView(fn[0], fn[1])
        return None

    def _emit(self, entry: UrlEntry) -> None:
        if entry.builtin == "admin":
            self.result.routes.append(
                RouteCandidate(
                    path=entry.path,
                    kind="page",
                    methods=["GET"],
                    guards=[
                        GuardInfo("role", "admin.site.urls", entry.source, ["admin"], admin=True)
                    ],
                    source=entry.source,
                )
            )
            return
        if entry.builtin:
            info = self._builtin_view(entry)
        else:
            resolved = self._resolve_view(entry.module, entry.view)
            if resolved is None:
                self.result.notes.append(
                    f"{entry.source}: view aniqlanmadi ({ast.unparse(entry.view)[:60]})"
                )
                return
            if resolved.builtin and resolved.builtin in set(AUTH_VIEWS) | AUTH_SKIPPED:
                entry.builtin = f"auth:{resolved.builtin}"
                info = self._builtin_view(entry, resolved.kwargs)
            elif isinstance(resolved.node, ast.ClassDef) and self._is_drf(resolved):
                self._drf_class(entry, resolved)
                return
            elif isinstance(resolved.node, ast.ClassDef) or resolved.builtin:
                info = self._class_view(entry, resolved)
            else:
                info = self._function_view(entry, resolved)
        if info is None:
            return
        self._add_routes(entry, info)

    def _add_routes(self, entry: UrlEntry, info: ViewInfo) -> None:
        public = info.public or any(g.expr == "login_not_required" for g in info.guards)
        guards = [g for g in info.guards if g.expr != "login_not_required"]
        if (
            self.settings.login_required_default
            and not public
            and not any(g.kind in {"auth", "role", "ownership"} for g in guards)
        ):
            guards.append(GuardInfo("auth", "LoginRequiredMiddleware", entry.source))
        component = self._component(entry, info)
        if component is not None:
            self.result.components[component.name] = component
        if "GET" in info.methods and info.renders:
            self.result.routes.append(
                RouteCandidate(
                    path=entry.path,
                    kind="page",
                    methods=["GET"],
                    guards=guards,
                    source=info.source,
                    handler=info.id,
                    component=component.name if component else None,
                )
            )
        if "GET" in info.methods and (info.read_action or not info.renders or info.downloads):
            hint = (info.entity, info.read_action) if info.entity and info.read_action else None
            self.result.routes.append(
                RouteCandidate(
                    path=entry.path,
                    kind="api",
                    methods=["GET"],
                    guards=guards,
                    source=info.source,
                    handler=info.id,
                    downloads=info.downloads,
                    entity_hint=hint,
                )
            )
        for method in info.methods:
            if method not in WRITE_METHODS:
                continue
            hint = (info.entity, info.write_action) if info.entity and info.write_action else None
            self.result.routes.append(
                RouteCandidate(
                    path=entry.path,
                    kind="api",
                    methods=[method],
                    guards=guards,
                    source=info.source,
                    handler=info.id,
                    request_model=info.request_model,
                    status_sets=list(info.status_sets),
                    status_requires=list(info.status_requires),
                    creates_user_role=info.creates_user_role if not info.guards else None,
                    entity_hint=hint,
                )
            )

    # --- built-in auth views ------------------------------------------------------

    def _builtin_view(
        self, entry: UrlEntry, kwargs: dict[str, ast.expr] | None = None
    ) -> ViewInfo | None:
        kind, _, name = (entry.builtin or "").partition(":")
        kwargs = kwargs or {}
        template_kw = self.index.string_constant(entry.module, kwargs.get("template_name"))
        if kind == "auth":
            if name in AUTH_SKIPPED:
                self.result.notes.append(
                    f"{entry.path}: Django «{name}» (havola yoki natija sahifasi) — o'tkazildi"
                )
                return None
            action, template, methods, form, guest = AUTH_VIEWS[name]
            fields = BUILTIN_FORM_FIELDS.get(form or "", [])
        else:
            spec = next(s for s in ALLAUTH_URLS if s[2] == name)
            action, template, fields = spec[2], spec[3], spec[4]
            methods = ["POST"] if action == "logout" else ["GET", "POST"]
            guest = action != "password_change"
        template = template_kw or template
        if template and template not in self.templates and "GET" in methods:
            self.result.notes.append(
                f"{entry.path}: «{template}» shabloni loyihada yo'q (kutubxona shabloni) — "
                "sahifa yo'riqnomaga olinmadi"
            )
            if action != "logout":
                return None
        guards = [] if guest else [GuardInfo("auth", f"{name}: login_required", entry.source)]
        role = None
        if action == "signup":
            role = self._signup_role()
        return ViewInfo(
            id=f"{kind}.{name}",
            source=entry.source,
            methods=methods,
            guards=guards,
            template=template,
            form_fields=[FormField(name=n, label=None, type=t, required=True) for n, t in fields],
            builtin_fields=True,
            creates_user_role=role,
            renders="GET" in methods,
            public=guest,
        )

    def _signup_role(self) -> str:
        choices, _field, default = self.models.user_roles()
        if default:
            return default
        return choices[0][0] if len(choices) == 1 else "user"

    # --- function views -----------------------------------------------------------

    def _function_view(self, entry: UrlEntry, view: ResolvedView) -> ViewInfo | None:
        func = view.node
        assert isinstance(func, ast.FunctionDef | ast.AsyncFunctionDef)
        module = view.module
        guards: list[GuardInfo] = []
        methods: list[str] | None = None
        is_api = False
        decorators = [(module, d) for d in func.decorator_list]
        decorators += [(entry.module, w) for w in view.wrappers]  # login_required(view) in urls
        for deco_module, deco in decorators:
            dguards, dmethods, api = self._decorator(deco_module, deco)
            guards += dguards
            methods = dmethods or methods
            is_api = is_api or api
        if is_api and not any(g.expr.startswith("permission_classes") for g in guards):
            guards += self._drf_perm_guards(module, self.settings.drf_permissions, entry)[1]
        handles_post = self._handles_post(func)
        methods = methods or (["GET", "POST"] if handles_post else ["GET"])
        guards += self._body_guards(module, func)
        if self._owned([func]):
            guards.append(GuardInfo("ownership", "egalik tekshiruvi", module.src(func)))
        template = self._render_template(module, func)
        form_cls = self._form_class(module, func)
        form_fields = self.models.form_fields(*form_cls) if form_cls else None
        model, read = self._read_entity(module, func)
        if model is not None and model.is_user:
            model, read = None, None
        write = _path_verb(entry.path) if model is not None and read == "view" else None
        sets, requires = self._status_logic(module, [func])
        signup = bool(form_cls and self.index.class_bases(*form_cls) & USER_CREATION_FORMS)
        returns_json = any(
            isinstance(n, ast.Call) and call_name(n).split(".")[-1] in {"JsonResponse", "Response"}
            for n in ast.walk(func)
        )
        return ViewInfo(
            id=f"{module.name}.{func.name}",
            source=module.src(func),
            methods=methods,
            guards=guards,
            template=template,
            form_fields=form_fields,
            entity=model.entity if model else None,
            read_action=read,
            write_action=write,
            status_sets=sets,
            status_requires=requires,
            creates_user_role=self._created_role(module, [func], signup),
            downloads=self._downloads(func),
            renders=template is not None and not (is_api or (returns_json and not template)),
        )

    def _decorator(
        self, module: PyModule, deco: ast.expr
    ) -> tuple[list[GuardInfo], list[str] | None, bool]:
        """(guards, methods, is DRF api_view) of one decorator."""
        name = (call_name(deco) or dotted_name(deco)).split(".")[-1]
        src = module.src(deco)
        expr = ast.unparse(deco)
        if name in METHOD_DECORATORS:
            return [], METHOD_DECORATORS[name], False
        if name == "require_http_methods" and isinstance(deco, ast.Call):
            return [], [m.upper() for m in _strings(deco.args[0] if deco.args else None)], False
        if name == "api_view" and isinstance(deco, ast.Call):
            methods = [m.upper() for m in _strings(deco.args[0] if deco.args else None)]
            return [], methods or ["GET"], True
        if name == "permission_classes" and isinstance(deco, ast.Call):
            first = deco.args[0] if deco.args else None
            elts = first.elts if isinstance(first, ast.List | ast.Tuple) else []
            write = self._drf_perm_guards(module, [dotted_name(e) for e in elts], None, src)[1]
            perm_guards = [
                GuardInfo(g.kind, f"permission_classes: {g.expr}", g.source, g.roles, g.admin)
                for g in write
            ]
            return perm_guards, None, False
        if name == "login_not_required":
            return [GuardInfo("unknown", "login_not_required", src)], None, False
        if name == "method_decorator" and isinstance(deco, ast.Call) and deco.args:
            inner = deco.args[0]
            items = list(inner.elts) if isinstance(inner, ast.List | ast.Tuple) else [inner]
            wrapped: list[GuardInfo] = []
            for item in items:
                wrapped += self._decorator(module, item)[0]
            return wrapped, None, False
        if name in AUTH_DECORATORS:
            return [GuardInfo("auth", expr, src)], None, False
        if name == "user_passes_test" and isinstance(deco, ast.Call) and deco.args:
            return self._test_guards(module, deco.args[0], expr, src), None, False
        if name == "permission_required":
            return [GuardInfo("unknown", expr, src)], None, False
        if name in IGNORED_DECORATORS:
            return [], None, False
        if any(w in name.lower() for w in ("staff", "superuser", "admin")):
            return [GuardInfo("role", expr, src, ["admin"], admin=True)], None, False
        target = deco.func if isinstance(deco, ast.Call) else deco
        found = self._resolve_function(module, target)
        args = list(deco.args) if isinstance(deco, ast.Call) else []
        if found is not None:
            guard = self._guard_function(found[0], found[1], args, module, expr, src)
            return ([guard] if guard else []), None, False
        low = name.lower()
        if any(w in low for w in ("login", "auth")):
            return [GuardInfo("auth", expr, src)], None, False
        if any(w in low for w in ("role", "perm", "group", "require", "allowed", "only")):
            return [GuardInfo("unknown", expr, src)], None, False
        return [], None, False

    def _render_template(self, module: PyModule, func: ast.AST) -> str | None:
        for node in ast.walk(func):
            if not isinstance(node, ast.Call):
                continue
            name = call_name(node).split(".")[-1]
            if name in {"render", "TemplateResponse", "render_to_response"}:
                pos = 0 if name == "render_to_response" else 1
                arg = node.args[pos] if len(node.args) > pos else kwarg(node, "template_name")
                value = self.index.string_constant(module, arg)
                if value:
                    return value
        return None

    def _form_class(self, module: PyModule, func: ast.AST) -> tuple[PyModule, ast.ClassDef] | None:
        for node in ast.walk(func):
            if not isinstance(node, ast.Call):
                continue
            name = dotted_name(node.func)
            if not name or (not name[:1].isupper() and "." not in name):
                continue
            found = resolve_dotted_class(self.index, module, name)
            if found and self.index.class_bases(*found) & {
                "Form",
                "ModelForm",
                *USER_CREATION_FORMS,
                "BaseForm",
            }:
                return found
        return None

    def _read_entity(
        self, module: PyModule, func: ast.AST
    ) -> tuple[DjangoModel | None, str | None]:
        listed: DjangoModel | None = None
        for node in ast.walk(func):
            if not isinstance(node, ast.Call):
                continue
            name = call_name(node).split(".")[-1]
            if name == "get_object_or_404" and node.args:
                model = self.models.model_of(module, node.args[0])
                if model is not None:
                    return model, "view"
            if isinstance(node.func, ast.Attribute) and ".objects" in dotted_name(node.func):
                model = self.models.model_of(module, node.func.value)
                if model is None:
                    continue
                if name == "get":
                    return model, "view"
                if name in {"filter", "all", "exclude", "order_by", "select_related"}:
                    listed = listed or model
        return (listed, "list") if listed else (None, None)

    def _created_role(self, module: PyModule, funcs: list[ast.AST], signup: bool) -> str | None:
        for func in funcs:
            for node in ast.walk(func):
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Attribute) and target.attr in ROLE_ATTRS:
                            value = enum_value(self.index, module, node.value)
                            if value is not None:
                                return value
                elif isinstance(node, ast.Call):
                    name = call_name(node).split(".")[-1]
                    if name in {"create_user", "create"}:
                        for kw in node.keywords:
                            if kw.arg in ROLE_ATTRS:
                                value = enum_value(self.index, module, kw.value)
                                if value is not None:
                                    return value
                        if name == "create_user":
                            signup = True
        return self._signup_role() if signup else None

    # --- class-based views ----------------------------------------------------------

    def _class_view(self, entry: UrlEntry, view: ResolvedView) -> ViewInfo | None:
        module = view.module
        cls = view.node if isinstance(view.node, ast.ClassDef) else None
        chain = class_chain(self.index, module, cls) if cls is not None else []
        bases = (self.index.class_bases(module, cls) | {cls.name}) if cls else set()
        if view.builtin:
            bases.add(view.builtin)
        cid = f"{module.name}.{cls.name}" if cls else f"django.{view.builtin}"
        src = module.src(cls) if cls else entry.source

        def attr(name: str) -> tuple[PyModule, ast.expr] | None:
            if name in view.kwargs:
                return entry.module, view.kwargs[name]
            return chain_attr(chain, name)

        if bases & set(AUTH_VIEWS):
            name = next(n for n in AUTH_VIEWS if n in bases)
            entry.builtin = f"auth:{name}"
            tpl = attr("template_name")
            kwargs = {"template_name": tpl[1]} if tpl else {}
            return self._builtin_view(entry, kwargs)
        generic = next((g for g in GENERIC_VIEWS if g[0] in bases), None)
        if generic and generic[0] == "RedirectView":
            return None
        guards = self._class_guards(module, cls, chain, bases, src)
        for wrapper in view.wrappers:  # login_required(View.as_view()) in urls
            guards += self._decorator(entry.module, wrapper)[0]
        methods = list(generic[2]) if generic else self._defined_methods(chain)
        allowed = attr("http_method_names")
        if allowed:
            names = [m.upper() for m in _strings(allowed[1])]
            methods = [m for m in methods if m in names] or methods
        model = self._class_model(chain, attr)
        profile = any(
            isinstance(n, ast.Return) and n.value is not None and _user_expr(n.value)
            for _m, c in chain
            for f in c.body
            if isinstance(f, ast.FunctionDef) and f.name == "get_object"
            for n in ast.walk(f)
        )
        if profile or (model is not None and model.is_user):
            model_entity = None
        else:
            model_entity = model.entity if model else None
        action = generic[1] if generic else None
        template = None
        tpl = attr("template_name")
        if tpl:
            template = self.index.string_constant(tpl[0], tpl[1])
        if template is None and generic and generic[3] and model is not None:
            template = f"{model.app_label}/{model.name.lower()}{generic[3]}.html"
        form_fields = self._class_form_fields(attr, model, action)
        funcs: list[ast.AST] = [f for _, c in chain for f in c.body if isinstance(f, FuncDef)]
        sets, requires = self._status_logic(module, funcs)
        if self._owned(funcs):
            guards.append(GuardInfo("ownership", "egalik tekshiruvi (get_queryset)", src))
        form_attr = attr("form_class")
        form_cls = (
            resolve_dotted_class(self.index, form_attr[0], dotted_name(form_attr[1]))
            if form_attr
            else None
        )
        signup = bool(form_cls and self.index.class_bases(*form_cls) & USER_CREATION_FORMS) or (
            action == "create" and model is not None and model.is_user
        )
        read = action if action in {"list", "view"} else None
        write = action if action in {"create", "update", "delete"} else None
        return ViewInfo(
            id=cid,
            source=src,
            methods=methods,
            guards=guards,
            template=template,
            form_fields=form_fields,
            entity=model_entity,
            read_action=read if model_entity else None,
            write_action=write if model_entity else None,
            status_sets=sets,
            status_requires=requires,
            creates_user_role=self._created_role(module, funcs, signup),
            downloads=any(self._downloads(f) for f in funcs),
            renders=template is not None or "GET" in methods,
        )

    def _class_guards(
        self,
        module: PyModule,
        cls: ast.ClassDef | None,
        chain: list[tuple[PyModule, ast.ClassDef]],
        bases: set[str],
        src: str,
    ) -> list[GuardInfo]:
        guards: list[GuardInfo] = []
        if "LoginRequiredMixin" in bases:
            guards.append(GuardInfo("auth", "LoginRequiredMixin", src))
        if "PermissionRequiredMixin" in bases:
            guards.append(GuardInfo("unknown", "PermissionRequiredMixin", src))
        if "GroupRequiredMixin" in bases:
            group = chain_attr(chain, "group_required")
            groups = _strings(group[1]) if group else []
            guards.append(
                self._group_guard(groups, "GroupRequiredMixin", src)
                if groups
                else GuardInfo("unknown", "GroupRequiredMixin", src)
            )
        for base in bases:
            low = base.lower()
            if ("mixin" in low or "required" in low) and any(
                w in low for w in ("staff", "superuser", "admin")
            ):
                guards.append(GuardInfo("role", base, src, ["admin"], admin=True))
        test = next(
            (
                (m, f)
                for m, c in chain
                for f in c.body
                if isinstance(f, FuncDef) and f.name == "test_func"
            ),
            None,
        )
        if test is not None:
            guards += self._test_body(test[0], test[1])
        elif "UserPassesTestMixin" in bases:
            guards.append(GuardInfo("unknown", "UserPassesTestMixin", src))
        for mod, klass in chain:
            for deco in klass.decorator_list:
                guards += self._decorator(mod, deco)[0]
            for item in klass.body:
                if isinstance(item, FuncDef) and item.name in {"dispatch", "get", "post"}:
                    for deco in item.decorator_list:
                        guards += self._decorator(mod, deco)[0]
                    guards += self._body_guards(mod, item)
        return guards

    def _test_body(self, module: PyModule, func: FuncDef) -> list[GuardInfo]:
        src = module.src(func)
        attrs = {n.attr for n in ast.walk(func) if isinstance(n, ast.Attribute)}
        if attrs & ADMIN_FLAGS:
            return [GuardInfo("role", "test_func", src, ["admin"], admin=True)]
        roles, _ = self._role_values(module, func, strict=False)
        if roles:
            return [
                GuardInfo("role", "test_func", src, roles, any(_is_admin_word(r) for r in roles))
            ]
        groups, _ = self._group_values(func)
        if groups:
            return [self._group_guard(groups, "test_func", src)]
        if self._owned([func]):
            return [GuardInfo("ownership", "test_func", src)]
        return [GuardInfo("unknown", "test_func", src)]

    @staticmethod
    def _defined_methods(chain: list[tuple[PyModule, ast.ClassDef]]) -> list[str]:
        names = {
            f.name.upper()
            for _, c in chain
            for f in c.body
            if isinstance(f, FuncDef) and f.name in {"get", "post", "put", "patch", "delete"}
        }
        ordered = [m for m in ("GET", "POST", "PUT", "PATCH", "DELETE") if m in names]
        return ordered or ["GET"]

    def _class_model(
        self, chain: list[tuple[PyModule, ast.ClassDef]], getter: AttrGetter
    ) -> DjangoModel | None:
        for name in ("model", "queryset"):
            found = getter(name)
            if found:
                model = self.models.model_of(found[0], found[1])
                if model is not None:
                    return model
        form_attr = getter("form_class")
        if form_attr:
            form_cls = resolve_dotted_class(self.index, form_attr[0], dotted_name(form_attr[1]))
            if form_cls:
                for fmod, fcls in class_chain(self.index, *form_cls):
                    meta = next(
                        (n for n in fcls.body if isinstance(n, ast.ClassDef) and n.name == "Meta"),
                        None,
                    )
                    if meta is not None:
                        for item in meta.body:
                            if (
                                isinstance(item, ast.Assign)
                                and isinstance(item.targets[0], ast.Name)
                                and item.targets[0].id == "model"
                            ):
                                return self.models.model_of(fmod, item.value)
        for mod, klass in chain:
            for item in klass.body:
                if isinstance(item, FuncDef) and item.name in {"get_queryset", "get_object"}:
                    model, _ = self._read_entity(mod, item)
                    if model is not None:
                        return model
        return None

    def _class_form_fields(
        self, getter: AttrGetter, model: DjangoModel | None, action: str | None
    ) -> list[FormField] | None:
        form_attr = getter("form_class")
        if form_attr:
            form_cls = resolve_dotted_class(self.index, form_attr[0], dotted_name(form_attr[1]))
            if form_cls:
                return self.models.form_fields(*form_cls)
        if action in {"create", "update"} and model is not None:
            fields_attr = getter("fields")
            names: list[str] = []
            if fields_attr:
                value = fields_attr[1]
                if isinstance(value, ast.Constant) and value.value == "__all__":
                    names = [n for n, f in model.fields.items() if f.editable]
                else:
                    names = _strings(value)
            return [model.fields[n].form_field() for n in names if n in model.fields]
        return None

    # --- Django REST framework ------------------------------------------------------

    def _is_drf(self, view: ResolvedView) -> bool:
        if not isinstance(view.node, ast.ClassDef):
            return False
        bases = self.index.class_bases(view.module, view.node)
        return bool(bases & (DRF_API_BASES | set(DRF_VIEWSETS)))

    def _drf_class(self, entry: UrlEntry, view: ResolvedView) -> None:
        cls = view.node
        assert isinstance(cls, ast.ClassDef)
        module = view.module
        chain = class_chain(self.index, module, cls)
        bases = self.index.class_bases(module, cls)
        read, write = self._drf_guards(module, chain, entry)
        model = self._drf_model(chain)
        serializer = self._serializer(chain)
        funcs: list[ast.AST] = [f for _, c in chain for f in c.body if isinstance(f, FuncDef)]
        owned = self._owned(funcs)
        generic = next((DRF_GENERICS[b] for b in DRF_GENERICS if b in bases), None)
        if generic is None:
            methods = {m: "" for m in self._defined_methods(chain)}
        else:
            methods = dict(generic)
        sets, requires = self._status_logic(module, funcs)
        for method, action in methods.items():
            guards = list(read if method == "GET" else write)
            if owned:
                guards.append(GuardInfo("ownership", "get_queryset", module.src(cls)))
            self.result.routes.append(
                RouteCandidate(
                    path=entry.path,
                    kind="api",
                    methods=[method],
                    guards=guards,
                    source=module.src(cls),
                    handler=f"{cls.name}.{method.lower()}",
                    request_model=serializer if method in WRITE_METHODS else None,
                    status_sets=sets if method in WRITE_METHODS else [],
                    status_requires=requires if method in WRITE_METHODS else [],
                    entity_hint=(model.entity, action) if model and action else None,
                )
            )

    def _router(self, module: PyModule, router: ast.expr, prefix: str) -> None:
        name = dotted_name(router)
        found = self.index.resolve_assign(module, name.split(".")[0]) if name else None
        homes = [module] + ([found[0]] if found and found[0] is not module else [])
        registered = False
        for home in homes:
            for node in ast.walk(home.tree):
                if not (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "register"
                    and dotted_name(node.func.value) == name
                    and len(node.args) >= 2
                ):
                    continue
                reg = self.index.string_constant(home, node.args[0])
                if reg is None:
                    continue
                registered = True
                self._viewset(home, node.args[1], join_url(prefix, reg.strip("^$") + "/"))
        if not registered:
            self.result.notes.append(f"{module.rel}: DRF router «{name}» ro'yxatlari topilmadi")

    def _viewset(self, module: PyModule, node: ast.expr, base: str) -> None:
        found = resolve_dotted_class(self.index, module, dotted_name(node))
        if found is None:
            self.result.notes.append(f"{module.rel}: ViewSet «{ast.unparse(node)}» topilmadi")
            return
        vmod, cls = found
        chain = class_chain(self.index, vmod, cls)
        bases = self.index.class_bases(vmod, cls) | {cls.name}
        actions: list[str] = []
        for vs, acts in DRF_VIEWSETS.items():
            if vs in bases:
                actions += acts
        for mixin, acts in DRF_MIXINS.items():
            if mixin in bases:
                actions += acts
        defined = {f.name: f for _, c in chain for f in c.body if isinstance(f, FuncDef)}
        actions += [a for a in VIEWSET_ACTIONS if a in defined]
        actions = list(dict.fromkeys(actions))
        lookup = "pk"
        for key in ("lookup_url_kwarg", "lookup_field"):
            value = chain_attr(chain, key)
            if value and isinstance(value[1], ast.Constant) and isinstance(value[1].value, str):
                lookup = value[1].value
                break
        entry = UrlEntry(base, None, vmod, node, vmod.src(cls))
        read, write = self._drf_guards(vmod, chain, entry)
        model = self._drf_model(chain)
        serializer = self._serializer(chain)
        funcs: list[ast.AST] = list(defined.values())
        owned = self._owned(funcs)
        for action in actions:
            method, detail, ent_action = VIEWSET_ACTIONS[action]
            path = base + (f":{lookup}/" if detail else "")
            hooks: list[ast.AST] = [
                defined[n] for n in (action, PERFORM_HOOKS.get(action, "")) if n in defined
            ]
            sets, requires = self._status_logic(vmod, hooks)
            self._drf_route(
                path,
                method,
                read,
                write,
                owned,
                vmod,
                cls,
                action,
                serializer,
                sets,
                requires,
                (model.entity, ent_action) if model else None,
            )
        for fname, func in defined.items():
            deco = next(
                (d for d in func.decorator_list if call_name(d).split(".")[-1] == "action"), None
            )
            if not isinstance(deco, ast.Call):
                continue
            detail_node = kwarg(deco, "detail")
            detail = isinstance(detail_node, ast.Constant) and detail_node.value is True
            url_path = self.index.string_constant(vmod, kwarg(deco, "url_path")) or fname
            methods = [m.upper() for m in _strings(kwarg(deco, "methods"))] or ["GET"]
            path = base + (f":{lookup}/" if detail else "") + url_path.strip("/") + "/"
            sets, requires = self._status_logic(vmod, [func])
            perm_node = kwarg(deco, "permission_classes")
            a_read, a_write = (
                self._drf_perm_guards(vmod, [dotted_name(e) for e in perm_node.elts], entry)
                if isinstance(perm_node, ast.List | ast.Tuple)
                else (read, write)
            )
            downloads = self._downloads(func)
            for method in methods:
                hint = None
                if model is not None and (method != "GET" or downloads):
                    verb = fname if method != "GET" else f"download_{fname}"
                    hint = (model.entity, verb)
                self._drf_route(
                    path,
                    method,
                    a_read,
                    a_write,
                    owned,
                    vmod,
                    cls,
                    fname,
                    serializer,
                    sets,
                    requires,
                    hint,
                    downloads,
                )

    def _drf_route(
        self,
        path: str,
        method: str,
        read: list[GuardInfo],
        write: list[GuardInfo],
        owned: bool,
        module: PyModule,
        cls: ast.ClassDef,
        handler: str,
        serializer: str | None,
        sets: list[tuple[str, str]],
        requires: list[str],
        hint: tuple[str, str] | None,
        downloads: bool = False,
    ) -> None:
        guards = list(read if method == "GET" else write)
        if owned:
            guards.append(GuardInfo("ownership", "get_queryset", module.src(cls)))
        self.result.routes.append(
            RouteCandidate(
                path=path,
                kind="api",
                methods=[method],
                guards=guards,
                source=module.src(cls),
                handler=f"{cls.name}.{handler}",
                request_model=serializer if method in WRITE_METHODS else None,
                status_sets=sets,
                status_requires=requires,
                downloads=downloads,
                entity_hint=hint,
            )
        )

    def _drf_guards(
        self, module: PyModule, chain: list[tuple[PyModule, ast.ClassDef]], entry: UrlEntry
    ) -> tuple[list[GuardInfo], list[GuardInfo]]:
        if any(
            isinstance(f, FuncDef) and f.name == "get_permissions" for _, c in chain for f in c.body
        ):
            unknown = [GuardInfo("unknown", "get_permissions()", entry.source)]
            return unknown, unknown
        perms = chain_attr(chain, "permission_classes")
        names = (
            [dotted_name(e) for e in perms[1].elts]
            if perms and isinstance(perms[1], ast.List | ast.Tuple)
            else list(self.settings.drf_permissions)
        )
        pmod = perms[0] if perms else module
        return self._drf_perm_guards(pmod, names, entry)

    def _drf_perm_guards(
        self, module: PyModule, names: list[str], entry: UrlEntry | None, src: str | None = None
    ) -> tuple[list[GuardInfo], list[GuardInfo]]:
        src = src or (entry.source if entry else module.rel)
        read: list[GuardInfo] = []
        write: list[GuardInfo] = []
        for full in names:
            name = full.split(".")[-1]
            kind = DRF_PERMS.get(name)
            if kind == "":
                continue
            if kind == "auth":
                read.append(GuardInfo("auth", name, src))
                write.append(GuardInfo("auth", name, src))
            elif kind == "auth_write":
                write.append(GuardInfo("auth", name, src))
            elif kind == "admin":
                guard = GuardInfo("role", name, src, ["admin"], admin=True)
                read.append(guard)
                write.append(guard)
            elif kind == "unknown":
                read.append(GuardInfo("unknown", name, src))
                write.append(GuardInfo("unknown", name, src))
            else:
                guards = self._custom_permission(module, full, src)
                read += guards
                write += guards
        return read, write

    def _custom_permission(self, module: PyModule, name: str, src: str) -> list[GuardInfo]:
        found = resolve_dotted_class(self.index, module, name)
        if found is None:
            return [GuardInfo("unknown", name, src)]
        pmod, cls = found
        methods = [
            f
            for f in cls.body
            if isinstance(f, FuncDef) and f.name in {"has_permission", "has_object_permission"}
        ]
        guards: list[GuardInfo] = []
        for func in methods:
            attrs = {n.attr for n in ast.walk(func) if isinstance(n, ast.Attribute)}
            if attrs & ADMIN_FLAGS:
                return [GuardInfo("role", name, pmod.src(cls), ["admin"], admin=True)]
            roles, _ = self._role_values(pmod, func, strict=False)
            if roles:
                guards.append(
                    GuardInfo(
                        "role", name, pmod.src(cls), roles, any(_is_admin_word(r) for r in roles)
                    )
                )
            elif self._owned([func]):
                guards.append(GuardInfo("ownership", name, pmod.src(cls)))
            elif "is_authenticated" in attrs:
                guards.append(GuardInfo("auth", name, pmod.src(cls)))
        return guards or [GuardInfo("unknown", name, pmod.src(cls))]

    def _drf_model(self, chain: list[tuple[PyModule, ast.ClassDef]]) -> DjangoModel | None:
        qs = chain_attr(chain, "queryset")
        if qs:
            model = self.models.model_of(qs[0], qs[1])
            if model is not None:
                return model
        ser = chain_attr(chain, "serializer_class")
        if ser:
            found = resolve_dotted_class(self.index, ser[0], dotted_name(ser[1]))
            if found:
                for fmod, fcls in class_chain(self.index, *found):
                    meta = next(
                        (n for n in fcls.body if isinstance(n, ast.ClassDef) and n.name == "Meta"),
                        None,
                    )
                    if meta is None:
                        continue
                    for item in meta.body:
                        if (
                            isinstance(item, ast.Assign)
                            and isinstance(item.targets[0], ast.Name)
                            and item.targets[0].id == "model"
                        ):
                            return self.models.model_of(fmod, item.value)
        for mod, klass in chain:
            for item in klass.body:
                if isinstance(item, FuncDef) and item.name == "get_queryset":
                    model, _ = self._read_entity(mod, item)
                    if model is not None:
                        return model
        return None

    def _serializer(self, chain: list[tuple[PyModule, ast.ClassDef]]) -> str | None:
        ser = chain_attr(chain, "serializer_class")
        if not ser:
            return None
        found = resolve_dotted_class(self.index, ser[0], dotted_name(ser[1]))
        if found is None:
            return None
        name = found[1].name
        if name not in self.result.request_models:
            self.result.request_models[name] = self.models.serializer_fields(*found)
        return name

    # --- components (templates) -------------------------------------------------------

    def _href(self, href: str) -> str | None:
        if href.startswith(URL_MARK):
            name = href[len(URL_MARK) :]
            return self.url_names.get(name)
        if href.startswith("/") and not href.startswith("//"):
            return href.split("?")[0].split("#")[0] or None
        return None

    def _component(self, entry: UrlEntry, info: ViewInfo) -> ComponentInfo | None:
        parsed = self._template(info.template)
        if parsed is None and not info.read_action:
            if info.template and "GET" in info.methods and info.renders:
                self.result.notes.append(
                    f"{entry.path}: «{info.template}» shabloni topilmadi — formalar o'qilmadi"
                )
            return None
        name = info.id if info.id not in self.result.components else f"{info.id}@{entry.path}"
        component = ComponentInfo(name=name, file=parsed[1] if parsed else info.source)
        if info.read_action:
            component.loads.append(f"GET {entry.path}")
        if parsed is None:
            return component
        tinfo, rel = parsed
        self._fill_component(component, tinfo, rel, entry.path, info)
        return component

    def _fill_component(
        self,
        component: ComponentInfo,
        tinfo: TemplateInfo,
        rel: str,
        page_path: str | None,
        info: ViewInfo | None,
    ) -> None:
        for i, tform in enumerate(tinfo.forms, start=1):
            method = tform.method_override or tform.method
            if method == "GET":
                continue
            action = self._href(tform.action) if tform.action else page_path
            if action is None:
                self.result.notes.append(f"{rel}:{tform.line}: forma manzili aniqlanmadi")
                continue
            fields = self._form_fields(tform, info)
            src = f"{rel}:{tform.line}"
            opener = tinfo.openers.get(tform.modal) if tform.modal else None
            submit = tform.submit or (info.submit_label if info and info.submit_label else "")
            if fields:
                form = Form(
                    id=re.sub(r"[^a-z0-9]+", "_", snake(component.name)).strip("_") + f"_form{i}",
                    page_path=page_path or action,
                    fields=fields,
                    submit=Target(role="button", name=submit)
                    if submit
                    else Target(css="form [type=submit]"),
                    api=f"{method} {action}",
                )
                component.forms.append(form)
                component.actions.append(
                    ActionBinding(
                        component=component.name,
                        kind="form",
                        api_method=method,
                        api_path=action,
                        trigger=submit,
                        source=src,
                        opener=opener,
                        in_modal=tform.modal is not None,
                        form_id=form.id,
                    )
                )
            elif submit:
                component.actions.append(
                    ActionBinding(
                        component=component.name,
                        kind="button",
                        api_method=method,
                        api_path=action,
                        trigger=submit,
                        source=src,
                        opener=opener,
                        in_modal=tform.modal is not None,
                    )
                )
            else:
                self.result.notes.append(f"{src}: tugma nomi yo'q forma o'tkazildi")
        for href, text in tinfo.links:
            path = self._href(href)
            if path is not None:
                component.links.append(LinkInfo(component.name, text, path, rel))

    @staticmethod
    def _form_fields(tform: TForm, info: ViewInfo | None) -> list[FormField]:
        by_name = {f.name: f for f in (info.form_fields or [])} if info else {}
        explicit: list[FormField] = []
        for f in tform.fields:
            if not f.type:  # {{ form.email() }} placeholder: the form class knows the field
                if f.name in by_name:
                    explicit.append(by_name[f.name])
                continue
            explicit.append(
                FormField(
                    name=f.name,
                    label=f.label or None,
                    type=f.type,
                    required=f.required,
                    rules="|".join(f.rules) or None,
                    options=f.options or None,
                )
            )
        if any(not f.type for f in tform.fields):
            return explicit
        if tform.renders_form_object and info is not None and info.form_fields:
            names = {f.name for f in explicit}
            return [*explicit, *(f for f in info.form_fields if f.name not in names)]
        if not explicit and info is not None and info.builtin_fields and info.form_fields:
            return list(info.form_fields)
        return explicit

    def _emit_layouts(self) -> None:
        for name in sorted(self.layouts):
            parsed = self._template(name)
            if parsed is None:
                continue
            tinfo, rel = parsed
            component = ComponentInfo(name=f"layout:{name}", file=rel)
            self._fill_component(component, tinfo, rel, None, None)
            self.result.components[component.name] = component
            for link in component.links:
                self.result.nav.append(NavItem(link.label, link.to, rel))

    # --- roles ----------------------------------------------------------------------

    def _collect_roles(self) -> None:
        choices, _field, _default = self.models.user_roles()
        source = self.models.role_source()
        for value, label in choices:
            self.result.role_values.setdefault(value, source)
            self.result.role_labels.setdefault(value, label)
        for gid, group in self._group_roles.items():
            self.result.role_values.setdefault(gid, "django.contrib.auth.models.Group")
            self.result.role_labels.setdefault(gid, group)
        signup = {r.creates_user_role for r in self.result.routes if r.creates_user_role}
        authed = any(g.kind in {"auth", "ownership"} for r in self.result.routes for g in r.guards)
        if not choices and not self._group_roles and (authed or signup):
            self.result.role_values.setdefault("user", "django.contrib.auth (kirgan foydalanuvchi)")
        for role in signup:
            self.result.role_values.setdefault(role, source)
