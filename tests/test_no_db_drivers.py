"""CLAUDE.md rule 3: the scanner and core never connect to the studied site's database.

The site is studied only through its source code (read via SafeFS) and its web UI.
These tests fail if a DB driver or ORM shows up in ``packages/scanner`` or
``packages/core``:

* in the source code (every ``.py`` file, parsed with ``ast``, including dynamic
  ``importlib.import_module("...")`` / ``__import__("...")`` calls);
* in their ``pyproject.toml`` dependencies (runtime, optional and groups);
* anywhere in their runtime dependency tree as resolved in ``uv.lock``.

Django is banned there too: the libraries must stay framework-free.
The Django apps have their *own* databases; they are not checked here.
"""

from __future__ import annotations

import ast
import re
import tomllib
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
GUARDED = {
    "yoriqnoma-scanner": REPO_ROOT / "packages" / "scanner",
    "yoriqnoma-core": REPO_ROOT / "packages" / "core",
}

# Top-level import names.
BANNED_MODULES = frozenset(
    {
        "sqlite3",
        "_sqlite3",
        "psycopg",
        "psycopg2",
        "pymysql",
        "MySQLdb",
        "mysql",
        "sqlalchemy",
        "sqlmodel",
        "asyncpg",
        "aiosqlite",
        "aiomysql",
        "aiopg",
        "oracledb",
        "cx_Oracle",
        "pymssql",
        "pyodbc",
        "pymongo",
        "motor",
        "peewee",
        "tortoise",
        "pony",
        "django",
    }
)

# Distribution names, PEP 503-normalised. A distribution is banned when its name
# equals an entry or starts with "<entry>-" (psycopg-binary, django-environ, ...).
BANNED_DISTRIBUTIONS = frozenset(
    {
        "psycopg",
        "psycopg2",
        "pymysql",
        "mysqlclient",
        "mysql-connector-python",
        "sqlalchemy",
        "sqlmodel",
        "asyncpg",
        "aiosqlite",
        "aiomysql",
        "aiopg",
        "oracledb",
        "cx-oracle",
        "pymssql",
        "pyodbc",
        "pymongo",
        "motor",
        "peewee",
        "tortoise-orm",
        "pony",
        "django",
    }
)

_DYNAMIC_IMPORTERS = frozenset({"__import__", "import_module"})
_REQUIREMENT_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


def normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def is_banned_distribution(name: str) -> bool:
    name = normalize(name)
    return any(name == banned or name.startswith(f"{banned}-") for banned in BANNED_DISTRIBUTIONS)


