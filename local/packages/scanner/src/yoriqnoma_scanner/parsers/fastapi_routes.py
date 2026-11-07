"""FastAPI routes and guards (TZ FR-S3, FR-S4), parsed with the stdlib ast.

Full paths follow ``APIRouter(prefix=...)`` and ``include_router(prefix=...)`` chains.
Guards come from router, decorator and parameter dependencies (``Depends(...)`` and
``Annotated[..., Depends(...)]`` aliases), classified one level into the function body.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field

from yoriqnoma_scanner.detect import ProjectInfo
from yoriqnoma_scanner.fs_guard import SafeFS
from yoriqnoma_scanner.parsers.base import GuardInfo, ParseResult, RouteCandidate
from yoriqnoma_scanner.pyindex import PyIndex, PyModule, call_name, dotted_name, kwarg

HTTP_METHODS = {"get", "post", "put", "patch", "delete"}
ADMIN_WORDS = ("admin", "superuser", "superadmin", "is_staff", "staff_member", "root")
AUTH_WORDS = ("current_user", "get_user", "auth", "login", "token", "session", "verify_user")
OWNER_FIELDS = ("user_id", "owner_id", "author_id", "created_by", "creator_id", "courier_id")
ROLE_ATTRS = ("role", "roles", "user_type", "kind", "group")
FILE_RESPONSES = {"FileResponse", "StreamingResponse"}


@dataclass(frozen=True)
class RouterRef:
    module: str
    var: str


@dataclass
class RouterDef:
    ref: RouterRef
    prefix: str
    deps: list[tuple[PyModule, ast.expr]]
    is_app: bool


@dataclass
class IncludeEdge:
    parent: RouterRef
    child: RouterRef
    prefix: str
    deps: list[tuple[PyModule, ast.expr]] = field(default_factory=list)


def to_path(fastapi_path: str) -> str:
    """FastAPI ``/orders/{order_id}`` -> ``/orders/:order_id``."""
    return re.sub(r"\{([^}:]+)(:[^}]*)?\}", r":\1", fastapi_path)


def join(*parts: str) -> str:
    joined = "/".join(p.strip("/") for p in parts if p and p.strip("/"))
    return "/" + joined if joined else "/"


class FastAPIParser:
    name = "fastapi"

    def applies(self, project: ProjectInfo) -> bool:
        return "fastapi" in project.stacks

    def parse(self, project: ProjectInfo, fs: SafeFS) -> ParseResult:
        index = PyIndex(fs, project.python_files)
        result = ParseResult(notes=list(index.errors))
        routers: dict[RouterRef, RouterDef] = {}
        edges: list[IncludeEdge] = []
        for module in index.modules.values():
            self._collect_routers(index, module, routers, edges)

        mounts = self._mounts(routers, edges)
        guard_cache: dict[tuple[str, str], GuardInfo | None] = {}
        for module in index.modules.values():
            for func in module.functions.values():
                for deco in func.decorator_list:
                    route = self._route_from_decorator(index, module, func, deco, routers)
                    if route is None:
                        continue
                    ref, method, path, deco_deps, extra = route
                    for prefix, chain_deps in mounts.get(ref, [("", [])]):
                        full = to_path(join(prefix, routers[ref].prefix, path))
                        deps = [*chain_deps, *routers[ref].deps, *deco_deps]
                        result.routes.append(
                            self._candidate(
                                index, module, func, method, full, deps, extra, guard_cache
                            )
                        )
        self._collect_roles(index, result)
        return result

    # --- routers ------------------------------------------------------------------

    def _router_ref(self, index: PyIndex, module: PyModule, node: ast.expr) -> RouterRef | None:
        if isinstance(node, ast.Name):
            found = index.resolve(module, node.id)
            if isinstance(found, tuple):
                return RouterRef(found[0].name, found[1])
            return RouterRef(module.name, node.id)
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            found = index.resolve(module, node.value.id)
            if isinstance(found, PyModule):
                return RouterRef(found.name, node.attr)
        return None

    def _collect_routers(
        self,
        index: PyIndex,
        module: PyModule,
        routers: dict[RouterRef, RouterDef],
        edges: list[IncludeEdge],
    ) -> None:
        for name, value in module.assigns.items():
            cname = call_name(value).split(".")[-1]
            if cname in {"FastAPI", "APIRouter"} and isinstance(value, ast.Call):
                prefix = index.string_constant(module, kwarg(value, "prefix")) or ""
                deps = self._deps_list(module, kwarg(value, "dependencies"))
                ref = RouterRef(module.name, name)
                routers[ref] = RouterDef(ref, prefix, deps, is_app=cname == "FastAPI")
        for node in ast.walk(module.tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
                continue
            if node.func.attr != "include_router" or not node.args:
                continue
            parent = self._router_ref(index, module, node.func.value)
            child = self._router_ref(index, module, node.args[0])
            if parent is None or child is None:
                continue
            prefix = index.string_constant(module, kwarg(node, "prefix")) or ""
            deps = self._deps_list(module, kwarg(node, "dependencies"))
            edges.append(IncludeEdge(parent, child, prefix, deps))

    @staticmethod
    def _deps_list(module: PyModule, node: ast.expr | None) -> list[tuple[PyModule, ast.expr]]:
        if isinstance(node, ast.List | ast.Tuple):
            return [(module, el) for el in node.elts]
        return []

    def _mounts(
        self, routers: dict[RouterRef, RouterDef], edges: list[IncludeEdge]
    ) -> dict[RouterRef, list[tuple[str, list[tuple[PyModule, ast.expr]]]]]:
        """Every router -> list of (prefix before its own prefix, inherited dependencies)."""
        children: dict[RouterRef, list[IncludeEdge]] = {}
        included: set[RouterRef] = set()
        for edge in edges:
            children.setdefault(edge.parent, []).append(edge)
            included.add(edge.child)
        roots = [r for r, d in routers.items() if d.is_app] or [
            r for r in routers if r not in included
        ]
        mounts: dict[RouterRef, list[tuple[str, list[tuple[PyModule, ast.expr]]]]] = {}
        stack: list[tuple[RouterRef, str, list[tuple[PyModule, ast.expr]], int]] = [
            (r, "", [], 0) for r in roots
        ]
        while stack:
            ref, prefix, deps, depth = stack.pop()
            mounts.setdefault(ref, []).append((prefix, deps))
            if depth > 10:
                continue
            own = routers.get(ref)
            own_prefix = own.prefix if own else ""
            own_deps = own.deps if own else []
            for edge in children.get(ref, []):
                stack.append(
                    (
                        edge.child,
                        join(prefix, own_prefix, edge.prefix),
                        [*deps, *own_deps, *edge.deps],
                        depth + 1,
                    )
                )
        return mounts

    # --- routes -------------------------------------------------------------------

    def _route_from_decorator(
        self,
        index: PyIndex,
        module: PyModule,
        func: ast.FunctionDef | ast.AsyncFunctionDef,
        deco: ast.expr,
        routers: dict[RouterRef, RouterDef],
    ) -> tuple[RouterRef, str, str, list[tuple[PyModule, ast.expr]], dict[str, object]] | None:
        if not (isinstance(deco, ast.Call) and isinstance(deco.func, ast.Attribute)):
            return None
        method = deco.func.attr.lower()
        if method not in HTTP_METHODS:
            return None
        ref = self._router_ref(index, module, deco.func.value)
        if ref is None or ref not in routers:
            return None
        path_node = deco.args[0] if deco.args else kwarg(deco, "path")
        path = index.string_constant(module, path_node)
        if path is None:
            return None
        deps = self._deps_list(module, kwarg(deco, "dependencies"))
        return ref, method.upper(), path, deps, {}

    def _candidate(
        self,
        index: PyIndex,
        module: PyModule,
        func: ast.FunctionDef | ast.AsyncFunctionDef,
        method: str,
        path: str,
        deps: list[tuple[PyModule, ast.expr]],
        extra: dict[str, object],
        cache: dict[tuple[str, str], GuardInfo | None],
    ) -> RouteCandidate:
        guards: list[GuardInfo] = []
        request_model: str | None = None
        for dep_module, dep in deps:
            guard = self._guard_for_dep(index, dep_module, dep, cache)
            if guard:
                guards.append(guard)
        for arg in [*func.args.args, *func.args.kwonlyargs]:
            for dep_module, dep in self._param_deps(index, module, func, arg):
                guard = self._guard_for_dep(index, dep_module, dep, cache)
                if guard:
                    guards.append(guard)
            model = self._body_model(index, module, arg.annotation)
            if model and request_model is None:
                request_model = model
        bodies = [func, *self._helpers(index, module, func)]
        if self._has_ownership(bodies):
            guards.append(GuardInfo("ownership", "egalik tekshiruvi", module.src(func)))
        status_sets, status_requires = self._status_logic(index, module, func)
        return RouteCandidate(
            path=path,
            kind="api",
            methods=[method],
            guards=guards,
            source=module.src(func),
            handler=func.name,
            request_model=request_model,
            status_sets=status_sets,
            status_requires=status_requires,
            downloads=self._returns_file(func),
            creates_user_role=self._created_user_role(index, module, func),
        )

    def _param_deps(
        self,
        index: PyIndex,
        module: PyModule,
        func: ast.FunctionDef | ast.AsyncFunctionDef,
        arg: ast.arg,
    ) -> list[tuple[PyModule, ast.expr]]:
        found: list[tuple[PyModule, ast.expr]] = []
        defaults = dict(
            zip(
                [a.arg for a in func.args.args][-len(func.args.defaults) :]
                if func.args.defaults
                else [],
                func.args.defaults,
                strict=False,
            )
        )
        kw_defaults = {
            a.arg: d
            for a, d in zip(func.args.kwonlyargs, func.args.kw_defaults, strict=False)
            if d is not None
        }
        default = defaults.get(arg.arg) or kw_defaults.get(arg.arg)
        if default is not None and call_name(default).endswith("Depends"):
            found.append((module, default))
        found.extend(self._annotation_deps(index, module, arg.annotation, 0))
        return found

    def _annotation_deps(
        self, index: PyIndex, module: PyModule, ann: ast.expr | None, depth: int
    ) -> list[tuple[PyModule, ast.expr]]:
        if ann is None or depth > 4:
            return []
        if isinstance(ann, ast.Subscript) and dotted_name(ann.value).endswith("Annotated"):
            elts = ann.slice.elts if isinstance(ann.slice, ast.Tuple) else [ann.slice]
            return [(module, e) for e in elts[1:] if call_name(e).endswith("Depends")]
        if isinstance(ann, ast.Name):
            found = index.resolve_assign(module, ann.id)
            if found:
                return self._annotation_deps(index, found[0], found[1], depth + 1)
        return []

    def _body_model(self, index: PyIndex, module: PyModule, ann: ast.expr | None) -> str | None:
        if not isinstance(ann, ast.Name):
            return None
        found = index.resolve_class(module, ann.id)
        if found and "BaseModel" in index.class_bases(*found):
            return ann.id
        return None

    # --- guards -------------------------------------------------------------------

    def _guard_for_dep(
        self,
        index: PyIndex,
        module: PyModule,
        dep: ast.expr,
        cache: dict[tuple[str, str], GuardInfo | None],
    ) -> GuardInfo | None:
        """Classify ``Depends(x)``; None when the dependency is not a guard (get_db...)."""
        if not isinstance(dep, ast.Call) or not dep.args:
            return None
        target = dep.args[0]
        src = module.src(dep)
        if isinstance(target, ast.Call):  # Depends(require_role("manager"))
            fname = call_name(target).split(".")[-1]
            roles = [v for a in target.args if (v := index.string_constant(module, a)) is not None]
            expr = ast.unparse(target)
            if roles:
                admin = any(_is_admin_word(r) for r in roles)
                return GuardInfo("role", expr, src, roles=roles, admin=admin)
            if _is_admin_word(fname):
                return GuardInfo("role", expr, src, roles=["admin"], admin=True)
            return GuardInfo("unknown", expr, src)
        name = dotted_name(target).split(".")[-1]
        if not name:
            return None
        key = (module.name, name)
        if key not in cache:
            cache[key] = None  # break recursion
            cache[key] = self._classify_function(index, module, name, src, cache)
        return cache[key]

    def _classify_function(
        self,
        index: PyIndex,
        module: PyModule,
        name: str,
        src: str,
        cache: dict[tuple[str, str], GuardInfo | None],
    ) -> GuardInfo | None:
        found = index.resolve_function(module, name)
        low = name.lower()
        if found is None:
            if _is_admin_word(low):
                return GuardInfo("role", name, src, roles=["admin"], admin=True)
            if any(w in low for w in AUTH_WORDS):
                return GuardInfo("auth", name, src)
            if any(w in low for w in ("role", "perm", "require")):
                return GuardInfo("unknown", name, src)
            return None
        fmod, func = found
        fsrc = fmod.src(func)
        roles = _role_comparisons(index, fmod, func)
        if roles == []:  # compares with a parameter: only the caller's argument says which
            return GuardInfo("unknown", name, fsrc)
        if roles is not None:
            admin = any(_is_admin_word(r) for r in roles) or _mentions_admin_flags(func)
            return GuardInfo("role", name, fsrc, roles=roles, admin=admin)
        if _mentions_admin_flags(func) or _is_admin_word(low):
            return GuardInfo("role", name, fsrc, roles=["admin"], admin=True)
        raises = _raised_statuses(func)
        inner = [
            g
            for arg in func.args.args
            for m, d in self._param_deps(index, fmod, func, arg)
            if (g := self._guard_for_dep(index, m, d, cache)) is not None
        ]
        if (
            raises & {401}
            or any(w in low for w in AUTH_WORDS)
            or any(g.kind == "auth" for g in inner)
        ):
            if raises & {403} and not inner:
                return GuardInfo("unknown", name, fsrc)
            return GuardInfo("auth", name, fsrc)
        if raises & {403}:
            return GuardInfo("unknown", name, fsrc)
        return None

    def _helpers(
        self, index: PyIndex, module: PyModule, func: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
        found: list[ast.FunctionDef | ast.AsyncFunctionDef] = []
        for node in ast.walk(func):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                hit = index.resolve_function(module, node.func.id)
                if hit and hit[1] is not func:
                    found.append(hit[1])
        return found

    @staticmethod
    def _has_ownership(bodies: list[ast.FunctionDef | ast.AsyncFunctionDef]) -> bool:
        for body in bodies:
            for node in ast.walk(body):
                if not isinstance(node, ast.Compare):
                    continue
                sides = [node.left, *node.comparators]
                names = [dotted_name(s) for s in sides]
                has_owner = any(n.split(".")[-1] in OWNER_FIELDS for n in names if n)
                has_user = any(
                    n.endswith(".id") and n.split(".")[0] in {"user", "current_user", "me"}
                    for n in names
                    if n
                )
                if has_owner and has_user:
                    return True
        return False

    def _status_logic(
        self, index: PyIndex, module: PyModule, func: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> tuple[list[tuple[str, str]], list[str]]:
        sets: list[tuple[str, str]] = []
        requires: list[str] = []
        for node in ast.walk(func):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Attribute) and isinstance(node.value, ast.Attribute):
                        enum_name = dotted_name(node.value.value)
                        if enum_name and index.is_enum(module, enum_name.split(".")[-1]):
                            value = _enum_value(index, module, enum_name, node.value.attr)
                            if target.attr not in ("role",):
                                sets.append((target.attr, value))
            elif isinstance(node, ast.If) and any(isinstance(n, ast.Raise) for n in node.body):
                test = node.test
                if isinstance(test, ast.Compare) and isinstance(test.left, ast.Attribute):
                    if test.left.attr not in ("status", "state"):
                        continue
                    op = test.ops[0]
                    comp = test.comparators[0]
                    values = _enum_values(index, module, comp)
                    if isinstance(op, ast.NotEq | ast.NotIn):
                        requires.extend(values)
        return sets, requires

    @staticmethod
    def _returns_file(func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
        for node in ast.walk(func):
            if isinstance(node, ast.Call):
                name = call_name(node).split(".")[-1]
                media = kwarg(node, "media_type")
                if (
                    isinstance(media, ast.Constant)
                    and isinstance(media.value, str)
                    and media.value.startswith("image/")
                ):
                    continue
                if name in FILE_RESPONSES:
                    return True
                if name.endswith("Response"):
                    headers = ast.unparse(kwarg(node, "headers") or ast.Constant(""))
                    if "attachment" in headers:
                        return True
        return False

    @staticmethod
    def _created_user_role(
        index: PyIndex, module: PyModule, func: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> str | None:
        for node in ast.walk(func):
            if not isinstance(node, ast.Call):
                continue
            role = kwarg(node, "role")
            if isinstance(role, ast.Attribute):
                enum_name = dotted_name(role.value)
                if enum_name and index.is_enum(module, enum_name.split(".")[-1]):
                    return _enum_value(index, module, enum_name, role.attr)
            if isinstance(role, ast.Constant) and isinstance(role.value, str):
                return role.value
        return None

    # --- roles --------------------------------------------------------------------

    def _collect_roles(self, index: PyIndex, result: ParseResult) -> None:
        for module in index.modules.values():
            for cname, cls in module.classes.items():
                if "role" not in cname.lower():
                    continue
                if not index.class_bases(module, cls) & {"Enum", "StrEnum", "IntEnum"}:
                    continue
                for member in _enum_member_values(cls):
                    result.role_values.setdefault(member, module.src(cls))
        for route in result.routes:
            for guard in route.guards:
                if guard.kind == "role":
                    for role in guard.roles:
                        result.role_values.setdefault(role, guard.source)


# --- helpers ----------------------------------------------------------------------------


def _is_admin_word(text: str) -> bool:
    low = text.lower()
    return any(w in low for w in ADMIN_WORDS)


def _mentions_admin_flags(func: ast.AST) -> bool:
    for node in ast.walk(func):
        if isinstance(node, ast.Attribute) and node.attr in {
            "is_superuser",
            "is_staff",
            "is_admin",
        }:
            return True
    return False


def _raised_statuses(func: ast.AST) -> set[int]:
    codes: set[int] = set()
    for node in ast.walk(func):
        if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call):
            for value in [*node.exc.args, *(k.value for k in node.exc.keywords)]:
                if isinstance(value, ast.Constant) and isinstance(value.value, int):
                    codes.add(value.value)
                name = dotted_name(value)
                for code in (401, 403):
                    if name.endswith(str(code)) or name.endswith(
                        "UNAUTHORIZED" if code == 401 else "FORBIDDEN"
                    ):
                        codes.add(code)
    return codes


def _enum_value(index: PyIndex, module: PyModule, enum_name: str, attr: str) -> str:
    found = index.is_enum(module, enum_name.split(".")[-1])
    if found:
        for node in found[1].body:
            if (
                isinstance(node, ast.Assign)
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == attr
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)
            ):
                return node.value.value
    return attr


def _enum_values(index: PyIndex, module: PyModule, node: ast.expr) -> list[str]:
    items = node.elts if isinstance(node, ast.Tuple | ast.List | ast.Set) else [node]
    values: list[str] = []
    for item in items:
        if isinstance(item, ast.Attribute):
            values.append(_enum_value(index, module, dotted_name(item.value), item.attr))
        elif isinstance(item, ast.Constant) and isinstance(item.value, str):
            values.append(item.value)
    return values


def _enum_member_values(cls: ast.ClassDef) -> list[str]:
    out: list[str] = []
    for node in cls.body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                out.append(node.value.value)
            elif not node.targets[0].id.startswith("_"):
                out.append(node.targets[0].id)
    return out


def _role_comparisons(
    index: PyIndex, module: PyModule, func: ast.FunctionDef | ast.AsyncFunctionDef
) -> list[str] | None:
    """Roles a guard function compares against (``user.role != Role.admin``), or None.

    An empty list means it compares against a parameter (``require_role(role)``): the
    caller's argument decides.
    """
    roles: list[str] = []
    seen = False
    for node in ast.walk(func):
        if not isinstance(node, ast.Compare):
            continue
        sides = [node.left, *node.comparators]
        if not any(isinstance(s, ast.Attribute) and s.attr in ROLE_ATTRS for s in sides):
            continue
        seen = True
        for side in sides:
            if isinstance(side, ast.Attribute) and side.attr in ROLE_ATTRS:
                continue
            roles.extend(_enum_values(index, module, side))
    return roles if seen else None
