"""tree-sitter helpers for JavaScript, TypeScript and JSX (Python uses the stdlib ast)."""

from __future__ import annotations

import re
from collections.abc import Iterator
from functools import cache

import tree_sitter_javascript as ts_javascript
import tree_sitter_typescript as ts_typescript
from tree_sitter import Language, Node, Parser


@cache
def _parser(kind: str) -> Parser:
    if kind == "ts":
        return Parser(Language(ts_typescript.language_typescript()))
    if kind == "tsx":
        return Parser(Language(ts_typescript.language_tsx()))
    return Parser(Language(ts_javascript.language()))


def language_for(suffix: str) -> str:
    suffix = suffix.lower()
    if suffix == ".ts":
        return "ts"
    if suffix == ".tsx":
        return "tsx"
    return "js"  # .js/.jsx/.mjs/.cjs and .vue <script> blocks (JSX grammar)


def vue_script(text: str) -> str:
    """The <script> block of a .vue single-file component (empty if none)."""
    match = re.search(r"<script[^>]*>(.*?)</script>", text, re.S)
    return match.group(1) if match else ""


def parse(text: str, suffix: str = ".js") -> Node:
    if suffix.lower() == ".vue":
        text = vue_script(text)
    return _parser(language_for(suffix)).parse(text.encode("utf-8")).root_node


def node_text(node: Node | None) -> str:
    if node is None or node.text is None:
        return ""
    return node.text.decode("utf-8", errors="replace")


def line(node: Node) -> int:
    return int(node.start_point[0]) + 1


def walk(node: Node) -> Iterator[Node]:
    stack = [node]
    while stack:
        current = stack.pop()
        yield current
        stack.extend(reversed(current.children))


def children_of_type(node: Node, *types: str) -> list[Node]:
    return [c for c in node.named_children if c.type in types]


def string_value(node: Node | None) -> str | None:
    """Value of a string literal, or a template string with ${...} turned into :param."""
    if node is None:
        return None
    if node.type == "string":
        return "".join(node_text(c) for c in node.named_children if c.type != "comment")
    if node.type == "template_string":
        out: list[str] = []
        for child in node.children:
            if child.type == "string_fragment":
                out.append(node_text(child))
            elif child.type == "template_substitution":
                inner = node_text(child)[2:-1].strip()
                name = re.split(r"[^A-Za-z0-9_]", inner.split(".")[-1])[0] or "param"
                out.append(f":{name}")
        return "".join(out)
    if node.type == "parenthesized_expression" and node.named_children:
        return string_value(node.named_children[0])
    return None


def jsx_name(node: Node) -> str:
    """Element name of a jsx_element / jsx_self_closing_element ("" for fragments)."""
    target = node.child_by_field_name("open_tag") if node.type == "jsx_element" else node
    if target is None:
        return ""
    name = target.child_by_field_name("name")
    return node_text(name)


def jsx_attributes(node: Node) -> dict[str, Node | None]:
    """Attribute name -> value node (None for boolean attributes like ``required``)."""
    target = node.child_by_field_name("open_tag") if node.type == "jsx_element" else node
    attrs: dict[str, Node | None] = {}
    if target is None:
        return attrs
    for child in target.named_children:
        if child.type != "jsx_attribute":
            continue
        parts = child.named_children
        if not parts:
            continue
        key = node_text(parts[0])
        attrs[key] = parts[1] if len(parts) > 1 else None
    return attrs


def jsx_children(node: Node) -> list[Node]:
    if node.type != "jsx_element":
        return []
    return [
        c
        for c in node.named_children
        if c.type not in {"jsx_opening_element", "jsx_closing_element"}
    ]


def unwrap_expression(node: Node | None) -> Node | None:
    """``{expr}`` and ``(expr)`` -> expr."""
    while node is not None and node.type in {"jsx_expression", "parenthesized_expression"}:
        named = node.named_children
        node = named[0] if named else None
    return node
