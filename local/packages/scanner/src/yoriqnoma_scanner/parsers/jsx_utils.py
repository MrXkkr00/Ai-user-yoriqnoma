"""Shared JSX helpers: visible labels (with t() resolved), imports, component bodies."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from tree_sitter import Node

from yoriqnoma_scanner.ast_utils import (
    jsx_attributes,
    jsx_children,
    jsx_name,
    node_text,
    string_value,
    unwrap_expression,
    walk,
)

T_FUNCS = {"t", "$t", "i18n.t", "intl.formatMessage", "translate"}


def t_key(node: Node | None) -> str | None:
    """``t("order.pay")`` -> "order.pay"."""
    node = unwrap_expression(node)
    if node is None or node.type != "call_expression":
        return None
    func = node_text(node.child_by_field_name("function"))
    if func not in T_FUNCS:
        return None
    args = node.child_by_field_name("arguments")
    first = args.named_children[0] if args and args.named_children else None
    return string_value(first)


def expr_text(node: Node | None, i18n: dict[str, str]) -> str:
    """Visible text of a JSX child expression: strings, t() calls; "" for dynamic values."""
    node = unwrap_expression(node)
    if node is None:
        return ""
    key = t_key(node)
    if key is not None:
        return i18n.get(key, key)
    value = string_value(node)
    if value is not None and ":" not in value:
        return value
    return ""


def label_of(node: Node, i18n: dict[str, str]) -> str:
    """Visible label of an element: its text, nested text and t() calls."""
    parts: list[str] = []
    attrs = jsx_attributes(node)
    for key in ("aria-label", "title"):
        if key in attrs:
            text = expr_text(attrs[key], i18n)
            if text:
                return text
    for child in jsx_children(node):
        if child.type == "jsx_text":
            parts.append(node_text(child))
        elif child.type == "jsx_expression":
            parts.append(expr_text(child, i18n))
        elif child.type in {"jsx_element", "jsx_self_closing_element"}:
            if jsx_name(child) not in {"svg", "img", "Icon"}:
                parts.append(label_of(child, i18n))
    return re.sub(r"\s+", " ", " ".join(parts)).strip()


@dataclass
class ImportRef:
    source: str  # resolved file path (POSIX, relative to project root) or package name
    name: str  # imported symbol ("default" for default imports)


def file_imports(root: Node, file: Path, project_root: Path) -> dict[str, ImportRef]:
    """Local name -> where it comes from (relative imports resolved to files)."""
    out: dict[str, ImportRef] = {}
    for node in root.named_children:
        if node.type != "import_statement":
            continue
        source_node = node.child_by_field_name("source")
        spec = string_value(source_node) or ""
        resolved = resolve_module(spec, file, project_root)
        for clause in node.named_children:
            if clause.type != "import_clause":
                continue
            for part in clause.named_children:
                if part.type == "identifier":
                    out[node_text(part)] = ImportRef(resolved, "default")
                elif part.type == "named_imports":
                    for spec_node in part.named_children:
                        if spec_node.type != "import_specifier":
                            continue
                        name = node_text(spec_node.child_by_field_name("name"))
                        alias = spec_node.child_by_field_name("alias")
                        out[node_text(alias) if alias else name] = ImportRef(resolved, name)
    return out


def resolve_module(spec: str, file: Path, project_root: Path) -> str:
    if not spec.startswith("."):
        return spec
    base = (file.parent / spec).resolve()
    for candidate in (
        base,
        *(base.with_suffix(s) for s in (".jsx", ".js", ".tsx", ".ts", ".vue")),
        *(base / f"index{s}" for s in (".jsx", ".js", ".tsx", ".ts")),
    ):
        if candidate.is_file():
            try:
                return candidate.relative_to(project_root).as_posix()
            except ValueError:
                return candidate.as_posix()
    return spec


def component_definitions(root: Node) -> dict[str, Node]:
    """Top-level React components (capitalised functions / arrow functions) -> body node."""
    found: dict[str, Node] = {}
    for node in root.named_children:
        target = node
        if node.type == "export_statement":
            decl = node.child_by_field_name("declaration")
            if decl is None:
                continue
            target = decl
        if target.type == "function_declaration":
            name = node_text(target.child_by_field_name("name"))
            if name[:1].isupper():
                found[name] = target
        elif target.type in {"lexical_declaration", "variable_declaration"}:
            for decl in target.named_children:
                if decl.type != "variable_declarator":
                    continue
                name = node_text(decl.child_by_field_name("name"))
                value = decl.child_by_field_name("value")
                if (
                    name[:1].isupper()
                    and value is not None
                    and value.type
                    in {
                        "arrow_function",
                        "function_expression",
                        "function",
                        "call_expression",
                    }
                ):
                    found[name] = value
    return found


def jsx_elements(node: Node) -> list[Node]:
    return [n for n in walk(node) if n.type in {"jsx_element", "jsx_self_closing_element"}]
