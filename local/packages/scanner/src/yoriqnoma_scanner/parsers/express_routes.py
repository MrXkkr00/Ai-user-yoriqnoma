"""Express (Node.js): routers, middleware guards, handlers and models (TZ FR-S3, FR-S4, T29).

Read with tree-sitter, never run. ``express()`` apps and ``express.Router()`` routers are
followed through ``app.use('/prefix', router)`` across ``require`` / ``import`` files.
Middleware gives guards: auth (``requireAuth``, ``passport.authenticate``...), roles
(``requireRole('manager')``, ``authorize('a', 'b')``) and admin; project middleware is
read for ``req.user.role`` checks. Handlers give status changes, preconditions and owner
checks. Mongoose schemas and Sequelize models give entities. ``res.render`` views (EJS)
give pages with forms and links.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from tree_sitter import Node

from yoriqnoma_scanner.ast_utils import line, node_text, parse, string_value, walk
from yoriqnoma_scanner.detect import ProjectInfo
from yoriqnoma_scanner.fs_guard import SafeFS
from yoriqnoma_scanner.parsers.base import (
    SIGNUP_DEFAULT,
    ActionBinding,
    ComponentInfo,
    EntityCandidate,
    GuardInfo,
    LinkInfo,
    ParseResult,
    RouteCandidate,
)
from yoriqnoma_scanner.parsers.html_forms import parse_template
from yoriqnoma_scanner.parsers.jsx_utils import file_imports, resolve_module
from yoriqnoma_scanner.parsers.sqlalchemy_models import is_pii_name
from yoriqnoma_schemas import Form, FormField, Target

METHODS = {"get", "post", "put", "patch", "delete", "all"}
AUTH_NAMES = re.compile(
    r"^(require_?auth|is_?authenticated|ensure_?(authenticated|logged_?in)|authenticate|"
    r"protect|verify_?(token|jwt)|auth|check_?auth|is_?logged_?in|logged_?in|jwt_?auth|"
    r"authenticate_?(token|jwt|user)|require_?login|require_?user|with_?auth)$",
    re.I,
)
ROLE_CALLS = re.compile(
    r"^(require_?roles?|authori[sz]e|check_?roles?|has_?roles?|permit|roles?|allow_?roles?|"
    r"restrict_?to|only)$",
    re.I,
)
IGNORED = re.compile(
    r"^(cors|helmet|morgan|json|urlencoded|static|validate\w*|upload\w*|multer|limiter|"
    r"rate_?limit\w*|csrf\w*|async_?handler|catch_?async|wrap\w*|body|param|query|check|"
    r"cookie_?parser|compression|log\w*)$",
    re.I,
)
ADMIN_WORDS = ("admin", "superuser", "superadmin", "staff", "root")
STATUS_KEYS = {"status", "state"}
ROLE_KEYS = {"role", "roles", "userType", "user_type"}
USER_EXPR = re.compile(r"\breq\.user\b|\breq\.session\.user\b|\bres\.locals\.user\b")
OWNER_KEYS = {"user", "userId", "user_id", "owner", "ownerId", "owner_id", "author", "createdBy"}
_EJS_TRANS = re.compile(r"<%[=-]\s*(?:__|t|i18n\.__)\(\s*[\"']([^\"']+)[\"']\s*\)\s*%>")
_EJS_ID = re.compile(r"<%=\s*[\w.]*?(\w*[iI]d)\s*%>")
_EJS_INCLUDE = re.compile(r"<%-\s*include\(\s*[\"']([^\"']+)[\"'][^%]*%>")


def _admin(text: str) -> bool:
    low = text.lower()
    return any(w in low for w in ADMIN_WORDS)


def express_path(path: str) -> str:
    """``/orders/:id(\\d+)?`` -> ``/orders/:id``."""
    return re.sub(r"(:\w+)\([^)]*\)", r"\1", path).replace("?", "")


def join(prefix: str, part: str) -> str:
    joined = "/".join(p.strip("/") for p in (prefix, part) if p and p.strip("/"))
    return "/" + joined


@dataclass
class ExRoute:
    method: str
    path: str
    middlewares: list[Node]
    handler: Node | None
    file: Path
    line: int


@dataclass
class ExRouter:
    file: Path
    var: str
    is_app: bool
    routes: list[ExRoute] = field(default_factory=list)
    uses: list[Node] = field(default_factory=list)  # router.use(mw) without a path
    mounts: list[tuple[str, Node, list[Node]]] = field(default_factory=list)


@dataclass
class JsFile:
    path: Path
    root: Node
    imports: dict[str, tuple[str, str]]  # local -> (file or package, symbol)
    functions: dict[str, Node]  # top-level functions and arrow functions
    exports: dict[str, Node]  # exported name ("default" too) -> value node


class ExpressParser:
    name = "express"

    def applies(self, project: ProjectInfo) -> bool:
        return "express" in project.stacks

    def parse(self, project: ProjectInfo, fs: SafeFS) -> ParseResult:
        self.fs = fs
        self.result = ParseResult()
        self.files: dict[str, JsFile] = {}
        for path in project.js_files:
            if path.suffix.lower() in {".vue", ".jsx", ".tsx"}:
                continue
            text = fs.read_text(path)
            if text is None:  # controllers and helpers are read too, not only route files
                continue
            root = parse(text, path.suffix)
            self.files[fs.rel(path)] = self._index(path, root)
        self.routers: dict[tuple[str, str], ExRouter] = {}
        for rel, jf in self.files.items():
            self._collect_routers(rel, jf)
        self._templates = {fs.rel(p): p for p in project.template_files}
        self._ejs = {fs.rel(p): p for p in fs.iter_files({".ejs"}) if "node_modules" not in str(p)}
        self._models()
        seen: set[tuple[str, str, str]] = set()
        roots = [r for r in self.routers.values() if r.is_app] or list(self.routers.values())
        for router in roots:
            self._emit(router, "", [], 0, seen)
        self._roles()
        return self.result

    # --- files ------------------------------------------------------------------------

    def _index(self, path: Path, root: Node) -> JsFile:
        imports = {k: (v.source, v.name) for k, v in file_imports(root, path, self.fs.root).items()}
        functions: dict[str, Node] = {}
        exports: dict[str, Node] = {}
        for node in walk(root):
            if node.type == "function_declaration":
                functions[node_text(node.child_by_field_name("name"))] = node
            elif node.type == "variable_declarator":
                name = node_text(node.child_by_field_name("name"))
                value = node.child_by_field_name("value")
                if value is None:
                    continue
                if (
                    value.type == "call_expression"
                    and node_text(value.child_by_field_name("function")) == "require"
                ):
                    spec = string_value(_first_arg(value)) or ""
                    source = resolve_module(spec, path, self.fs.root)
                    pattern = node.child_by_field_name("name")
                    if pattern is not None and pattern.type == "object_pattern":
                        for part in walk(pattern):  # const { requireAuth } = require(...)
                            if part.type == "shorthand_property_identifier_pattern":
                                imports[node_text(part)] = (source, node_text(part))
                    else:
                        imports[name] = (source, "default")
                elif value.type in {"arrow_function", "function_expression", "function"}:
                    functions[name] = value
                else:
                    functions.setdefault(name, value)
            elif node.type == "assignment_expression":
                left = node_text(node.child_by_field_name("left"))
                right = node.child_by_field_name("right")
                if right is None:
                    continue
                if left == "module.exports":
                    exports["default"] = right
                    if right.type == "object":
                        for name, value in _object_pairs(right).items():
                            exports[name] = value
                elif left.startswith(("exports.", "module.exports.")):
                    exports[left.split(".")[-1]] = right
            elif node.type == "export_statement":
                value = node.child_by_field_name("value")
                decl = node.child_by_field_name("declaration")
                if value is not None and "default" in node_text(node)[:16]:
                    exports["default"] = value
                if decl is not None:
                    for sub in walk(decl):
                        if sub.type in {"function_declaration", "variable_declarator"}:
                            name = node_text(sub.child_by_field_name("name"))
                            target = sub.child_by_field_name("value") or sub
                            exports[name] = target
                            if sub.type == "function_declaration":
                                functions[name] = sub
        return JsFile(path, root, imports, functions, exports)

    def _resolve(self, rel: str, name: str, depth: int = 0) -> tuple[str, Node] | None:
        """A local name -> (file, definition node), following imports and exports."""
        jf = self.files.get(rel)
        if jf is None or depth > 4:
            return None
        if name in jf.functions:
            node = jf.functions[name]
            if node.type == "identifier" and node_text(node) != name:
                return self._resolve(rel, node_text(node), depth + 1)
            return rel, node
        if name in jf.imports:
            src, symbol = jf.imports[name]
            target = self.files.get(src)
            if target is None:
                return None
            exported = target.exports.get(symbol)
            if exported is not None and exported.type == "identifier":
                return self._resolve(src, node_text(exported), depth + 1)
            if exported is not None:
                return src, exported
            return self._resolve(src, symbol, depth + 1)
        return None

    def _member(self, rel: str, node: Node) -> tuple[str, Node] | None:
        """``ordersController.pay`` -> the ``pay`` function in the controller's file."""
        if node.type == "identifier":
            return self._resolve(rel, node_text(node))
        if node.type != "member_expression":
            return None
        obj = node_text(node.child_by_field_name("object"))
        prop = node_text(node.child_by_field_name("property"))
        jf = self.files.get(rel)
        if jf is None:
            return None
        if obj in jf.imports:
            src, symbol = jf.imports[obj]
            target = self.files.get(src)
            if target is None:
                return None
            if prop in target.exports:
                value = target.exports[prop]
                if value.type == "identifier":
                    return self._resolve(src, node_text(value))
                return src, value
            return self._resolve(src, prop)
        found = self._resolve(rel, obj)
        if found is not None and found[1].type == "object":
            member = _object_pairs(found[1]).get(prop)
            if member is not None:
                if member.type == "identifier":
                    return self._resolve(found[0], node_text(member))
                return found[0], member
        return None

    # --- routers ------------------------------------------------------------------------

    def _collect_routers(self, rel: str, jf: JsFile) -> None:
        for node in walk(jf.root):
            if node.type != "variable_declarator":
                continue
            value = node.child_by_field_name("value")
            if value is None or value.type != "call_expression":
                continue
            func = node_text(value.child_by_field_name("function"))
            name = node_text(node.child_by_field_name("name"))
            if func in {"express"}:
                self.routers[(rel, name)] = ExRouter(jf.path, name, True)
            elif func.endswith("Router") or func == "Router":
                self.routers[(rel, name)] = ExRouter(jf.path, name, False)
        for node in walk(jf.root):
            if node.type != "call_expression":
                continue
            callee = node.child_by_field_name("function")
            if callee is None or callee.type != "member_expression":
                continue
            prop = node_text(callee.child_by_field_name("property"))
            obj = callee.child_by_field_name("object")
            if obj is None:
                continue
            args = _args(node)
            chain = _route_chain(obj)
            if chain is not None:  # router.route('/x').get(...).post(...)
                router = self.routers.get((rel, chain[0]))
                if router is not None and prop in METHODS:
                    self._add_route(router, prop, chain[1], args, jf, node)
                continue
            router = self.routers.get((rel, node_text(obj)))
            if router is None:
                continue
            if prop in METHODS and args:
                path = string_value(args[0])
                if path is not None:
                    self._add_route(router, prop, path, args[1:], jf, node)
            elif prop == "use" and args:
                path = string_value(args[0])
                if path is None:
                    for arg in args:
                        router.uses.append(arg)
                else:
                    *middleware, target = args[1:] or [args[0]]
                    router.mounts.append((path, target, list(middleware)))

    def _add_route(
        self, router: ExRouter, method: str, path: str, args: list[Node], jf: JsFile, node: Node
    ) -> None:
        handler = args[-1] if args else None
        middlewares = list(args[:-1])
        for m in ("get", "post", "put", "patch", "delete") if method == "all" else (method,):
            router.routes.append(
                ExRoute(m.upper(), path, middlewares, handler, jf.path, line(node))
            )

    def _router_for(self, rel: str, node: Node) -> ExRouter | None:
        """The router a ``use()`` target refers to: local, imported or ``require(...)``."""
        if node.type == "call_expression" and node_text(node.child_by_field_name("function")) == (
            "require"
        ):
            src = resolve_module(
                string_value(_first_arg(node)) or "", self.files[rel].path, self.fs.root
            )
            return self._exported_router(src)
        if node.type != "identifier":
            return None
        name = node_text(node)
        if (rel, name) in self.routers:
            return self.routers[(rel, name)]
        jf = self.files.get(rel)
        if jf is not None and name in jf.imports:
            src, symbol = jf.imports[name]
            return self._exported_router(src, symbol)
        return None

    def _exported_router(self, src: str, symbol: str = "default") -> ExRouter | None:
        target = self.files.get(src)
        if target is None:
            return None
        exported = target.exports.get(symbol)
        if exported is not None and exported.type == "identifier":
            return self.routers.get((src, node_text(exported)))
        return None

    # --- output -------------------------------------------------------------------------

    def _emit(
        self,
        router: ExRouter,
        prefix: str,
        inherited: list[GuardInfo],
        depth: int,
        seen: set[tuple[str, str, str]],
    ) -> None:
        if depth > 8:
            return
        rel = self.fs.rel(router.file)
        guards = list(inherited)
        children: list[ExRouter] = []
        for mw in router.uses:
            child = self._router_for(rel, mw)
            if child is not None:  # app.use(router) mounts it at the same prefix
                children.append(child)
                continue
            guard = self._mw_guard(rel, mw)
            if guard is not None:
                guards.append(guard)
        for route in router.routes:
            full = express_path(join(prefix, route.path))
            key = (route.method, full, rel)
            if key in seen:
                continue
            seen.add(key)
            self._route(rel, route, full, guards)
        for path, target, middleware in router.mounts:
            mounted = self._router_for(rel, target)
            if mounted is None:
                continue
            mguards = [g for mw in middleware if (g := self._mw_guard(rel, mw)) is not None]
            self._emit(mounted, join(prefix, path), guards + mguards, depth + 1, seen)
        for child in children:
            self._emit(child, prefix, guards, depth + 1, seen)

    def _route(self, rel: str, route: ExRoute, full: str, inherited: list[GuardInfo]) -> None:
        src = f"{rel}:{route.line}"
        guards = list(inherited)
        for mw in route.middlewares:
            guard = self._mw_guard(rel, mw)
            if guard is not None:
                guards.append(guard)
        body: Node | None = None
        body_rel = rel
        if route.handler is not None:
            if route.handler.type in {"arrow_function", "function_expression", "function"}:
                body = route.handler
            else:
                found = self._member(rel, route.handler)
                if found is not None:
                    body_rel, body = found
        sets: list[tuple[str, str]] = []
        requires: list[str] = []
        view: str | None = None
        downloads = False
        created_role: str | None = None
        if body is not None:
            text = node_text(body)
            sets, requires = _status_logic(body)
            if _owned(body):
                guards.append(GuardInfo("ownership", "egalik tekshiruvi", src))
            guards += self._body_guards(body, src)
            view = _render_view(body)
            downloads = bool(re.search(r"res\.(download|attachment)\(|attachment;", text))
            created_role = self._created_role(body)
        handler_name = node_text(route.handler)[:60] if route.handler is not None else None
        if view is not None and route.method == "GET":
            component = self._view_component(view, full, src)
            self.result.routes.append(
                RouteCandidate(
                    path=full,
                    kind="page",
                    methods=["GET"],
                    guards=guards,
                    source=src,
                    handler=handler_name,
                    component=component,
                )
            )
            return
        self.result.routes.append(
            RouteCandidate(
                path=full,
                kind="api",
                methods=[route.method],
                guards=guards,
                source=src if body_rel == rel else f"{src} -> {body_rel}",
                handler=handler_name,
                status_sets=sets,
                status_requires=requires,
                downloads=downloads,
                creates_user_role=created_role if not guards else None,
            )
        )

    # --- guards -------------------------------------------------------------------------

    def _mw_guard(self, rel: str, node: Node) -> GuardInfo | None:
        expr = node_text(node)[:80]
        src = f"{rel}:{line(node)}"
        if node.type in {"array"}:
            return None
        if node.type == "call_expression":
            func = node.child_by_field_name("function")
            name = node_text(func).split(".")[-1]
            if node_text(func) == "passport.authenticate":
                return GuardInfo("auth", expr, src)
            values = [v for a in _args(node) for v in _strings(a)]
            if ROLE_CALLS.match(name) or "role" in name.lower():
                if values:
                    return GuardInfo(
                        "role", expr, src, values, admin=any(_admin(v) for v in values)
                    )
                return GuardInfo("unknown", expr, src)
            if AUTH_NAMES.match(name):
                return GuardInfo("auth", expr, src)
            if IGNORED.match(name):
                return None
            found = self._member(rel, func) if func is not None else None
            if found is not None:
                return self._guard_from_function(found[1], expr, src, values)
            if any(w in name.lower() for w in ("perm", "guard", "can", "access")):
                return GuardInfo("unknown", expr, src)
            return None
        name = node_text(node).split(".")[-1]
        if _admin(name):
            return GuardInfo("role", expr, src, ["admin"], admin=True)
        if AUTH_NAMES.match(name):
            return GuardInfo("auth", expr, src)
        if IGNORED.match(name):
            return None
        found = self._member(rel, node)
        if found is not None:
            return self._guard_from_function(found[1], expr, src, [])
        if any(w in name.lower() for w in ("role", "perm", "guard", "only")):
            return GuardInfo("unknown", expr, src)
        return None

    def _guard_from_function(
        self, func: Node, expr: str, src: str, call_values: list[str]
    ) -> GuardInfo | None:
        text = node_text(func)
        if re.search(r"\b(isAdmin|is_admin|isSuperuser|isStaff)\b", text):
            return GuardInfo("role", expr, src, ["admin"], admin=True)
        roles = _role_values(func)
        if roles is not None:
            values = roles or call_values
            if values:
                return GuardInfo("role", expr, src, values, admin=any(_admin(v) for v in values))
            return GuardInfo("unknown", expr, src)
        if USER_EXPR.search(text) or re.search(
            r"isAuthenticated\(\)|jwt\.verify|verifyToken", text
        ):
            if re.search(r"status\(\s*40[13]\s*\)|redirect\(|next\(\s*\w*[Ee]rr", text):
                return GuardInfo("auth", expr, src)
        if re.search(r"status\(\s*403\s*\)", text):
            return GuardInfo("unknown", expr, src)
        return None

    def _body_guards(self, body: Node, src: str) -> list[GuardInfo]:
        guards: list[GuardInfo] = []
        for node in walk(body):
            if node.type != "if_statement" or not _denies(node):
                continue
            cond = node.child_by_field_name("condition")
            text = node_text(cond)
            if re.search(r"\b(isAdmin|is_admin|isStaff)\b", text):
                guards.append(GuardInfo("role", text, src, ["admin"], admin=True))
                continue
            roles = _role_values(cond) if cond is not None else None
            if roles and USER_EXPR.search(text):
                guards.append(GuardInfo("role", text, src, roles, any(_admin(r) for r in roles)))
        return guards

    def _created_role(self, body: Node) -> str | None:
        for node in walk(body):
            if node.type not in {"call_expression", "new_expression"}:
                continue
            target = node.child_by_field_name("function") or node.child_by_field_name("constructor")
            text = node_text(target)
            if not re.search(r"\bUser\b.*\b(create|build)$|^User$", text):
                continue
            for arg in _args(node):
                if arg.type == "object":
                    pairs = _object_pairs(arg)
                    for key in ROLE_KEYS:
                        value = string_value(pairs.get(key))
                        if value:
                            return value
            return self._user_default or SIGNUP_DEFAULT
        return None

    # --- views --------------------------------------------------------------------------

    def _view_component(self, view: str, path: str, src: str) -> str | None:
        rel = next(
            (r for r in self._ejs if r.endswith(f"views/{view}.ejs") or r.endswith(f"{view}.ejs")),
            None,
        )
        if rel is None:
            self.result.notes.append(f"{src}: «{view}» ko'rinishi (EJS) topilmadi")
            return None
        text = self._ejs_text(rel)
        info = parse_template(_EJS_ID.sub(":id", _EJS_TRANS.sub(lambda m: m.group(1), text)))
        name = f"express:{view}"
        component = ComponentInfo(name=name, file=rel)
        for i, tform in enumerate(info.forms, start=1):
            method = tform.method_override or tform.method
            if method == "GET":
                continue
            action = tform.action or path
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
            if fields:
                form = Form(
                    id=re.sub(r"[^a-z0-9]+", "_", f"{view}_form{i}".lower()),
                    page_path=path,
                    fields=fields,
                    submit=Target(role="button", name=tform.submit)
                    if tform.submit
                    else Target(css="form [type=submit]"),
                    api=f"{method} {action}",
                )
                component.forms.append(form)
                component.actions.append(
                    ActionBinding(name, "form", method, action, tform.submit, rel, form_id=form.id)
                )
            elif tform.submit:
                component.actions.append(
                    ActionBinding(name, "button", method, action, tform.submit, rel)
                )
        for href, text_ in info.links:
            if href.startswith("/"):
                component.links.append(LinkInfo(name, text_, href.split("?")[0], rel))
        self.result.components[name] = component
        return name

    def _ejs_text(self, rel: str, depth: int = 0) -> str:
        path = self._ejs.get(rel)
        text = self.fs.read_text(path) if path is not None else None
        if text is None or depth > 3:
            return ""
        base = str(Path(rel).parent).replace("\\", "/")

        def include(match: re.Match[str]) -> str:
            name = match.group(1)
            target = f"{base}/{name}".replace("./", "")
            target = target if target.endswith(".ejs") else target + ".ejs"
            return self._ejs_text(target, depth + 1)

        return _EJS_INCLUDE.sub(include, text)

    # --- models -------------------------------------------------------------------------

    def _models(self) -> None:
        self._user_default: str | None = None
        self._role_enum: list[str] = []
        for rel, jf in self.files.items():
            schemas: dict[str, Node] = {}
            for node in walk(jf.root):
                if node.type == "variable_declarator":
                    value = node.child_by_field_name("value")
                    if (
                        value is not None
                        and value.type == "new_expression"
                        and "Schema" in (node_text(value.child_by_field_name("constructor")))
                    ):
                        first = _first_arg(value)
                        if first is not None and first.type == "object":
                            schemas[node_text(node.child_by_field_name("name"))] = first
            for node in walk(jf.root):
                if node.type != "call_expression":
                    continue
                func = node_text(node.child_by_field_name("function"))
                args = _args(node)
                if len(args) < 2:
                    continue
                if func.endswith("model") and func != "model":  # mongoose.model('Order', s)
                    name = string_value(args[0])
                    schema = args[1]
                    fields = (
                        schemas.get(node_text(schema))
                        if schema.type == "identifier"
                        else (_first_arg(schema) if schema.type == "new_expression" else None)
                    )
                    if name and fields is not None:
                        self._entity(name, fields, f"{rel}:{line(node)}")
                elif func.endswith(".define"):  # sequelize.define('Order', {...})
                    name = string_value(args[0])
                    if name and args[1].type == "object":
                        self._entity(name, args[1], f"{rel}:{line(node)}")

    def _entity(self, name: str, fields: Node, src: str) -> None:
        entity_name = re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()
        table = entity_name + "s" if not entity_name.endswith("s") else entity_name
        cand = EntityCandidate(name=entity_name, table=table, source=src)
        for key, value in _object_pairs(fields).items():
            cand.fields.append(key)
            text = node_text(value)
            enum = _enum_values(value)
            if key in STATUS_KEYS and enum:
                cand.status_field = key
                cand.statuses = enum
            if re.search(r"ref\s*:\s*['\"]User['\"]", text) or key in {"userId", "user_id"}:
                cand.owner_field = cand.owner_field or key
            elif key in OWNER_KEYS and cand.owner_field is None and "Id" in text:
                cand.owner_field = key
            if is_pii_name(re.sub(r"(?<!^)(?=[A-Z])", "_", key).lower(), table):
                cand.pii_fields.append(key)
            if entity_name == "user" and key in ROLE_KEYS:
                self._role_enum = enum
                default = re.search(r"default\s*:\s*['\"](\w+)['\"]", text)
                if default:
                    self._user_default = default.group(1)
        self.result.entities.append(cand)

    def _roles(self) -> None:
        for value in self._role_enum:
            self.result.role_values.setdefault(value, "User modeli (role enum)")
        if self._user_default:
            self.result.signup_role_default = self._user_default


