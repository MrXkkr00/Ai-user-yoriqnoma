"""Laravel: routes, middleware, controllers, migrations and Blade views (TZ FR-S3/S4, T29).

PHP is read as text with a small bracket-aware tokenizer (no PHP runtime, nothing run).
``routes/web.php`` and ``routes/api.php`` (prefix ``/api``) give routes, including
``Route::resource`` / ``apiResource``, and groups built with ``middleware()``, ``prefix()``,
``name()`` and ``group()``. Middleware gives guards: ``auth`` / ``auth:sanctum``, Spatie
``role:manager|courier``, admin aliases; ``can:`` and ``permission:`` stay unknown
(default-deny). Controllers give pages (``view()``), status changes, preconditions
(``abort_if``) and owner checks. Migrations give entities, status enums and the users'
role column. Blade views give forms (``@method``, ``route()``), links and the navigation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from yoriqnoma_scanner.detect import ProjectInfo
from yoriqnoma_scanner.fs_guard import SafeFS
from yoriqnoma_scanner.parsers.base import (
    SIGNUP_DEFAULT,
    ActionBinding,
    ComponentInfo,
    EntityCandidate,
    GuardInfo,
    LinkInfo,
    NavItem,
    ParseResult,
    RouteCandidate,
)
from yoriqnoma_scanner.parsers.html_forms import URL_MARK, TemplateInfo, parse_template
from yoriqnoma_scanner.parsers.sqlalchemy_models import is_pii_name, singular
from yoriqnoma_schemas import Form, FormField, Target

VERBS = {"get", "post", "put", "patch", "delete", "options", "any"}
ROUTE_CALLS = {"match", "view", "resource", "apiResource", "resources", "redirect"}
AUTH_MIDDLEWARE = {"auth", "auth.basic", "auth.session", "verified", "password.confirm"}
IGNORED_MIDDLEWARE = {
    "web",
    "api",
    "guest",
    "throttle",
    "signed",
    "bindings",
    "cache.headers",
    "csrf",
    "localization",
    "locale",
    "setlocale",
}
ADMIN_WORDS = ("admin", "superadmin", "superuser", "staff", "root")
RESOURCE = [  # action, method, suffix, entity action
    ("index", "GET", "", "list"),
    ("create", "GET", "/create", None),
    ("store", "POST", "", "create"),
    ("show", "GET", "/{%s}", "view"),
    ("edit", "GET", "/{%s}/edit", None),
    ("update", "PUT", "/{%s}", "update"),
    ("update", "PATCH", "/{%s}", "update"),
    ("destroy", "DELETE", "/{%s}", "delete"),
]
_STRING = re.compile(r"""^\s*(['"])(.*)\1\s*$""", re.S)


def _admin(text: str) -> bool:
    return any(w in text.lower() for w in ADMIN_WORDS)


def laravel_path(uri: str) -> str:
    """``orders/{order}/pay`` -> ``/orders/:order/pay``."""
    path = re.sub(r"\{(\w+)\??\}", r":\1", uri.strip())
    return "/" + path.strip("/")


def join(*parts: str) -> str:
    joined = "/".join(p.strip("/") for p in parts if p and p.strip("/"))
    return "/" + joined


def strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"(?m)^\s*(//|#).*$", "", text)


def split_top(text: str, sep: str) -> list[str]:
    """Split on ``sep`` outside brackets and strings."""
    parts: list[str] = []
    depth = 0
    quote: str | None = None
    start = 0
    i = 0
    while i < len(text):
        ch = text[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in "'\"":
            quote = ch
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif depth == 0 and text.startswith(sep, i):
            parts.append(text[start:i])
            start = i + len(sep)
            i += len(sep)
            continue
        i += 1
    parts.append(text[start:])
    return [p for p in parts if p.strip()]


def calls(chain: str) -> list[tuple[str, str]]:
    """``Route::middleware('auth')->prefix('x')`` -> [("middleware", "'auth'"), ...]."""
    out: list[tuple[str, str]] = []
    for part in re.split(r"::", chain, maxsplit=1)[-1:]:
        for seg in split_top(part, "->"):
            match = re.match(r"\s*(\w+)\s*\((.*)\)\s*$", seg, re.S)
            if match:
                out.append((match.group(1), match.group(2)))
    return out


def string(arg: str) -> str | None:
    match = _STRING.match(arg)
    return match.group(2) if match else None


def strings(arg: str) -> list[str]:
    return re.findall(r"""['"]([^'"]*)['"]""", arg)


def closure_body(arg: str) -> str | None:
    """Body of ``function () { ... }`` / ``fn() => ...`` passed as an argument."""
    start = arg.find("{")
    if "function" not in arg or start < 0:
        return None
    depth = 0
    for i in range(start, len(arg)):
        if arg[i] == "{":
            depth += 1
        elif arg[i] == "}":
            depth -= 1
            if depth == 0:
                return arg[start + 1 : i]
    return None


@dataclass
class Group:
    prefix: str = ""
    name: str = ""
    middleware: list[str] = field(default_factory=list)
    controller: str | None = None


@dataclass
class Action:
    controller: str | None
    method: str | None
    inline: str | None = None  # closure body


class LaravelParser:
    name = "laravel"

    def __init__(self, i18n: dict[str, str] | None = None) -> None:
        self.i18n = i18n or {}

    def applies(self, project: ProjectInfo) -> bool:
        return "laravel" in project.stacks

    def parse(self, project: ProjectInfo, fs: SafeFS) -> ParseResult:
        self.fs = fs
        self.result = ParseResult()
        self.php = {fs.rel(p): p for p in project.php_files}
        self.views = {
            rel.split("views/", 1)[1].removesuffix(".blade.php").replace("/", "."): rel
            for rel in self.php
            if rel.endswith(".blade.php") and "views/" in rel
        }
        self.aliases = self._middleware_aliases()
        self.enums = self._php_enums()
        self.url_names: dict[str, str] = {}
        self.layouts: set[str] = set()
        self._migrations()
        pending: list[tuple[str, str, Action, Group, str]] = []
        for rel in sorted(self.php):
            parts = PurePosixPath(rel).parts
            if len(parts) < 2 or parts[-2] != "routes" or rel.endswith(".blade.php"):
                continue
            if parts[-1] in {"console.php", "channels.php"}:
                continue
            text = strip_comments(self._read(rel))
            group = Group(prefix="api" if parts[-1] == "api.php" else "")
            self._statements(text, group, rel, pending)
        for method, path, action, group, src in pending:
            self._route(method, path, action, group, src)
        self._emit_layouts()
        return self.result

    def _read(self, rel: str) -> str:
        path = self.php.get(rel)
        return (self.fs.read_text(path) or "") if path is not None else ""

    def translate(self, text: str) -> str:
        return self.i18n.get(text, text)

    # --- routes ------------------------------------------------------------------------

    def _statements(
        self, text: str, group: Group, rel: str, out: list[tuple[str, str, Action, Group, str]]
    ) -> None:
        for statement in split_top(text, ";"):
            stmt = statement.strip()
            idx = stmt.find("Route::")
            if idx < 0:
                continue
            stmt = stmt[idx:]
            line_no = text[: text.find(statement)].count("\n") + 1
            src = f"{rel}:{line_no}"
            chain = calls(stmt)
            if not chain:
                continue
            g = Group(group.prefix, group.name, list(group.middleware), group.controller)
            body: str | None = None
            routes: list[tuple[str, list[str]]] = []  # (call name, args)
            for name, args in chain:
                parts = split_top(args, ",")
                if routes or name in VERBS | ROUTE_CALLS:
                    routes.append((name, parts))  # the route and its own ->name()/->middleware()
                elif name == "prefix" and parts:
                    g.prefix = join(g.prefix, string(parts[0]) or "")
                elif name in {"name", "as"} and parts:
                    g.name += string(parts[0]) or ""
                elif name == "middleware" and parts:
                    g.middleware += [m for p in parts for m in strings(p)]
                elif name == "controller" and parts:
                    g.controller = parts[0].split("::")[0].strip().split("\\")[-1]
                elif name == "group":
                    if parts and parts[0].strip().startswith("["):
                        self._group_array(parts[0], g)
                    body = closure_body(parts[-1]) if parts else None
                elif name in {"withoutMiddleware"} and parts:
                    removed = {m for p in parts for m in strings(p)}
                    g.middleware = [m for m in g.middleware if m not in removed]
                # other group modifiers (domain, scopeBindings...) do not change paths or guards
            if body is not None:
                self._statements(body, g, rel, out)
                continue
            self._route_calls(routes, g, src, out)

    @staticmethod
    def _group_array(arg: str, g: Group) -> None:
        for key, value in re.findall(r"""['"](\w+)['"]\s*=>\s*(\[[^\]]*\]|['"][^'"]*['"])""", arg):
            values = strings(value)
            if key == "prefix" and values:
                g.prefix = join(g.prefix, values[0])
            elif key in {"middleware"}:
                g.middleware += values
            elif key in {"as", "name"} and values:
                g.name += values[0]

    def _route_calls(
        self,
        routes: list[tuple[str, list[str]]],
        g: Group,
        src: str,
        out: list[tuple[str, str, Action, Group, str]],
    ) -> None:
        if not routes:
            return
        verb, args = routes[0]
        modifiers = routes[1:]
        route_name: str | None = None
        for name, margs in modifiers:
            if name == "middleware":
                g.middleware += [m for p in margs for m in strings(p)]
            elif name == "name" and margs:
                route_name = string(margs[0])
        if verb in VERBS or verb == "match":
            if verb == "match":
                methods = [m.upper() for m in strings(args[0])] if args else []
                args = args[1:]
            else:
                methods = ["GET"] if verb == "any" else [verb.upper()]
            if not args:
                return
            uri = string(args[0])
            if uri is None:
                return
            action = self._action(args[1] if len(args) > 1 else "", g)
            path = join(g.prefix, laravel_path(uri))
            if route_name:
                self.url_names[g.name + route_name] = path
            for method in methods:
                out.append((method, path, action, g, src))
        elif verb == "view" and len(args) >= 2:
            uri, view = string(args[0]), string(args[1])
            if uri is not None and view:
                path = join(g.prefix, laravel_path(uri))
                if route_name:
                    self.url_names[g.name + route_name] = path
                out.append(("GET", path, Action(None, None, f"return view('{view}');"), g, src))
        elif verb in {"resource", "apiResource", "resources"} and len(args) >= 2:
            self._resource(verb, args, modifiers, g, src, out)

    def _resource(
        self,
        verb: str,
        args: list[str],
        modifiers: list[tuple[str, list[str]]],
        g: Group,
        src: str,
        out: list[tuple[str, str, Action, Group, str]],
    ) -> None:
        uri = string(args[0]) or ""
        controller = args[1].split("::")[0].strip().split("\\")[-1]
        only: set[str] | None = None
        except_: set[str] = set()
        for name, margs in modifiers:
            if name == "only":
                only = {s for a in margs for s in strings(a)}
            elif name == "except":
                except_ = {s for a in margs for s in strings(a)}
        last = uri.split(".")[-1].split("/")[-1]
        param = singular(last.replace("-", "_"))
        base = join(g.prefix, laravel_path(uri.replace(".", "/")))
        for action, method, suffix, _entity_action in RESOURCE:
            if verb == "apiResource" and action in {"create", "edit"}:
                continue
            if (only is not None and action not in only) or action in except_:
                continue
            path = base + laravel_path(suffix % param if "%s" in suffix else suffix).rstrip("/")
            path = path if path != "" else "/"
            self.url_names.setdefault(f"{g.name}{uri}.{action}", path)
            out.append((method, path, Action(controller, action), g, src))

    def _action(self, arg: str, g: Group) -> Action:
        arg = arg.strip()
        match = re.match(r"\[\s*([\w\\]+)::class\s*,\s*['\"](\w+)['\"]\s*\]", arg)
        if match:
            return Action(match.group(1).split("\\")[-1], match.group(2))
        match = re.match(r"['\"]([\w\\]+)@(\w+)['\"]", arg)
        if match:
            return Action(match.group(1).split("\\")[-1], match.group(2))
        match = re.match(r"([\w\\]+)::class$", arg)
        if match:
            return Action(match.group(1).split("\\")[-1], "__invoke")
        method = string(arg)
        if method and g.controller:  # Route::controller(X::class)->group(...get('/', 'index'))
            return Action(g.controller, method)
        return Action(None, None, closure_body(arg) or arg)

    # --- one route ------------------------------------------------------------------------

    def _route(self, method: str, path: str, action: Action, g: Group, src: str) -> None:
        guards = [guard for m in g.middleware if (guard := self._middleware_guard(m, src))]
        body = action.inline or ""
        entity: str | None = None
        resource_action: str | None = None
        if action.controller:
            ctrl = self._controller(action.controller)
            if ctrl is not None:
                ctext, crel = ctrl
                body = _method_body(ctext, action.method or "") or ""
                for mw in re.findall(r"\$this->middleware\(\s*([^)]*)\)", ctext):
                    guards += [x for m in strings(mw) if (x := self._middleware_guard(m, crel))]
            entity = (
                singular(
                    re.sub(
                        r"(?<!^)(?=[A-Z])", "_", action.controller.removesuffix("Controller")
                    ).lower()
                )
                or None
            )
            resource_action = {a: e for a, _m, _s, e in RESOURCE}.get(action.method or "")
        guards += self._body_guards(body, src)
        if _owned(body):
            guards.append(GuardInfo("ownership", "egalik tekshiruvi", src))
        view = _view(body)
        sets, requires = self._status_logic(body)
        known_entity = entity if entity in self._entities else None
        if method == "GET" and view is not None:
            component = self._view_component(view, path, src)
            self.result.routes.append(
                RouteCandidate(path, "page", ["GET"], guards, src, action.method, component)
            )
            if known_entity and resource_action in {"list", "view"}:
                self.result.routes.append(
                    RouteCandidate(
                        path,
                        "api",
                        ["GET"],
                        guards,
                        src,
                        action.method,
                        entity_hint=(known_entity, resource_action),
                    )
                )
                comp = self.result.components.get(component or "")
                if comp is not None:
                    comp.loads.append(f"GET {path}")
            return
        created = None
        if re.search(r"\bUser::(create|forceCreate)\(|new User\b", body):
            role = re.search(r"['\"]role['\"]\s*=>\s*['\"](\w+)['\"]", body)
            created = role.group(1) if role else SIGNUP_DEFAULT
        hint = (known_entity, resource_action) if known_entity and resource_action else None
        self.result.routes.append(
            RouteCandidate(
                path=path,
                kind="api",
                methods=[method],
                guards=guards,
                source=src,
                handler=action.method,
                status_sets=sets,
                status_requires=requires,
                downloads=bool(re.search(r"->download\(|Storage::download\(", body)),
                creates_user_role=created if not guards else None,
                entity_hint=hint,
            )
        )

    def _controller(self, name: str) -> tuple[str, str] | None:
        for rel in self.php:
            if rel.endswith(f"/{name}.php") and "Controllers" in rel:
                return strip_comments(self._read(rel)), rel
        return None

    # --- guards --------------------------------------------------------------------------

    def _middleware_aliases(self) -> dict[str, str]:
        """Alias -> middleware class name (app/Http/Kernel.php or bootstrap/app.php)."""
        out: dict[str, str] = {}
        for rel in self.php:
            if not rel.endswith(("Http/Kernel.php", "bootstrap/app.php")):
                continue
            for alias, cls in re.findall(
                r"""['"]([\w.-]+)['"]\s*=>\s*\\?([\w\\]+)::class""", self._read(rel)
            ):
                out[alias] = cls.split("\\")[-1]
        return out

    def _middleware_guard(self, spec: str, src: str) -> GuardInfo | None:
        name, _, params = spec.partition(":")
        values = [v for v in re.split(r"[|,]", params) if v]
        if name in AUTH_MIDDLEWARE:
            return GuardInfo("auth", spec, src)
        if name in IGNORED_MIDDLEWARE:
            return None
        if name in {"role", "roles", "role_or_permission"} and values:
            return GuardInfo("role", spec, src, values, admin=any(_admin(v) for v in values))
        if name in {"can", "permission", "ability", "abilities"}:
            return GuardInfo("unknown", spec, src)
        if _admin(name):
            return GuardInfo("role", spec, src, ["admin"], admin=True)
        cls = self.aliases.get(name)
        if cls is not None:
            for rel in self.php:
                if rel.endswith(f"/{cls}.php"):
                    text = self._read(rel)
                    if re.search(r"is_?admin|isSuperAdmin|hasRole\(\s*['\"]admin", text, re.I):
                        return GuardInfo("role", spec, src, ["admin"], admin=True)
                    roles = re.findall(r"->role\s*[!=]==?\s*['\"](\w+)['\"]", text)
                    if roles or values:
                        found = roles or values
                        return GuardInfo("role", spec, src, found, any(_admin(r) for r in found))
                    if re.search(r"auth\(\)->check\(\)|Auth::check\(\)", text):
                        return GuardInfo("auth", spec, src)
        return GuardInfo("unknown", spec, src)

    @staticmethod
    def _body_guards(body: str, src: str) -> list[GuardInfo]:
        guards: list[GuardInfo] = []
        if re.search(r"(->|::)(is_admin|isAdmin\(\))", body) and re.search(
            r"abort|403|redirect", body
        ):
            guards.append(GuardInfo("role", "is_admin", src, ["admin"], admin=True))
        for cond in re.findall(r"abort_(?:if|unless)\s*\(([^;]*?),\s*40[13]", body):
            roles = re.findall(r"->role\s*[!=]==?\s*['\"](\w+)['\"]", cond) + re.findall(
                r"hasRole\(\s*['\"](\w+)['\"]", cond
            )
            if roles:
                guards.append(
                    GuardInfo("role", cond.strip()[:80], src, roles, any(_admin(r) for r in roles))
                )
        for roles_text in re.findall(
            r"if\s*\(([^)]*->role\s*!==?\s*['\"]\w+['\"][^)]*)\)\s*\{?\s*(?:abort|return\s+redirect)",
            body,
        ):
            roles = re.findall(r"['\"](\w+)['\"]", roles_text)
            guards.append(
                GuardInfo("role", roles_text[:80], src, roles, any(_admin(r) for r in roles))
            )
        return guards

    def _status_logic(self, body: str) -> tuple[list[tuple[str, str]], list[str]]:
        def value(token: str) -> str | None:
            token = token.strip()
            plain = string(token)
            if plain is not None:
                return plain
            match = re.match(r"(\w+)::(\w+)(->value)?$", token)
            if match and match.group(1) in self.enums:
                return self.enums[match.group(1)].get(match.group(2))
            return None

        sets: list[tuple[str, str]] = []
        for token in re.findall(r"->(?:status|state)\s*=\s*([^;]+);", body):
            v = value(token)
            if v:
                sets.append(("status", v))
        for token in re.findall(r"""['"](?:status|state)['"]\s*=>\s*([^,\]\n]+)""", body):
            v = value(token)
            if v and not re.search(r"where\s*\(\s*\[?[^;]*" + re.escape(token.strip()), body):
                sets.append(("status", v))
        requires: list[str] = []
        for cond in re.findall(r"abort_if\s*\(([^;]*?),\s*4\d\d", body) + re.findall(
            r"if\s*\(([^)]*)\)\s*\{?\s*(?:abort|return\s+(?:back|redirect|response))", body
        ):
            for token in re.findall(r"->(?:status|state)\s*!==?\s*([^&|)]+)", cond):
                v = value(token)
                if v:
                    requires.append(v)
        for cond in re.findall(r"abort_unless\s*\(([^;]*?),\s*4\d\d", body):
            for token in re.findall(r"->(?:status|state)\s*===?\s*([^&|)]+)", cond):
                v = value(token)
                if v:
                    requires.append(v)
        return list(dict.fromkeys(sets)), list(dict.fromkeys(requires))

    # --- models -------------------------------------------------------------------------

    def _php_enums(self) -> dict[str, dict[str, str]]:
        out: dict[str, dict[str, str]] = {}
        for rel in self.php:
            text = self._read(rel) if "/Enums/" in rel or rel.endswith("Status.php") else ""
            for name, body in re.findall(r"enum\s+(\w+)\s*:\s*string[^{]*\{(.*?)\}", text, re.S):
                out[name] = dict(re.findall(r"case\s+(\w+)\s*=\s*['\"]([\w-]+)['\"]", body))
        return out

    def _migrations(self) -> None:
        self._entities: set[str] = set()
        for rel in sorted(self.php):
            if "migrations/" not in rel:
                continue
            text = self._read(rel)
            for table, body in re.findall(
                r"Schema::create\(\s*['\"](\w+)['\"]\s*,\s*function[^{]*\{(.*?)\n\s*\}\s*\)",
                text,
                re.S,
            ):
                self._table(table, body, rel)

    def _table(self, table: str, body: str, rel: str) -> None:
        if table in {"password_reset_tokens", "sessions", "jobs", "cache", "failed_jobs"}:
            return
        name = singular(table)
        cand = EntityCandidate(name=name, table=table, source=f"{rel}#{table}")
        for kind, column, rest in re.findall(r"\$table->(\w+)\(\s*['\"](\w+)['\"]([^;]*);", body):
            cand.fields.append(column)
            if kind in {"foreignId", "unsignedBigInteger"} and column in {
                "user_id",
                "owner_id",
                "author_id",
            }:
                cand.owner_field = cand.owner_field or column
            if is_pii_name(column, table):
                cand.pii_fields.append(column)
            values = strings(rest.split("->")[0]) if kind == "enum" else []
            default = re.search(r"->default\(\s*['\"](\w+)['\"]", rest)
            if column in {"status", "state"} and values:
                cand.status_field, cand.statuses = column, values
            if table == "users" and column in {"role", "type", "user_type"}:
                for v in values:
                    self.result.role_values.setdefault(v, f"{rel}#users.{column}")
                if default:
                    self.result.signup_role_default = default.group(1)
        if re.search(r"\$table->foreignIdFor\(\s*[\w\\]*User::class", body):
            cand.owner_field = cand.owner_field or "user_id"
        if table != "users":
            self._entities.add(name)
            self.result.entities.append(cand)

    # --- views --------------------------------------------------------------------------

    def _view_text(self, view: str, depth: int = 0) -> str:
        rel = self.views.get(view)
        if rel is None or depth > 3:
            return ""
        text = self._read(rel)

        def include(match: re.Match[str]) -> str:
            return self._view_text(match.group(1), depth + 1)

        return re.sub(r"@include(?:If|When)?\(\s*['\"]([\w.-]+)['\"][^)]*\)", include, text)

    def _template(self, view: str) -> TemplateInfo | None:
        text = self._view_text(view)
        if not text:
            return None
        for parent in re.findall(r"@extends\(\s*['\"]([\w.-]+)['\"]", text):
            self.layouts.add(parent)
        for comp in re.findall(r"<x-([\w-]+)-layout\b", text):
            for candidate in (f"layouts.{comp}", f"components.{comp}-layout"):
                if candidate in self.views:
                    self.layouts.add(candidate)
        text = re.sub(
            r"@method\(\s*['\"](\w+)['\"]\s*\)",
            r'<input type="hidden" name="_method" value="\1">',
            text,
        )
        return parse_template(text, self.translate)

    def _href(self, href: str) -> str | None:
        if href.startswith(URL_MARK):
            return self.url_names.get(href[len(URL_MARK) :])
        if href.startswith("/") and not href.startswith("//"):
            return href.split("?")[0]
        return None

    def _fill(self, component: ComponentInfo, info: TemplateInfo, rel: str, path: str) -> None:
        for i, tform in enumerate(info.forms, start=1):
            method = tform.method_override or tform.method
            if method == "GET":
                continue
            action = self._href(tform.action) if tform.action else path
            if action is None:
                self.result.notes.append(f"{rel}:{tform.line}: forma manzili aniqlanmadi")
                continue
            fields = [
                FormField(
                    name=f.name,
                    label=f.label or None,
                    type=f.type or "text",
                    required=f.required,
                    rules="|".join(f.rules) or None,
                    options=f.options or None,
                )
                for f in tform.fields
            ]
            src = f"{rel}:{tform.line}"
            opener = info.openers.get(tform.modal) if tform.modal else None
            if fields:
                form = Form(
                    id=re.sub(r"[^a-z0-9]+", "_", f"{component.name}_form{i}".lower()),
                    page_path=path,
                    fields=fields,
                    submit=Target(role="button", name=tform.submit)
                    if tform.submit
                    else Target(css="form [type=submit]"),
                    api=f"{method} {action}",
                )
                component.forms.append(form)
                component.actions.append(
                    ActionBinding(
                        component.name,
                        "form",
                        method,
                        action,
                        tform.submit,
                        src,
                        opener=opener,
                        in_modal=tform.modal is not None,
                        form_id=form.id,
                    )
                )
            elif tform.submit:
                component.actions.append(
                    ActionBinding(
                        component.name,
                        "button",
                        method,
                        action,
                        tform.submit,
                        src,
                        opener=opener,
                        in_modal=tform.modal is not None,
                    )
                )
        for href, label in info.links:
            target = self._href(href)
            if target is not None:
                component.links.append(LinkInfo(component.name, label, target, rel))

    def _view_component(self, view: str, path: str, src: str) -> str | None:
        info = self._template(view)
        if info is None:
            self.result.notes.append(f"{src}: «{view}» Blade ko'rinishi topilmadi")
            return None
        name = f"laravel:{view}@{path}"
        component = ComponentInfo(name=name, file=self.views.get(view, view))
        self._fill(component, info, component.file, path)
        self.result.components[name] = component
        return name

    def _emit_layouts(self) -> None:
        for view in sorted(self.layouts):
            info = self._template(view)
            if info is None:
                continue
            component = ComponentInfo(name=f"layout:{view}", file=self.views.get(view, view))
            self._fill(component, info, component.file, "/")
            self.result.components[component.name] = component
            for link in component.links:
                self.result.nav.append(NavItem(link.label, link.to, component.file))


def _method_body(text: str, method: str) -> str | None:
    match = re.search(rf"function\s+{re.escape(method)}\s*\([^)]*\)[^{{]*\{{", text)
    if not match:
        return None
    depth = 0
    for i in range(match.end() - 1, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[match.end() : i]
    return None


def _view(body: str) -> str | None:
    match = re.search(r"\bview\(\s*['\"]([\w.-]+)['\"]", body) or re.search(
        r"Inertia::render\(\s*['\"]([\w/.-]+)['\"]", body
    )
    return match.group(1) if match else None


def _owned(body: str) -> bool:
    return bool(
        re.search(
            r"->(user_id|owner_id|author_id)\s*!==?\s*(auth\(\)->id\(\)|\$request->user\(\)->id"
            r"|Auth::id\(\)|auth\(\)->user\(\)->id)",
            body,
        )
        or re.search(
            r"where\(\s*['\"](user_id|owner_id)['\"]\s*,\s*(auth\(\)->id\(\)|Auth::id\(\)"
            r"|\$request->user\(\)->id)",
            body,
        )
        or re.search(r"(auth\(\)->user\(\)|\$request->user\(\)|Auth::user\(\))->\w+\(\)", body)
        or re.search(r"\$this->authorize\(", body)
    )
