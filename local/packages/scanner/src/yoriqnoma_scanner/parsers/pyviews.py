"""Checks on Python view functions shared by the Django and Flask parsers (TZ FR-S4).

Guards written in the body (``if user.role != ...: raise / abort / redirect``), project
decorators and test functions, ownership filters, status changes and preconditions. Read
with the stdlib ast; nothing is imported or run.
"""

from __future__ import annotations

import ast
import re

from yoriqnoma_scanner.parsers.base import GuardInfo, ParseResult
from yoriqnoma_scanner.parsers.django_models import enum_value
from yoriqnoma_scanner.pyindex import PyIndex, PyModule, call_name, dotted_name, kwarg

FuncDef = ast.FunctionDef | ast.AsyncFunctionDef

ADMIN_WORDS = ("admin", "superuser", "superadmin", "staff", "root")
ADMIN_FLAGS = {"is_staff", "is_superuser", "is_admin"}
ROLE_ATTRS = {"role", "roles", "user_type", "account_type"}
STATUS_ATTRS = {"status", "state"}
OWNER_ATTRS = {
    "owner",
    "user",
    "author",
    "created_by",
    "creator",
    "customer",
    "client",
    "owner_id",
    "user_id",
    "author_id",
    "created_by_id",
}
DENY_CALLS = ("Forbidden", "redirect", "Redirect", "NotFound", "404", "Denied", "Unauthorized")
WRITE_METHODS = ("POST", "PUT", "PATCH", "DELETE")


def _is_admin_word(text: str) -> bool:
    low = text.lower()
    return any(w in low for w in ADMIN_WORDS)


def _strings(node: ast.expr | None) -> list[str]:
    if isinstance(node, ast.List | ast.Tuple | ast.Set):
        return [
            e.value for e in node.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)
        ]
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    return []


USER_EXPRS = {"user", "u", "self.user", "current_user", "g.user", "flask_login.current_user"}


def _user_expr(node: ast.AST) -> bool:
    """The signed-in user: ``request.user`` (Django), ``current_user`` / ``g.user`` (Flask)."""
    name = dotted_name(node)
    return name.endswith("request.user") or name in USER_EXPRS


def _user_id_expr(node: ast.AST) -> bool:
    name = dotted_name(node)
    return _user_expr(node) or (name.endswith((".id", ".pk")) and _user_expr_name(name[:-3]))


def _user_expr_name(name: str) -> bool:
    return name.endswith("request.user") or name.rstrip(".") in USER_EXPRS


def _path_verb(path: str) -> str | None:
    """What a POST to an object's page does: ``/tickets/:pk/close/`` -> "close"."""
    parts = [p for p in path.split("/") if p]
    params = [i for i, p in enumerate(parts) if p.startswith(":")]
    if not params:
        return None
    rest = parts[params[-1] + 1 :]
    if not rest:
        return "update"
    verb = rest[-1].replace("-", "_")
    if verb in {"edit", "update", "change"}:
        return "update"
    if verb in {"delete", "remove", "destroy"}:
        return "delete"
    return verb


def _denies(body: list[ast.stmt]) -> bool:
    """The branch refuses the request: raise, or return a forbidden / redirect response."""
    first = body[0] if body else None
    if isinstance(first, ast.Raise):
        return True
    if isinstance(first, ast.Expr | ast.Return) and isinstance(first.value, ast.Call):
        if call_name(first.value).split(".")[-1] in {"abort", "abort_if", "abort_unless"}:
            return True  # Flask / Werkzeug abort(403)
    if isinstance(first, ast.Return) and isinstance(first.value, ast.Call):
        call = first.value
        name = call_name(call).split(".")[-1]
        if any(w in name for w in (*DENY_CALLS, "BadRequest", "NotAllowed", "Conflict")):
            return True
        status = kwarg(call, "status")
        if isinstance(status, ast.Constant) and isinstance(status.value, int):
            return status.value >= 400
        return bool(re.search(r"HTTP_4\d\d", dotted_name(status) if status else ""))
    return False