# --- tree-sitter helpers ---------------------------------------------------------------


def _route_chain(obj: Node) -> tuple[str, str] | None:
    """``router.route('/x')`` (maybe followed by ``.get(...)``) -> ("router", "/x")."""
    current: Node | None = obj
    while current is not None and current.type == "call_expression":
        func = current.child_by_field_name("function")
        if func is None or func.type != "member_expression":
            return None
        prop = node_text(func.child_by_field_name("property"))
        if prop == "route":
            path = string_value(_first_arg(current))
            target = node_text(func.child_by_field_name("object"))
            return (target, path) if path is not None else None
        if prop not in METHODS:
            return None
        current = func.child_by_field_name("object")
    return None


def _args(call: Node) -> list[Node]:
    args = call.child_by_field_name("arguments")
    return [a for a in args.named_children if a.type != "comment"] if args else []


def _first_arg(call: Node) -> Node | None:
    args = _args(call)
    return args[0] if args else None


def _strings(node: Node) -> list[str]:
    if node.type == "array":
        return [v for c in node.named_children if (v := string_value(c))]
    value = string_value(node)
    return [value] if value else []


def _object_pairs(obj: Node) -> dict[str, Node]:
    out: dict[str, Node] = {}
    for pair in obj.named_children:
        if pair.type == "pair":
            key = pair.child_by_field_name("key")
            value = pair.child_by_field_name("value")
            if key is not None and value is not None:
                out[string_value(key) or node_text(key)] = value
        elif pair.type == "shorthand_property_identifier":
            out[node_text(pair)] = pair
    return out


