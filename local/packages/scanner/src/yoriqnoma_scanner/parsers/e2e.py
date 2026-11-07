"""Flows from Playwright E2E tests (Python and TypeScript), TZ FR-S6.

Each test function / ``test()`` block becomes a Flow. Filled values are replaced with
generated-data markers (``fake:email``...), so no literal personal data is carried over.
Tests that open admin pages are dropped (with a note).
"""

from __future__ import annotations

import ast
import re

from tree_sitter import Node

from yoriqnoma_scanner.ast_utils import line, node_text, parse, string_value, walk
from yoriqnoma_scanner.detect import ProjectInfo
from yoriqnoma_scanner.fs_guard import SafeFS
from yoriqnoma_scanner.parsers.base import ParseResult
from yoriqnoma_schemas import Flow, Step, Target

ADMIN_PATH = re.compile(r"^/(api/)?(admin|ops|superadmin|wp-admin|administrator)(/|$)", re.I)


def data_for_value(label: str, value: str) -> str:
    """A literal from a test -> a generated-data marker (never copy test data as is)."""
    low = label.lower()
    if "@" in value or "email" in low:
        return "fake:email"
    if "parol" in low or "password" in low or "пароль" in low:
        return "fake:password"
    if re.fullmatch(r"\+?\d[\d\s()-]{8,}", value) or "telefon" in low or "phone" in low:
        return "fake:phone_uz"
    if any(w in low for w in ("ism", "name", "f.i.sh", "фио", "имя")):
        return "fake:full_name"
    if any(w in low for w in ("manzil", "address", "адрес")):
        return "fake:address"
    if re.fullmatch(r"\d{1,4}", value):
        return f"literal:{value}"
    if len(value) > 20 or " " in value:
        return "fake:text"
    return f"literal:{value}"


def slug(title: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")
    return text[:40] or "test"


def _admin_flow(steps: list[Step]) -> bool:
    return any(s.action == "goto" and s.path and ADMIN_PATH.search(s.path) for s in steps)


# --- Python ---------------------------------------------------------------------------


def _py_target(call: ast.expr) -> Target | None:
    """``page.get_by_role("button", name="X")`` chains -> Target."""
    if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Attribute):
        return None
    method = call.func.attr
    args = [a.value for a in call.args if isinstance(a, ast.Constant)]
    kwargs = {
        k.arg: k.value.value for k in call.keywords if k.arg and isinstance(k.value, ast.Constant)
    }
    first = str(args[0]) if args else None
    if method == "get_by_role" and first:
        return Target(role=first, name=str(kwargs["name"]) if "name" in kwargs else None)
    if method == "get_by_label" and first:
        return Target(label=first)
    if method == "get_by_test_id" and first:
        return Target(testid=first)
    if method in {"get_by_text", "get_by_placeholder"} and first:
        return Target(name=first)
    if method == "locator" and first:
        return Target(css=first)
    return None


def _py_regex(node: ast.expr) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    first = node.args[0] if isinstance(node, ast.Call) and node.args else None
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        return f"re:{first.value}"
    return None


def _py_step(stmt: ast.stmt) -> Step | None:
    """One expression statement of a test -> one step (or None)."""
    if not isinstance(stmt, ast.Expr) or not isinstance(stmt.value, ast.Call):
        return None
    node = stmt.value
    if not isinstance(node.func, ast.Attribute):
        return None
    attr = node.func.attr
    owner = node.func.value
    if attr == "goto" and node.args and isinstance(node.args[0], ast.Constant):
        return Step(action="goto", path=str(node.args[0].value))
    if attr in {"click", "check", "fill", "select_option"}:
        target = _py_target(owner)
        if target is None:
            return None
        if attr == "click":
            return Step(action="click", target=target)
        if attr == "check":
            return Step(action="check", target=target, data="literal:true")
        first = node.args[0] if node.args else None
        value = str(first.value) if isinstance(first, ast.Constant) else ""
        data = data_for_value(target.label or target.name or "", value)
        return Step(action="fill" if attr == "fill" else "select", target=target, data=data)
    if attr == "to_have_url" and node.args:
        pattern = _py_regex(node.args[0])
        return Step(action="expect_url", path=pattern) if pattern else None
    if attr in {"to_be_visible", "to_have_text"}:
        inner = owner.args[0] if isinstance(owner, ast.Call) and owner.args else None
        target = _py_target(inner) if inner is not None else None
        return Step(action="expect_visible", target=target) if target else None
    return None


