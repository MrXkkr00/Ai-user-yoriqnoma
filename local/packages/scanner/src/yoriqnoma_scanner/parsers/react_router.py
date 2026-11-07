"""React Router v6 routes, guard components and navigation (TZ FR-S3, FR-S4).

Supports ``<Routes><Route path element>`` JSX (nested, index and layout routes) and
``createBrowserRouter([{path, element, children}])`` objects. A guard wrapping a route's
element (``<RequireAdmin>``, ``<RequireRole role="manager">``, ``<RequireAuth>``) applies
to that route and all its children.
"""

from __future__ import annotations

import re
from pathlib import Path

from tree_sitter import Node

from yoriqnoma_scanner.ast_utils import (
    jsx_attributes,
    jsx_children,
    jsx_name,
    line,
    node_text,
    parse,
    string_value,
    unwrap_expression,
    walk,
)
from yoriqnoma_scanner.detect import ProjectInfo
from yoriqnoma_scanner.fs_guard import SafeFS
from yoriqnoma_scanner.parsers.base import GuardInfo, NavItem, ParseResult, RouteCandidate
from yoriqnoma_scanner.parsers.jsx_utils import (
    component_definitions,
    file_imports,
    label_of,
)

AUTH_GUARDS = re.compile(
    r"^(Require(Auth|Login|User)|Protected|Private|Auth(Guard|Route|Only)?$|"
    r"Authenticated|LoggedIn|RequireSignIn)",
    re.I,
)
GUARD_NAME = re.compile(
    r"^(Require|Protected|Private|Guard|Only|Has[A-Z]|Role(Guard|Route)|"
    r"(Admin|Superuser|Staff)(Route|Guard|Only|Required|Protected|Layout)$)"
)
ADMIN_WORD = re.compile(r"admin|superuser|superadmin|staffonly", re.I)
ROLE_GUARDS = re.compile(r"^(Require(Role|Roles|Permission)|RoleGuard|RoleRoute|HasRole)", re.I)
TRANSPARENT = {"Outlet", "Suspense", "React.Suspense", "Fragment", "React.Fragment", ""}


def join(parent: str, child: str) -> str:
    if child.startswith("/"):
        return child.rstrip("/") or "/"
    joined = "/".join(p.strip("/") for p in (parent, child) if p and p.strip("/"))
    return "/" + joined if joined else "/"