def _enum_values(value: Node) -> list[str]:
    text = node_text(value)
    match = re.search(r"enum\s*:\s*\[([^\]]*)\]", text) or re.search(r"ENUM\(([^)]*)\)", text)
    if not match:
        return []
    return re.findall(r"['\"]([\w-]+)['\"]", match.group(1))


def _role_values(node: Node) -> list[str] | None:
    """Values a role property is compared with; [] when compared with a variable."""
    values: list[str] = []
    seen = False
    for sub in walk(node):
        if sub.type == "binary_expression":
            left, right = sub.child_by_field_name("left"), sub.child_by_field_name("right")
            sides = [s for s in (left, right) if s is not None]
            if not any(re.search(r"\.(role|roles|userType)\b", node_text(s)) for s in sides):
                continue
            seen = True
            for side in sides:
                values += _strings(side)
        elif sub.type == "call_expression" and node_text(
            sub.child_by_field_name("function")
        ).endswith(".includes"):
            text = node_text(sub)
            if re.search(r"\.(role|roles)\b", text):
                seen = True
                obj = (sub.child_by_field_name("function") or sub).child_by_field_name("object")
                if obj is not None:
                    values += _strings(obj)
    return list(dict.fromkeys(values)) if seen else None


def _denies(node: Node) -> bool:
    cons = node.child_by_field_name("consequence")
    text = node_text(cons)
    return bool(
        re.search(r"status\(\s*4\d\d\s*\)|\bthrow\b|sendStatus\(\s*4\d\d|redirect\(", text)
        or re.search(r"next\(\s*(new\s+)?\w*(Error|createError)\(\s*4\d\d", text)
        or re.search(r"status\s*:\s*4\d\d|notFound\(|forbidden\(|unauthorized\(", text)
    )


