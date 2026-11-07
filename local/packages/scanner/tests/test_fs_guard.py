from __future__ import annotations

import builtins
import io
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from yoriqnoma_scanner.api import scan
from yoriqnoma_scanner.detect import detect
from yoriqnoma_scanner.fs_guard import SafeFS


@pytest.fixture
def project(tmp_path: Path, write_files: Callable[..., Path]) -> Path:
    return write_files(
        tmp_path,
        {
            "app/main.py": "print('ok')\n",
            ".env": "SECRET=1\n",
            ".env.local": "SECRET=2\n",
            "prod.env": "SECRET=3\n",
            "certs/server.pem": "-----BEGIN-----\n",
            "var/demo.db": "x",
            "data.sqlite3": "x",
            "backup_dump.json": "{}",
            "db/schema.sql": "create table x;",
            "node_modules/pkg/index.js": "module.exports = 1\n",
            "uploads/photo.txt": "x",
            "docker-compose.yml": "services: {}\n",
            "secrets.json": "{}",
        },
    )


@pytest.mark.parametrize(
    "rel",
    [
        ".env",
        ".env.local",
        "prod.env",
        "certs/server.pem",
        "var/demo.db",
        "data.sqlite3",
        "backup_dump.json",
        "db/schema.sql",
        "node_modules/pkg/index.js",
        "uploads/photo.txt",
        "docker-compose.yml",
        "secrets.json",
    ],
)
def test_forbidden_files_are_not_read(project: Path, rel: str) -> None:
    fs = SafeFS(project)

    assert fs.read_text(project / rel) is None
    assert any(s.path == rel for s in fs.skipped)


def test_allowed_file_is_read_and_listing_skips_forbidden(project: Path) -> None:
    fs = SafeFS(project)

    assert fs.read_text("app/main.py") == "print('ok')\n"
    listed = {fs.rel(p) for p in fs.iter_files()}
    assert listed == {"app/main.py"}
    reasons = {s.path: s.reason for s in fs.skipped}
    assert "node_modules" in reasons and ".env" in reasons


def test_large_and_binary_files_are_skipped(tmp_path: Path) -> None:
    (tmp_path / "big.py").write_text("x" * 50, encoding="utf-8")
    (tmp_path / "bin.js").write_bytes(b"abc\0def")
    fs = SafeFS(tmp_path, max_bytes=10)

    assert fs.read_text("big.py") is None
    fs.max_bytes = 1000
    assert fs.read_text("bin.js") is None
    assert {s.reason.split(" ")[0] for s in fs.skipped} == {"juda", "binar"}


def test_extra_deny_cannot_shrink_the_standard_list(project: Path) -> None:
    fs = SafeFS(project, extra_deny=("*.py",))

    assert fs.read_text("app/main.py") is None
    assert fs.read_text(".env") is None


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need admin rights on Windows")
def test_symlink_outside_root_is_blocked(tmp_path: Path) -> None:
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    root = tmp_path / "proj"
    root.mkdir()
    os.symlink(outside, root / "link.py")
    fs = SafeFS(root)

    assert fs.read_text("link.py") is None
    assert "symlink" in fs.skipped[0].reason


def _spy(monkeypatch: pytest.MonkeyPatch, opened: list[str]) -> None:
    real_open = builtins.open
    real_io_open = io.open

    def make(real: Callable[..., Any]) -> Callable[..., Any]:
        def spy(file: Any, *args: Any, **kwargs: Any) -> Any:
            opened.append(str(file))
            return real(file, *args, **kwargs)

        return spy

    monkeypatch.setattr(builtins, "open", make(real_open))
    monkeypatch.setattr(io, "open", make(real_io_open))


def test_scanning_demo_shop_never_opens_env(
    monkeypatch: pytest.MonkeyPatch, demo_shop_dir: Path
) -> None:
    """QM-1: the trap .env (fake secrets) is never opened while scanning demo_shop."""
    opened: list[str] = []
    _spy(monkeypatch, opened)

    result = scan(demo_shop_dir, "http://127.0.0.1:8800")

    assert opened, "the spy saw no reads: the check would be vacuous"
    names = {Path(p).name for p in opened}
    assert ".env" not in names
    assert not any(n.endswith((".db", ".sqlite3", ".eml")) for n in names)
    assert any(s.path == ".env" for s in result.skipped)


def test_detect_finds_demo_shop_stack(demo_shop_dir: Path) -> None:
    info = detect(SafeFS(demo_shop_dir))

    assert {"fastapi", "react", "react-router", "vite", "playwright-py", "playwright-ts"} <= (
        info.stacks
    )
    assert {p.name for p in info.e2e_files} == {"test_register.py", "order.spec.ts"}
    assert {p.name for p in info.locales} == {"uz.json", "ru.json"}