def python_flows(rel: str, text: str) -> tuple[list[Flow], list[str]]:
    flows: list[Flow] = []
    notes: list[str] = []
    tree = ast.parse(text)
    for func in tree.body:
        if not (isinstance(func, ast.FunctionDef) and func.name.startswith("test")):
            continue
        steps = [s for stmt in func.body if (s := _py_step(stmt)) is not None]
        if _admin_flow(steps):
            notes.append(f"{rel}:{func.lineno}: «{func.name}» admin sahifasini ochadi, tashlandi")
            continue
        if steps:
            flows.append(
                Flow(
                    id=f"e2e.{slug(func.name)}",
                    title=func.name.removeprefix("test_").replace("_", " "),
                    stage="core",
                    role="guest",
                    source=f"{rel}:{func.lineno}",
                    steps=steps,
                )
            )
    return flows, notes


# --- TypeScript -----------------------------------------------------------------------


def _ts_target(node: Node | None) -> Target | None:
    if node is None or node.type != "call_expression":
        return None
    func = node.child_by_field_name("function")
    if func is None or func.type != "member_expression":
        return None
    method = node_text(func.child_by_field_name("property"))
    args = node.child_by_field_name("arguments")
    named = args.named_children if args else []
    first = string_value(named[0]) if named else None
    options = node_text(named[1]) if len(named) > 1 else ""
    name_match = re.search(r"name\s*:\s*['\"`]([^'\"`]+)['\"`]", options)
    if method == "getByRole" and first:
        return Target(role=first, name=name_match.group(1) if name_match else None)
    if method == "getByLabel" and first:
        return Target(label=first)
    if method == "getByTestId" and first:
        return Target(testid=first)
    if method in {"getByText", "getByPlaceholder"} and first:
        return Target(name=first)
    if method == "locator" and first:
        return Target(css=first)
    return None


def _ts_step(call: Node) -> Step | None:
    func = call.child_by_field_name("function")
    if func is None or func.type != "member_expression":
        return None
    method = node_text(func.child_by_field_name("property"))
    obj = func.child_by_field_name("object")
    args = call.child_by_field_name("arguments")
    named = args.named_children if args else []
    if method == "goto" and named:
        path = string_value(named[0])
        return Step(action="goto", path=path) if path else None
    if method in {"click", "fill", "selectOption", "check"}:
        target = _ts_target(obj)
        if target is None:
            return None
        if method == "click":
            return Step(action="click", target=target)
        if method == "check":
            return Step(action="check", target=target, data="literal:true")
        value = string_value(named[0]) if named else ""
        data = data_for_value(target.label or target.name or "", value or "")
        return Step(action="fill" if method == "fill" else "select", target=target, data=data)
    if method == "toHaveURL" and named:
        arg = named[0]
        if arg.type == "regex":
            pattern = node_text(arg.child_by_field_name("pattern"))
            return Step(action="expect_url", path=f"re:{pattern}")
        path = string_value(arg)
        return Step(action="expect_url", path=path) if path else None
    if method in {"toBeVisible", "toHaveText"} and obj is not None:
        # expect(page.getByText("x")).toBeVisible()
        inner_args = obj.child_by_field_name("arguments")
        inner = inner_args.named_children[0] if inner_args and inner_args.named_children else None
        target = _ts_target(inner)
        return Step(action="expect_visible", target=target) if target else None
    return None


def ts_flows(rel: str, text: str, suffix: str) -> tuple[list[Flow], list[str]]:
    flows: list[Flow] = []
    notes: list[str] = []
    root = parse(text, suffix)
    for call in walk(root):
        if (
            call.type != "call_expression"
            or node_text(call.child_by_field_name("function")) != "test"
        ):
            continue
        args = call.child_by_field_name("arguments")
        named = args.named_children if args else []
        if len(named) < 2:
            continue
        title = string_value(named[0]) or "test"
        steps = [s for c in walk(named[1]) if c.type == "call_expression" if (s := _ts_step(c))]
        if _admin_flow(steps):
            notes.append(f"{rel}:{line(call)}: «{title}» admin sahifasini ochadi, tashlandi")
            continue
        if steps:
            flows.append(
                Flow(
                    id=f"e2e.{slug(title)}",
                    title=title,
                    stage="core",
                    role="guest",
                    source=f"{rel}:{line(call)}",
                    steps=steps,
                )
            )
    return flows, notes


class E2EParser:
    name = "e2e"

    def applies(self, project: ProjectInfo) -> bool:
        return bool(project.e2e_files)

    def parse(self, project: ProjectInfo, fs: SafeFS) -> ParseResult:
        result = ParseResult()
        for path in project.e2e_files:
            text = fs.read_text(path)
            if text is None:
                continue
            rel = fs.rel(path)
            try:
                if path.suffix == ".py":
                    flows, notes = python_flows(rel, text)
                else:
                    flows, notes = ts_flows(rel, text, path.suffix)
            except (SyntaxError, ValueError) as exc:
                result.notes.append(f"{rel}: E2E testni o'qib bo'lmadi ({exc})")
                continue
            result.flows += flows
            result.notes += notes
        return result