def _status_logic(body: Node) -> tuple[list[tuple[str, str]], list[str]]:
    sets: list[tuple[str, str]] = []
    requires: list[str] = []
    for node in walk(body):
        if node.type == "assignment_expression":
            left = node.child_by_field_name("left")
            right = node.child_by_field_name("right")
            if left is not None and left.type == "member_expression":
                prop = node_text(left.child_by_field_name("property"))
                value = string_value(right)
                if prop in STATUS_KEYS and value:
                    sets.append((prop, value))
        elif node.type == "pair":
            key = node.child_by_field_name("key")
            k = string_value(key) or node_text(key)
            value = string_value(node.child_by_field_name("value"))
            if k in STATUS_KEYS and value and not _in_condition(node):
                sets.append((k, value))
        elif node.type == "if_statement" and _denies(node):
            cond = node.child_by_field_name("condition")
            for sub in walk(cond) if cond is not None else []:
                if sub.type != "binary_expression":
                    continue
                op = node_text(sub.child_by_field_name("operator"))
                left, right = sub.child_by_field_name("left"), sub.child_by_field_name("right")
                texts = [node_text(s) for s in (left, right) if s is not None]
                if op in {"!==", "!="} and any(re.search(r"\.(status|state)$", t) for t in texts):
                    for side in (left, right):
                        value = string_value(side)
                        if value:
                            requires.append(value)
    return list(dict.fromkeys(sets)), list(dict.fromkeys(requires))