class PyViewChecks:
    """Mixin: needs ``self.index`` (PyIndex), ``self.result`` and ``self._group_roles``."""

    index: PyIndex
    result: ParseResult
    _group_roles: dict[str, str]

    def _resolve_function(
        self, module: PyModule, node: ast.expr
    ) -> tuple[PyModule, FuncDef] | None:
        dotted = dotted_name(node)
        if not dotted:
            return None
        parts = dotted.split(".")
        if len(parts) == 1:
            return self.index.resolve_function(module, parts[0])
        found = self.index.resolve(module, parts[0])
        if isinstance(found, PyModule):
            return self.index.resolve_function(found, parts[-1])
        return None

    def _guard_function(
        self,
        fmod: PyModule,
        func: FuncDef,
        args: list[ast.expr],
        call_module: PyModule,
        expr: str,
        src: str,
    ) -> GuardInfo | None:
        """A project decorator or test function -> the guard it implements, or None."""
        roles, param = self._role_values(fmod, func, strict=False)
        if param and args:
            roles = [v for a in args if (v := enum_value(self.index, call_module, a))]
            roles += [g for a in args for g in _strings(a)]
        groups, gparam = self._group_values(func)
        if gparam and args:
            groups = [g for a in args for g in _strings(a)]
        if roles:
            roles = list(dict.fromkeys(roles))
            return GuardInfo("role", expr, src, roles, admin=any(_is_admin_word(r) for r in roles))
        if groups:
            return self._group_guard(groups, expr, src)
        attrs = {n.attr for n in ast.walk(func) if isinstance(n, ast.Attribute)}
        names = {
            dotted_name(n).split(".")[-1]
            for n in ast.walk(func)
            if isinstance(n, ast.Name | ast.Attribute)
        }
        if attrs & ADMIN_FLAGS:
            return GuardInfo("role", expr, src, ["admin"], admin=True)
        if "login_required" in names or attrs & {"is_authenticated", "is_anonymous"}:
            return GuardInfo("auth", expr, src)
        if attrs & {"has_perm", "has_perms"} or self._denies_anywhere(func):
            return GuardInfo("unknown", expr, src)
        return None

    def _test_guards(
        self, module: PyModule, node: ast.expr, expr: str, src: str
    ) -> list[GuardInfo]:
        """``user_passes_test(lambda u: u.is_staff)`` / ``test_func`` -> guards."""
        body: ast.AST | None = None
        fmod = module
        if isinstance(node, ast.Lambda):
            body = node
        else:
            found = self._resolve_function(module, node)
            if found:
                fmod, body = found
        if body is None:
            return [GuardInfo("unknown", expr, src)]
        attrs = {n.attr for n in ast.walk(body) if isinstance(n, ast.Attribute)}
        if attrs & ADMIN_FLAGS:
            return [GuardInfo("role", expr, src, ["admin"], admin=True)]
        roles, _param = self._role_values(fmod, body, strict=False)
        if roles:
            return [
                GuardInfo("role", expr, src, roles, admin=any(_is_admin_word(r) for r in roles))
            ]
        groups, _ = self._group_values(body)
        if groups:
            return [self._group_guard(groups, expr, src)]
        if self._owned([body]):
            return [GuardInfo("ownership", expr, src)]
        if attrs and attrs <= {"is_authenticated", "is_active"}:
            return [GuardInfo("auth", expr, src)]
        return [GuardInfo("unknown", expr, src)]

    def _group_guard(self, groups: list[str], expr: str, src: str) -> GuardInfo:
        ids = []
        for group in groups:
            gid = re.sub(r"[^a-z0-9]+", "_", group.lower()).strip("_") or "group"
            self._group_roles.setdefault(gid, group)
            ids.append(gid)
        return GuardInfo("role", expr, src, ids, admin=any(_is_admin_word(g) for g in groups))

    def _role_values(self, module: PyModule, node: ast.AST, strict: bool) -> tuple[list[str], bool]:
        """Role values compared against the user's role field, and whether a parameter is."""
        values: list[str] = []
        param = False
        for cmp in ast.walk(node):
            if not isinstance(cmp, ast.Compare):
                continue
            sides = [cmp.left, *cmp.comparators]
            role_sides = [
                s
                for s in sides
                if isinstance(s, ast.Attribute)
                and s.attr in ROLE_ATTRS
                and (not strict or "user" in dotted_name(s.value))
            ]
            if not role_sides:
                continue
            for side in sides:
                if side in role_sides:
                    continue
                items = side.elts if isinstance(side, ast.Tuple | ast.List | ast.Set) else [side]
                for item in items:
                    value = enum_value(self.index, module, item)
                    if value is not None:
                        values.append(value)
                    elif isinstance(item, ast.Name):
                        param = True
        return list(dict.fromkeys(values)), param

    @staticmethod
    def _group_values(node: ast.AST) -> tuple[list[str], bool]:
        groups: list[str] = []
        param = False
        for call in ast.walk(node):
            if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)):
                continue
            if "groups" not in dotted_name(call.func.value):
                continue
            for kw in call.keywords:
                if kw.arg in {"name", "name__in", "name__iexact"}:
                    found = _strings(kw.value)
                    groups += found
                    param = param or (not found and isinstance(kw.value, ast.Name))
        return groups, param

    def _body_guards(self, module: PyModule, func: ast.AST) -> list[GuardInfo]:
        """Checks in the view body that deny the request (``if ...: raise PermissionDenied``)."""
        guards: list[GuardInfo] = []
        for node in ast.walk(func):
            if not (isinstance(node, ast.If) and _denies(node.body)):
                continue
            test = node.test
            expr = ast.unparse(test)
            src = module.src(node)
            attrs = {n.attr for n in ast.walk(test) if isinstance(n, ast.Attribute)}
            if attrs & ADMIN_FLAGS:
                guards.append(GuardInfo("role", expr, src, ["admin"], admin=True))
                continue
            roles, _param = self._role_values(module, test, strict=True)
            if roles:
                guards.append(
                    GuardInfo("role", expr, src, roles, admin=any(_is_admin_word(r) for r in roles))
                )
                continue
            groups, _ = self._group_values(test)
            if groups:
                guards.append(self._group_guard(groups, expr, src))
            elif attrs & {"is_authenticated", "is_anonymous"}:
                guards.append(GuardInfo("auth", expr, src))
            elif attrs & {"has_perm", "has_perms"}:
                guards.append(GuardInfo("unknown", expr, src))
        return guards

    @staticmethod
    def _denies_anywhere(func: ast.AST) -> bool:
        return any(isinstance(n, ast.If) and _denies(n.body) for n in ast.walk(func))

    @staticmethod
    def _handles_post(func: ast.AST) -> bool:
        for node in ast.walk(func):
            if isinstance(node, ast.Attribute) and node.attr in {"POST", "FILES", "form", "files"}:
                if dotted_name(node.value).endswith("request"):
                    return True
            if isinstance(node, ast.Compare) and dotted_name(node.left).endswith("request.method"):
                if any(
                    isinstance(c, ast.Constant) and c.value in {"POST", "PUT", "PATCH", "DELETE"}
                    for c in node.comparators
                ):
                    return True
                if any(
                    isinstance(c, ast.Constant) and c.value == "GET" for c in node.comparators
                ) and any(isinstance(op, ast.NotEq) for op in node.ops):
                    return True
        return False

    def _owned(self, nodes: list[ast.AST]) -> bool:
        for root in nodes:
            for node in ast.walk(root):
                if isinstance(node, ast.Call):
                    name = call_name(node).split(".")[-1]
                    if name in {
                        "get_object_or_404",
                        "get_list_or_404",
                        "filter",
                        "get",
                        "filter_by",
                    }:
                        for kw in node.keywords:  # .filter(<any field>=request.user)
                            if kw.arg and _user_id_expr(kw.value):
                                return True
                elif isinstance(node, ast.Compare):
                    sides = [node.left, *node.comparators]
                    if any(_user_id_expr(s) for s in sides) and any(
                        isinstance(s, ast.Attribute) and s.attr in OWNER_ATTRS and not _user_expr(s)
                        for s in sides
                    ):
                        return True
        return False

    def _status_logic(
        self, module: PyModule, funcs: list[ast.AST]
    ) -> tuple[list[tuple[str, str]], list[str]]:
        sets: list[tuple[str, str]] = []
        requires: list[str] = []
        for func in funcs:
            for node in ast.walk(func):
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Attribute) and target.attr in STATUS_ATTRS:
                            value = enum_value(self.index, module, node.value)
                            if value is not None:
                                sets.append((target.attr, value))
                elif isinstance(node, ast.Call):
                    cname = call_name(node).split(".")[-1]
                    # .update(status=...), serializer.save(status=...), Order(status=...)
                    if cname in {"update", "save", "create"} or cname[:1].isupper():
                        for kw in node.keywords:
                            if kw.arg in STATUS_ATTRS:
                                value = enum_value(self.index, module, kw.value)
                                if value is not None:
                                    sets.append((kw.arg, value))
                elif isinstance(node, ast.If) and _denies(node.body):
                    test = node.test
                    if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
                        continue
                    if not (
                        isinstance(test, ast.Compare)
                        and isinstance(test.left, ast.Attribute)
                        and test.left.attr in STATUS_ATTRS
                    ):
                        continue
                    if isinstance(test.ops[0], ast.NotEq | ast.NotIn):
                        comp = test.comparators[0]
                        items = (
                            comp.elts
                            if isinstance(comp, ast.Tuple | ast.List | ast.Set)
                            else [comp]
                        )
                        for item in items:
                            value = enum_value(self.index, module, item)
                            if value is not None:
                                requires.append(value)
        return list(dict.fromkeys(sets)), list(dict.fromkeys(requires))

    @staticmethod
    def _downloads(func: ast.AST) -> bool:
        for node in ast.walk(func):
            if isinstance(node, ast.Call) and call_name(node).split(".")[-1] == "FileResponse":
                return True
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and "attachment" in node.value
            ):
                return True
        return False
