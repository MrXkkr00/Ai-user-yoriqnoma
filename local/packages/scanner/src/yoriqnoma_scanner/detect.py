"""Detect the studied project's stack (TZ FR-S2). MVP: FastAPI + React (Vite, React Router)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from yoriqnoma_scanner.fs_guard import SafeFS

JS_SUFFIXES = (".js", ".jsx", ".ts", ".tsx", ".mjs", ".vue")


@dataclass
class ProjectInfo:
    root: Path
    stacks: set[str] = field(default_factory=set)
    backend_dirs: list[Path] = field(default_factory=list)
    frontend_dirs: list[Path] = field(default_factory=list)
    e2e_files: list[Path] = field(default_factory=list)
    locales: list[Path] = field(default_factory=list)
    python_files: list[Path] = field(default_factory=list)
    js_files: list[Path] = field(default_factory=list)


def _deps_of_package_json(text: str) -> set[str]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return set()
    deps: set[str] = set()
    for key in ("dependencies", "devDependencies", "peerDependencies"):
        section = data.get(key)
        if isinstance(section, dict):
            deps.update(section)
    return deps


def _is_e2e_python(text: str) -> bool:
    return "playwright" in text and bool(re.search(r"def test_\w+\(\s*page", text))


def _is_e2e_ts(text: str) -> bool:
    return "@playwright/test" in text


def detect(fs: SafeFS) -> ProjectInfo:
    info = ProjectInfo(root=fs.root)
    py_deps = ""
    for path in fs.iter_files():
        rel = fs.rel(path)
        name = path.name.lower()
        suffix = path.suffix.lower()
        if name in {"pyproject.toml", "setup.cfg"} or re.match(r"requirements.*\.txt$", name):
            py_deps += (fs.read_text(path) or "").lower()
        elif name == "package.json":
            deps = _deps_of_package_json(fs.read_text(path) or "")
            if "react" in deps:
                info.stacks.add("react")
                info.frontend_dirs.append(path.parent)
            if "react-router-dom" in deps or "react-router" in deps:
                info.stacks.add("react-router")
            if "vite" in deps:
                info.stacks.add("vite")
            if "@playwright/test" in deps:
                info.stacks.add("playwright-ts")
            if "vue" in deps:
                info.stacks.add("vue")
        elif suffix == ".py":
            info.python_files.append(path)
            parts = {p.lower() for p in Path(rel).parts}
            text = fs.read_text(path) or ""
            if ({"e2e", "tests", "test"} & parts or name.startswith("test_")) and _is_e2e_python(
                text
            ):
                info.e2e_files.append(path)
                info.stacks.add("playwright-py")
        elif suffix in JS_SUFFIXES:
            info.js_files.append(path)
            if re.search(r"\.(spec|test)\.[jt]sx?$", name):
                text = fs.read_text(path) or ""
                if _is_e2e_ts(text):
                    info.e2e_files.append(path)
                    info.stacks.add("playwright-ts")
        elif suffix == ".json" and {"locales", "locale", "i18n", "lang"} & {
            p.lower() for p in Path(rel).parts[:-1]
        }:
            info.locales.append(path)
    if re.search(r"\bfastapi\b", py_deps):
        info.stacks.add("fastapi")
    if re.search(r"\bdjango\b", py_deps):
        info.stacks.add("django")
    if re.search(r"\bsqlalchemy\b|\bsqlmodel\b", py_deps):
        info.stacks.add("sqlalchemy")
    e2e = set(info.e2e_files)
    if "fastapi" in info.stacks:
        info.backend_dirs = sorted({p.parent for p in info.python_files if p not in e2e})
    info.python_files = [p for p in info.python_files if p not in e2e]
    info.js_files = [p for p in info.js_files if p not in e2e]
    return info
