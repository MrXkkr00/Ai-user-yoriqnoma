"""The schemas and core libraries exist twice: local/packages and server/packages.

Each program folder is self-contained (it is installed or deployed on its own), so the
libraries both programs need are copied into each. These tests keep the copies
identical: after changing one copy, copy the whole package folder over the other.
The same file lives in local/tests and server/tests.
"""

from __future__ import annotations

from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent  # local/ or server/
REPO_ROOT = PROJECT_ROOT.parent
PROGRAMS = ("local", "server")
SHARED = ("schemas", "core")
LOCAL_ONLY = ("scanner",)
SKIP_PARTS = frozenset({"__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache"})


def other_program() -> str:
    name = PROJECT_ROOT.name
    assert name in PROGRAMS, f"tests must live in local/ or server/, not {name!r}"
    return PROGRAMS[1 - PROGRAMS.index(name)]


def snapshot(root: Path) -> dict[str, bytes]:
    """Relative path -> content (line endings normalised) of every source file under root."""
    files: dict[str, bytes] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix != ".pyc" and not SKIP_PARTS.intersection(path.parts):
            files[path.relative_to(root).as_posix()] = path.read_bytes().replace(b"\r\n", b"\n")
    return files


def differences(a: dict[str, bytes], b: dict[str, bytes]) -> list[str]:
    out = [f"only in this copy: {p}" for p in sorted(a.keys() - b.keys())]
    out += [f"only in the other copy: {p}" for p in sorted(b.keys() - a.keys())]
    out += [f"content differs: {p}" for p in sorted(a.keys() & b.keys()) if a[p] != b[p]]
    return out


@pytest.mark.parametrize("package", SHARED)
def test_shared_package_is_identical_in_both_programs(package: str) -> None:
    mine = PROJECT_ROOT / "packages" / package
    assert mine.is_dir(), f"{mine} is missing"
    other = other_program()
    theirs = REPO_ROOT / other / "packages" / package
    if not theirs.is_dir():
        pytest.skip(f"{theirs} is not in this checkout (program installed on its own)")

    problems = differences(snapshot(mine), snapshot(theirs))

    assert not problems, (
        f"packages/{package} differs between {PROJECT_ROOT.name}/ and {other}/:\n  "
        + "\n  ".join(problems)
        + f"\nCopy the up-to-date folder over the other one ({PROJECT_ROOT.name}/packages/{package}"
        f" <-> {other}/packages/{package})."
    )


@pytest.mark.parametrize("package", LOCAL_ONLY)
def test_local_only_packages_stay_out_of_the_server(package: str) -> None:
    server_copy = REPO_ROOT / "server" / "packages" / package
    assert not server_copy.exists(), f"{server_copy} must not exist: the server never reads code"


def test_differences_are_reported(tmp_path: Path) -> None:
    a, b = tmp_path / "a", tmp_path / "b"
    for root in (a, b):
        (root / "src").mkdir(parents=True)
        (root / "src" / "same.py").write_text("x = 1\n", encoding="utf-8")
    (a / "src" / "changed.py").write_text("x = 1\n", encoding="utf-8")
    (b / "src" / "changed.py").write_text("x = 2\n", encoding="utf-8")
    (a / "src" / "extra.py").write_text("", encoding="utf-8")
    (b / "src" / "__pycache__").mkdir()
    (b / "src" / "__pycache__" / "same.cpython-312.pyc").write_bytes(b"\0")

    assert differences(snapshot(a), snapshot(b)) == [
        "only in this copy: src/extra.py",
        "content differs: src/changed.py",
    ]


def test_line_endings_do_not_count_as_differences(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    (tmp_path / "a" / "f.py").write_bytes(b"x = 1\r\n")
    (tmp_path / "b" / "f.py").write_bytes(b"x = 1\n")

    assert differences(snapshot(tmp_path / "a"), snapshot(tmp_path / "b")) == []
