"""Vue: Vue Router routes and single-file components (TZ FR-S3, FR-S4, T29).

Routes come from ``createRouter({ routes })`` / ``new VueRouter({ routes })``: nested
``children``, lazy ``() => import('...')`` components and ``meta`` guards
(``requiresAuth``, ``roles`` / ``role``, ``requiresAdmin``). Components (``.vue``) give
template forms, buttons and ``router-link`` links (read like server templates) and the
API calls of their ``@submit`` / ``@click`` handlers and of ``onMounted`` / ``created``.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path, PurePosixPath

from tree_sitter import Node

from yoriqnoma_scanner.ast_utils import line, node_text, parse, string_value, walk
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
from yoriqnoma_scanner.parsers.html_forms import parse_template
from yoriqnoma_scanner.parsers.jsx_forms import api_calls
from yoriqnoma_scanner.parsers.jsx_utils import file_imports
from yoriqnoma_schemas import Form, FormField, Target

AUTH_META = {"requiresAuth", "requireAuth", "auth", "authRequired", "requiresLogin", "private"}
ADMIN_META = {"requiresAdmin", "isAdmin", "admin", "adminOnly", "superuser"}
ROLE_META = {"roles", "role", "allowedRoles", "permissions"}
MOUNT_HOOKS = {"onMounted", "onBeforeMount", "created", "mounted", "beforeMount", "watchEffect"}
NAV_NAMES = re.compile(r"(App|Layout|Nav|Header|Sidebar|Menu)", re.I)
_TEMPLATE = re.compile(r"<template[^>]*>(.*)</template>", re.S)


def join(parent: str, child: str) -> str:
    if child.startswith("/"):
        return child
    joined = "/".join(p.strip("/") for p in (parent, child) if p and p.strip("/"))
    return "/" + joined


class VueParser:
    name = "vue"

    def __init__(self, i18n: dict[str, str] | None = None) -> None:
        self.i18n = i18n or {}

    def applies(self, project: ProjectInfo) -> bool:
        return "vue" in project.stacks

    def parse(self, project: ProjectInfo, fs: SafeFS) -> ParseResult:
        self.fs = fs
        self.result = ParseResult()
        for path in project.js_files:
            text = fs.read_text(path)
            if text is None:
                continue
            if path.suffix.lower() == ".vue":
                self._component(path, text)
            if "createRouter" in text or "VueRouter" in text:
                self._router(path, parse(text, path.suffix))
        return self.result

    # --- components ---------------------------------------------------------------------

    def _component(self, path: Path, text: str) -> None:
        name = path.stem
        rel = self.fs.rel(path)
        root = parse(text, ".vue")
        funcs = _functions(root)
        calls = {fname: api_calls(body) for fname, body in funcs.items()}
        component = ComponentInfo(name=name, file=rel)
        component.loads = self._loads(root, funcs, calls)
        match = _TEMPLATE.search(text)
        template = match.group(1) if match else ""
        info = parse_template(template, lambda key: self.i18n.get(key, key))
        for i, tform in enumerate(info.forms, start=1):
            api = _first_write(calls.get(tform.handler or "", [])) or (
                (tform.method, tform.action) if tform.method != "GET" and tform.action else None
            )
            if api is None:
                continue
            fields = [
                FormField(
                    name=f.name.split(".")[-1],
                    label=f.label or None,
                    type=f.type or "text",
                    required=f.required,
                    rules="|".join(f.rules) or None,
                    options=f.options or None,
                )
                for f in tform.fields
            ]
            form = Form(
                id=re.sub(r"[^a-z0-9]+", "_", f"{name}_form{i}".lower()),
                page_path="",
                fields=fields,
                submit=Target(role="button", name=tform.submit)
                if tform.submit
                else Target(css="form [type=submit]"),
                api=f"{api[0]} {api[1]}",
            )
            component.forms.append(form)
            self.result.forms.append(form)
            component.actions.append(
                ActionBinding(
                    name,
                    "form",
                    api[0],
                    api[1],
                    tform.submit,
                    f"{rel}:{tform.line}",
                    form_id=form.id,
                )
            )
        for label, handler in info.clicks:
            api = _first_write(calls.get(handler, []))
            if api is not None and label:
                component.actions.append(ActionBinding(name, "button", api[0], api[1], label, rel))
        for href, label in info.links:
            if href.startswith("/"):
                component.links.append(LinkInfo(name, label, href, rel))
                if NAV_NAMES.search(name):
                    self.result.nav.append(NavItem(label, href, rel))
        self.result.components[name] = component

    @staticmethod
    def _loads(
        root: Node, funcs: dict[str, Node], calls: dict[str, list[tuple[str, str]]]
    ) -> list[str]:
        loads: list[str] = []
        for node in walk(root):
            hook: Node | None = None
            if (
                node.type == "call_expression"
                and node_text(node.child_by_field_name("function")) in MOUNT_HOOKS
            ):
                hook = node
            elif (
                node.type in {"method_definition", "pair"}
                and node_text(node.child_by_field_name("name") or node.child_by_field_name("key"))
                in MOUNT_HOOKS
            ):
                hook = node
            if hook is None:
                continue
            found = list(api_calls(hook))
            for sub in walk(hook):
                if sub.type == "identifier" and node_text(sub) in calls:
                    found += calls[node_text(sub)]
            for method, path in found:
                if method == "GET":
                    loads.append(f"GET {path}")
        return list(dict.fromkeys(loads))

    # --- router ---------------------------------------------------------------------------

    def _router(self, path: Path, root: Node) -> None:
        rel = self.fs.rel(path)
        imports = file_imports(root, path, self.fs.root)
        arrays: dict[str, Node] = {}
        for node in walk(root):
            if node.type == "variable_declarator":
                value = node.child_by_field_name("value")
                if value is not None and value.type == "array":
                    arrays[node_text(node.child_by_field_name("name"))] = value
        for node in walk(root):
            if node.type not in {"call_expression", "new_expression"}:
                continue
            target = node.child_by_field_name("function") or node.child_by_field_name("constructor")
            if node_text(target) not in {"createRouter", "VueRouter"}:
                continue
            args = node.child_by_field_name("arguments")
            options = args.named_children[0] if args and args.named_children else None
            if options is None or options.type != "object":
                continue
            for pair in options.named_children:
                key = pair.child_by_field_name("key") if pair.type == "pair" else pair
                if node_text(key) != "routes":
                    continue
                value = pair.child_by_field_name("value") if pair.type == "pair" else pair
                routes = (
                    arrays.get(node_text(value))
                    if value is not None
                    and (value.type in {"identifier", "shorthand_property_identifier"})
                    else value
                )
                if routes is not None and routes.type == "array":
                    for item in routes.named_children:
                        self._route(item, "", [], rel, imports)

    def _route(
        self,
        node: Node,
        parent: str,
        guards: list[GuardInfo],
        rel: str,
        imports: Mapping[str, object],
    ) -> None:
        if node.type != "object":
            return
        pairs: dict[str, Node] = {}
        for pair in node.named_children:
            if pair.type == "pair":
                key = pair.child_by_field_name("key")
                value = pair.child_by_field_name("value")
                if key is not None and value is not None:
                    pairs[string_value(key) or node_text(key)] = value
        path_value = string_value(pairs.get("path"))
        if path_value is None:
            return
        full = join(parent, path_value)
        source = f"{rel}:{line(node)}"
        own = guards + self._meta_guards(pairs.get("meta"), source)
        component = self._component_name(pairs.get("component"), imports)
        if (
            component is not None
            and "redirect" not in pairs
            and not full.endswith(("*", "(.*)*", ":pathMatch(.*)*"))
        ):
            self.result.routes.append(
                RouteCandidate(
                    path=re.sub(r"\(.*?\)", "", full).replace("?", ""),
                    kind="page",
                    methods=["GET"],
                    guards=list(own),
                    source=source,
                    component=component,
                )
            )
        children = pairs.get("children")
        if children is not None and children.type == "array":
            for child in children.named_children:
                self._route(child, full, own, rel, imports)

    @staticmethod
    def _meta_guards(meta: Node | None, source: str) -> list[GuardInfo]:
        if meta is None or meta.type != "object":
            return []
        guards: list[GuardInfo] = []
        for pair in meta.named_children:
            if pair.type != "pair":
                continue
            key = node_text(pair.child_by_field_name("key")).strip("'\"")
            value = pair.child_by_field_name("value")
            text = node_text(value)
            expr = f"meta.{key}: {text}"[:80]
            if key in ADMIN_META and text == "true":
                guards.append(GuardInfo("role", expr, source, ["admin"], admin=True))
            elif key in AUTH_META and text == "true":
                guards.append(GuardInfo("auth", expr, source))
            elif key in ROLE_META:
                values = re.findall(r"['\"]([\w-]+)['\"]", text)
                if values:
                    admin = any("admin" in v.lower() for v in values)
                    guards.append(GuardInfo("role", expr, source, values, admin=admin))
                else:
                    guards.append(GuardInfo("unknown", expr, source))
        return guards

    def _component_name(self, node: Node | None, imports: Mapping[str, object]) -> str | None:
        if node is None:
            return None
        if node.type == "identifier":
            ref = imports.get(node_text(node))
            source = getattr(ref, "source", None)
            if isinstance(source, str) and source.endswith(".vue"):
                return PurePosixPath(source).stem
            return node_text(node)
        match = re.search(r"import\(\s*['\"]([^'\"]+)['\"]\s*\)", node_text(node))
        if match:
            return PurePosixPath(match.group(1)).stem.split(".")[0]
        return None


def _functions(root: Node) -> dict[str, Node]:
    """Named functions of a component script: setup functions and Options API methods."""
    out: dict[str, Node] = {}
    for node in walk(root):
        if node.type == "function_declaration":
            out[node_text(node.child_by_field_name("name"))] = node
        elif node.type == "variable_declarator":
            value = node.child_by_field_name("value")
            if value is not None and value.type in {"arrow_function", "function_expression"}:
                out[node_text(node.child_by_field_name("name"))] = value
        elif node.type == "method_definition":
            out[node_text(node.child_by_field_name("name"))] = node
        elif node.type == "pair":
            value = node.child_by_field_name("value")
            if value is not None and value.type in {"arrow_function", "function_expression"}:
                out[node_text(node.child_by_field_name("key"))] = value
    return out


def _first_write(calls: list[tuple[str, str]]) -> tuple[str, str] | None:
    return next(((m, p) for m, p in calls if m != "GET"), None)