class ReactRouterParser:
    name = "react-router"

    def __init__(self, i18n: dict[str, str] | None = None) -> None:
        self.i18n = i18n or {}

    def applies(self, project: ProjectInfo) -> bool:
        return "react" in project.stacks

    def parse(self, project: ProjectInfo, fs: SafeFS) -> ParseResult:
        result = ParseResult()
        self._defs: dict[str, tuple[str, Node]] = {}  # component name -> (file, body)
        trees: dict[Path, Node] = {}
        for path in project.js_files:
            text = fs.read_text(path)
            if text is None:
                continue
            root = parse(text, path.suffix)
            trees[path] = root
            for name, body in component_definitions(root).items():
                self._defs.setdefault(name, (fs.rel(path), body))
        for path, root in trees.items():
            source = node_text(root)
            if "<Route" in source or "createBrowserRouter" in source or "useRoutes" in source:
                self._routes_in_file(fs, path, root, result)
            self._nav_in_file(fs, path, root, result)
        return result

    # --- routes -------------------------------------------------------------------

    def _routes_in_file(self, fs: SafeFS, path: Path, root: Node, result: ParseResult) -> None:
        rel = fs.rel(path)
        file_imports(root, path, fs.root)  # resolved lazily via self._defs by name
        for node in walk(root):
            if node.type == "jsx_element" and jsx_name(node) == "Routes":
                for child in jsx_children(node):
                    self._jsx_route(child, "", [], rel, result)
            elif node.type == "call_expression":
                func = node_text(node.child_by_field_name("function"))
                if func in {"createBrowserRouter", "createHashRouter", "useRoutes"}:
                    args = node.child_by_field_name("arguments")
                    first = args.named_children[0] if args and args.named_children else None
                    if first is not None and first.type == "array":
                        for item in first.named_children:
                            self._object_route(item, "", [], rel, result)

    def _jsx_route(
        self, node: Node, parent: str, guards: list[GuardInfo], rel: str, result: ParseResult
    ) -> None:
        if node.type not in {"jsx_element", "jsx_self_closing_element"}:
            return
        if jsx_name(node) != "Route":
            return
        attrs = jsx_attributes(node)
        path_value = string_value(unwrap_expression(attrs.get("path"))) if "path" in attrs else None
        element = unwrap_expression(attrs.get("element"))
        component, own_guards = self._element(element, rel)
        all_guards = [*guards, *own_guards]
        full = join(parent, path_value) if path_value is not None else parent
        if "index" in attrs or path_value is not None:
            self._add_page(full or "/", component, all_guards, f"{rel}:{line(node)}", result)
        for child in jsx_children(node):
            self._jsx_route(child, full, all_guards, rel, result)

    def _object_route(
        self, node: Node, parent: str, guards: list[GuardInfo], rel: str, result: ParseResult
    ) -> None:
        if node.type != "object":
            return
        props: dict[str, Node] = {}
        for pair in node.named_children:
            if pair.type == "pair":
                key = node_text(pair.child_by_field_name("key")).strip("\"'")
                value = pair.child_by_field_name("value")
                if value is not None:
                    props[key] = value
        path_value = string_value(props.get("path"))
        component, own_guards = self._element(unwrap_expression(props.get("element")), rel)
        all_guards = [*guards, *own_guards]
        full = join(parent, path_value) if path_value is not None else parent
        if "index" in props or path_value is not None:
            self._add_page(full or "/", component, all_guards, f"{rel}:{line(node)}", result)
        children = props.get("children")
        if children is not None and children.type == "array":
            for item in children.named_children:
                self._object_route(item, full, all_guards, rel, result)

    def _add_page(
        self,
        path: str,
        component: str | None,
        guards: list[GuardInfo],
        source: str,
        result: ParseResult,
    ) -> None:
        if path.endswith("*") or component is None:
            return  # catch-all (404) or a pure guard/layout wrapper without its own page
        result.routes.append(
            RouteCandidate(
                path=path,
                kind="page",
                methods=["GET"],
                guards=list(guards),
                source=source,
                component=component,
            )
        )

    def _element(self, element: Node | None, rel: str) -> tuple[str | None, list[GuardInfo]]:
        """Inner page component of a route element, and the guards wrapping it."""
        guards: list[GuardInfo] = []
        node = element
        while node is not None and node.type in {"jsx_element", "jsx_self_closing_element"}:
            name = jsx_name(node)
            guard = self._guard(node, name, f"{rel}:{line(node)}")
            if guard is not None:
                guards.append(guard)
            elif name not in TRANSPARENT:
                return name, guards
            inner = [
                c
                for c in jsx_children(node)
                if c.type in {"jsx_element", "jsx_self_closing_element"}
            ]
            node = inner[0] if inner else None
        return None, guards

    def _guard(self, node: Node, name: str, source: str) -> GuardInfo | None:
        attrs = jsx_attributes(node)
        roles: list[str] = []
        for key in ("role", "roles", "allow", "allowed", "requiredRole"):
            if key in attrs:
                value = unwrap_expression(attrs[key])
                if value is None:
                    continue
                if value.type == "array":
                    roles += [v for c in value.named_children if (v := string_value(c))]
                elif (single := string_value(value)) is not None:
                    roles.append(single)
        is_guard = bool(GUARD_NAME.match(name)) or bool(roles)
        if is_guard and (ADMIN_WORD.search(name) or any(ADMIN_WORD.search(r) for r in roles)):
            return GuardInfo("role", f"<{name}>", source, roles=roles or ["admin"], admin=True)
        if roles and (ROLE_GUARDS.search(name) or self._body_checks_role(name)):
            return GuardInfo("role", f"<{name} role={roles}>", source, roles=roles)
        if AUTH_GUARDS.search(name):
            return GuardInfo("auth", f"<{name}>", source)
        if ROLE_GUARDS.search(name):
            return GuardInfo("unknown", f"<{name}>", source)
        if self._body_redirects_to_login(name):
            return GuardInfo("auth", f"<{name}>", source)
        return None

    def _body_checks_role(self, name: str) -> bool:
        found = self._defs.get(name)
        return found is not None and ".role" in node_text(found[1])

    def _body_redirects_to_login(self, name: str) -> bool:
        found = self._defs.get(name)
        if not found:
            return False
        body = node_text(found[1])
        return "<Navigate" in body and "/login" in body and "children" in body

    # --- navigation ---------------------------------------------------------------

    def _nav_in_file(self, fs: SafeFS, path: Path, root: Node, result: ParseResult) -> None:
        rel = fs.rel(path)
        for node in walk(root):
            if node.type not in {"jsx_element", "jsx_self_closing_element"}:
                continue
            if jsx_name(node) not in {"nav", "header", "NavBar", "Navbar", "Menu"}:
                continue
            for el in walk(node):
                if el.type not in {"jsx_element", "jsx_self_closing_element"}:
                    continue
                if jsx_name(el) not in {"Link", "NavLink", "a"}:
                    continue
                attrs = jsx_attributes(el)
                target = unwrap_expression(attrs.get("to") or attrs.get("href"))
                to = string_value(target)
                label = label_of(el, self.i18n)
                if to and to.startswith("/") and ":" not in to and label:
                    if not any(n.path == to for n in result.nav):
                        result.nav.append(NavItem(label, to, f"{rel}:{line(el)}"))