def _in_condition(node: Node) -> bool:
    parent = node.parent
    while parent is not None:
        if parent.type in {"if_statement", "binary_expression"}:
            return parent.type == "binary_expression"
        if parent.type in {"call_expression", "arguments"}:
            call = parent.parent if parent.type == "arguments" else parent
            name = node_text(call.child_by_field_name("function")) if call is not None else ""
            # a query filter ({status: 'paid'} in find/where), not a change
            if re.search(r"update", name, re.I):
                return False  # findByIdAndUpdate(id, {status}), Model.update({status}, ...)
            return bool(re.search(r"(find|findOne|findAll|where|count)\w*$", name))
        parent = parent.parent
    return False


def _owned(body: Node) -> bool:
    text = node_text(body)
    if re.search(r"(user|userId|owner|ownerId|author)\s*:\s*req\.user\.(id|_id)\b", text):
        return True
    return bool(
        re.search(r"\.(user|userId|owner|ownerId|author)(\.toString\(\))?\s*!==?\s*req\.user", text)
        or re.search(r"req\.user\.(id|_id)\s*!==?\s*\w+\.(user|userId|owner|ownerId)", text)
    )


def _render_view(body: Node) -> str | None:
    for node in walk(body):
        if node.type == "call_expression" and node_text(
            node.child_by_field_name("function")
        ).endswith("res.render"):
            return string_value(_first_arg(node))
    return None