def _imported_names(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if isinstance(node, ast.ImportFrom):
        # Relative imports (level > 0) point inside the package itself.
        return [node.module] if node.level == 0 and node.module else []
    if isinstance(node, ast.Call) and node.args:
        func = node.func
        callee = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
        first = node.args[0]
        if (
            callee in _DYNAMIC_IMPORTERS
            and isinstance(first, ast.Constant)
            and isinstance(first.value, str)
        ):
            return [first.value]
    return []


def banned_imports(source: str, filename: str = "<string>") -> list[str]:
    """Return ``file:line: module`` for every banned import in ``source``."""
    found: list[str] = []
    for node in ast.walk(ast.parse(source, filename=filename)):
        for name in _imported_names(node):
            if name.split(".", 1)[0] in BANNED_MODULES:
                found.append(f"{filename}:{getattr(node, 'lineno', '?')}: {name}")
    return found


def python_files(package_dir: Path) -> list[Path]:
    return sorted(p for p in package_dir.rglob("*.py") if "__pycache__" not in p.parts)


def declared_requirements(pyproject: Path) -> list[str]:
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    project = data.get("project", {})
    requirements: list[str] = list(project.get("dependencies", []))
    for extra in project.get("optional-dependencies", {}).values():
        requirements.extend(extra)
    for group in data.get("dependency-groups", {}).values():
        requirements.extend(item for item in group if isinstance(item, str))
    return requirements


def requirement_name(requirement: str) -> str:
    match = _REQUIREMENT_NAME.match(requirement)
    assert match, f"cannot parse requirement {requirement!r}"
    return normalize(match.group(1))


def runtime_closure(root: str, lock: dict[str, Any]) -> set[str]:
    """Names of every package ``root`` needs at runtime, according to uv.lock."""
    entries: dict[str, list[dict[str, Any]]] = {}
    for package in lock.get("package", []):
        entries.setdefault(package["name"], []).append(package)

    seen: set[tuple[str, tuple[str, ...]]] = set()
    names: set[str] = set()
    stack: list[tuple[str, tuple[str, ...]]] = [(root, ())]
    while stack:
        name, extras = stack.pop()
        if (name, extras) in seen:
            continue
        seen.add((name, extras))
        names.add(name)
        for entry in entries.get(name, []):
            deps = list(entry.get("dependencies", []))
            for extra in extras:
                deps.extend(entry.get("optional-dependencies", {}).get(extra, []))
            for dep in deps:
                stack.append((dep["name"], tuple(sorted(dep.get("extra", [])))))
    return names


# --- the guards themselves -----------------------------------------------------------


@pytest.mark.parametrize("dist", sorted(GUARDED))
def test_source_has_no_db_or_django_imports(dist: str) -> None:
    files = python_files(GUARDED[dist])
    assert files, f"no .py files found for {dist}: the check would be vacuous"

    problems = [
        problem
        for path in files
        for problem in banned_imports(
            path.read_text(encoding="utf-8"), str(path.relative_to(REPO_ROOT))
        )
    ]

    assert not problems, "DB driver / ORM / Django imports:\n" + "\n".join(problems)


@pytest.mark.parametrize("dist", sorted(GUARDED))
def test_pyproject_declares_no_db_or_django_dependency(dist: str) -> None:
    requirements = declared_requirements(GUARDED[dist] / "pyproject.toml")

    offending = [r for r in requirements if is_banned_distribution(requirement_name(r))]

    assert not offending, f"{dist} declares banned dependencies: {offending}"


@pytest.mark.parametrize("dist", sorted(GUARDED))
def test_locked_dependency_tree_has_no_db_or_django_package(dist: str) -> None:
    lock_file = REPO_ROOT / "uv.lock"
    if not lock_file.exists():
        pytest.fail("uv.lock is missing; run `uv lock` (the lock file is committed)")
    lock = tomllib.loads(lock_file.read_text(encoding="utf-8"))

    closure = runtime_closure(dist, lock)

    assert dist in closure and len(closure) > 1, f"{dist} not found in uv.lock"
    offending = sorted(name for name in closure if is_banned_distribution(name))
    assert not offending, f"{dist} pulls in banned packages: {offending}"


# --- the detector catches what it should (negative controls) ------------------------


@pytest.mark.parametrize(
    "source",
    [
        "import sqlite3",
        "import psycopg2.extras",
        "import os, psycopg",
        "from sqlalchemy.orm import Session",
        "from sqlmodel import SQLModel",
        "from django.db import models",
        "import asyncpg as pg",
        "async def f():\n    import aiosqlite",
        "import importlib\nimportlib.import_module('pymysql')",
        "__import__('sqlite3')",
    ],
)
def test_detector_flags_banned_imports(source: str) -> None:
    assert banned_imports(source)


@pytest.mark.parametrize(
    "source",
    [
        "import json",
        "from pathlib import Path",
        "from yoriqnoma_schemas import blueprint",
        "from . import sqlite3",
        "import importlib\nimportlib.import_module(name)",
        "text = 'import sqlite3'",
    ],
)
def test_detector_allows_clean_code(source: str) -> None:
    assert banned_imports(source) == []


@pytest.mark.parametrize(
    ("name", "banned"),
    [
        ("psycopg", True),
        ("psycopg-binary", True),
        ("psycopg2_binary", True),
        ("SQLAlchemy", True),
        ("Django", True),
        ("django-environ", True),
        ("pydantic", False),
        ("playwright", False),
        ("motorway", False),
    ],
)
def test_distribution_matcher(name: str, banned: bool) -> None:
    assert is_banned_distribution(name) is banned


def test_lock_walk_follows_transitive_and_extra_dependencies() -> None:
    lock = {
        "package": [
            {"name": "core", "dependencies": [{"name": "lib", "extra": ["db"]}]},
            {
                "name": "lib",
                "dependencies": [{"name": "pydantic"}],
                "optional-dependencies": {"db": [{"name": "sqlalchemy"}]},
            },
            {"name": "pydantic"},
            {"name": "sqlalchemy"},
        ]
    }

    assert runtime_closure("core", lock) == {"core", "lib", "pydantic", "sqlalchemy"}
