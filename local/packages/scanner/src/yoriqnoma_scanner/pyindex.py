"""Index of a project's Python modules (stdlib ast; code is parsed, never imported)."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

from yoriqnoma_scanner.fs_guard import SafeFS


@dataclass
class PyModule:
    name: str  # dotted, e.g. "demo_shop.api.orders"
    rel: str  # "src/demo_shop/api/orders.py"
    tree: ast.Module
    functions: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = field(default_factory=dict)
    classes: dict[str, ast.ClassDef] = field(default_factory=dict)
    assigns: dict[str, ast.expr] = field(default_factory=dict)  # every NAME = expr
    imports: dict[str, tuple[str, str | None]] = field(default_factory=dict)  # local -> (mod, sym)

    def src(self, node: ast.AST) -> str:
        return f"{self.rel}:{getattr(node, 'lineno', 0)}"


def _dotted_candidates(rel: Path) -> list[str]:
    parts = list(rel.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return [".".join(parts[i:]) for i in range(len(parts)) if parts[i:]]


class PyIndex:
    """All parsed modules plus name resolution across ``import`` statements."""

    def __init__(self, fs: SafeFS, files: list[Path]) -> None:
        self.modules: dict[str, PyModule] = {}
        self._by_suffix: dict[str, list[PyModule]] = {}
        self.errors: list[str] = []
        for path in files:
            text = fs.read_text(path)
            if text is None:
                continue
            rel = path.relative_to(fs.root)
            try:
                tree = ast.parse(text, filename=rel.as_posix())
            except SyntaxError as exc:
                self.errors.append(f"{rel.as_posix()}: sintaksis xatosi ({exc.msg})")
                continue
            candidates = _dotted_candidates(rel)
            if not candidates:
                continue
            module = PyModule(name=candidates[0], rel=rel.as_posix(), tree=tree)
            self._fill(module, is_package=path.name == "__init__.py")
            self.modules[module.name] = module
            for cand in candidates:
                self._by_suffix.setdefault(cand, []).append(module)

    # --- building -----------------------------------------------------------------

    def _fill(self, module: PyModule, is_package: bool) -> None:
        package = module.name if is_package else module.name.rpartition(".")[0]
        for node in module.tree.body:
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                module.functions[node.name] = node
            elif isinstance(node, ast.ClassDef):
                module.classes[node.name] = node
        for item in ast.walk(module.tree):
            if isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name):
                        module.assigns.setdefault(target.id, item.value)
            elif isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                if item.value is not None:
                    module.assigns.setdefault(item.target.id, item.value)
            elif isinstance(item, ast.Import):
                for alias in item.names:
                    local = alias.asname or alias.name.split(".")[0]
                    module.imports[local] = (alias.name if alias.asname else local, None)
            elif isinstance(item, ast.ImportFrom):
                base = item.module or ""
                if item.level:
                    parts = package.split(".") if package else []
                    keep = parts[: len(parts) - (item.level - 1)] if item.level > 1 else parts
                    base = ".".join([*keep, base] if base else keep)
                for alias in item.names:
                    module.imports[alias.asname or alias.name] = (base, alias.name)

    # --- resolution ---------------------------------------------------------------

    def find_module(self, dotted: str) -> PyModule | None:
        if dotted in self.modules:
            return self.modules[dotted]
        matches = self._by_suffix.get(dotted, [])
        return matches[0] if len(matches) == 1 else None

    def resolve(self, module: PyModule, name: str) -> tuple[PyModule, str] | PyModule | None:
        """A local name -> (module, symbol) where it is defined, or a module, or None."""
        seen: set[tuple[str, str]] = set()
        current, symbol = module, name
        while (current.name, symbol) not in seen:
            seen.add((current.name, symbol))
            if (
                symbol in current.functions
                or symbol in current.classes
                or symbol in current.assigns
            ):
                return current, symbol
            if symbol not in current.imports:
                return None
            target_mod, target_sym = current.imports[symbol]
            if target_sym is None:
                return self.find_module(target_mod)
            sub = self.find_module(f"{target_mod}.{target_sym}")
            if sub is not None:
                return sub
            nxt = self.find_module(target_mod)
            if nxt is None:
                return None
            current, symbol = nxt, target_sym
        return None

    def resolve_function(
        self, module: PyModule, name: str
    ) -> tuple[PyModule, ast.FunctionDef | ast.AsyncFunctionDef] | None:
        found = self.resolve(module, name)
        if isinstance(found, tuple) and found[1] in found[0].functions:
            return found[0], found[0].functions[found[1]]
        return None

    def resolve_class(self, module: PyModule, name: str) -> tuple[PyModule, ast.ClassDef] | None:
        found = self.resolve(module, name)
        if isinstance(found, tuple) and found[1] in found[0].classes:
            return found[0], found[0].classes[found[1]]
        return None

    def resolve_assign(self, module: PyModule, name: str) -> tuple[PyModule, ast.expr] | None:
        found = self.resolve(module, name)
        if isinstance(found, tuple) and found[1] in found[0].assigns:
            return found[0], found[0].assigns[found[1]]
        return None

    def string_constant(self, module: PyModule, node: ast.expr | None) -> str | None:
        """A literal string, or a module constant (possibly imported) holding one."""
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.Name):
            found = self.resolve_assign(module, node.id)
            if found and isinstance(found[1], ast.Constant) and isinstance(found[1].value, str):
                return found[1].value
        return None

    def class_bases(self, module: PyModule, cls: ast.ClassDef, depth: int = 0) -> set[str]:
        """Names of all base classes, following project-local bases a few levels up."""
        names: set[str] = set()
        for base in cls.bases:
            name = dotted_name(base)
            if not name:
                continue
            last = name.split(".")[-1]
            names.add(last)
            if depth < 4:
                found = self.resolve_class(module, last)
                if found:
                    names |= self.class_bases(found[0], found[1], depth + 1)
        return names

    def is_enum(self, module: PyModule, name: str) -> tuple[PyModule, ast.ClassDef] | None:
        found = self.resolve_class(module, name)
        if found and self.class_bases(*found) & {"Enum", "StrEnum", "IntEnum"}:
            return found
        return None


def dotted_name(node: ast.AST | None) -> str:
    """``a.b.c`` for Name/Attribute chains, "" otherwise."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return ""


def call_name(node: ast.AST | None) -> str:
    return dotted_name(node.func) if isinstance(node, ast.Call) else ""


def kwarg(call: ast.Call, name: str) -> ast.expr | None:
    return next((k.value for k in call.keywords if k.arg == name), None)


def enum_members(cls: ast.ClassDef) -> list[str]:
    values: list[str] = []
    for node in cls.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name) and not target.id.startswith("_"):
                value = node.value
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    values.append(value.value)
                else:
                    values.append(target.id)
    return values
