"""SafeFS: the only way the scanner reads the studied project (TZ SEC-3, CLAUDE.md rule 2).

Forbidden files (secrets, dumps, databases) and folders (dependencies, runtime data,
VCS) are never opened. Every skipped path is recorded with a reason, never with content.
"""

from __future__ import annotations

import builtins
import fnmatch
import os
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

MAX_BYTES = 2 * 1024 * 1024

# File name patterns that are never read. The standard list cannot be shortened.
DENY_FILES: tuple[str, ...] = (
    ".env",
    ".env.*",
    "*.env",
    ".envrc",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "*.keystore",
    "*.jks",
    "id_rsa*",
    "id_ed25519*",
    "*.sql",
    "*.sql.gz",
    "*.db",
    "*.sqlite",
    "*.sqlite3",
    "*.sqlite*",
    "*dump*",
    "*.bak",
    "docker-compose*.yml",
    "docker-compose*.yaml",
    "compose*.yml",
    "secrets*",
    "*secret*.json",
    "credentials*",
    "*.eml",
)

# Folders that are never entered.
DENY_DIRS: tuple[str, ...] = (
    "storage",
    "uploads",
    "media",
    "logs",
    "log",
    "var",
    "tmp",
    "node_modules",
    ".git",
    ".hg",
    ".svn",
    "venv",
    ".venv",
    "env",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "secrets",
)

# Folders that hold build output: not secret, but not source code either.
SKIP_DIRS: tuple[str, ...] = ("dist", "build", ".next", "coverage", ".cache", "out")

TEXT_SUFFIXES = frozenset(
    {
        ".py",
        ".js",
        ".jsx",
        ".ts",
        ".tsx",
        ".mjs",
        ".cjs",
        ".vue",
        ".json",
        ".toml",
        ".txt",
        ".cfg",
        ".ini",
        ".md",
        ".html",
        ".htm",
        ".jinja",
        ".jinja2",
        ".j2",
        ".twig",
        ".php",
        ".yml",
        ".yaml",
        ".po",
    }
)


@dataclass(frozen=True)
class Skipped:
    path: str  # relative, POSIX
    reason: str


@dataclass
class SafeFS:
    root: Path
    extra_deny: tuple[str, ...] = ()
    max_bytes: int = MAX_BYTES
    skipped: list[Skipped] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.root = Path(self.root).resolve()
        if not self.root.is_dir():
            raise NotADirectoryError(f"loyiha papkasi topilmadi: {self.root}")
        self._seen_skips: set[str] = set()

    # --- checks -------------------------------------------------------------------

    def rel(self, path: Path) -> str:
        try:
            return path.relative_to(self.root).as_posix()
        except ValueError:
            return path.as_posix()

    def _skip(self, path: Path, reason: str) -> None:
        key = self.rel(path)
        if key not in self._seen_skips:
            self._seen_skips.add(key)
            self.skipped.append(Skipped(key, reason))

    def denied_reason(self, path: Path) -> str | None:
        """Why ``path`` may not be read, or None when it may be."""
        absolute = path if path.is_absolute() else self.root / path
        try:
            resolved = absolute.resolve()
        except OSError:
            return "yo'lni aniqlab bo'lmadi"
        if not resolved.is_relative_to(self.root):
            return "loyiha papkasidan tashqarida (symlink)"
        parts = resolved.relative_to(self.root).parts
        for part in parts[:-1]:
            if part.lower() in DENY_DIRS:
                return f"taqiqlangan papka: {part}/"
            if part.lower() in SKIP_DIRS:
                return f"build natijasi: {part}/"
        name = parts[-1] if parts else resolved.name
        for pattern in (*DENY_FILES, *self.extra_deny):
            if fnmatch.fnmatch(name.lower(), pattern.lower()):
                return f"taqiqlangan fayl naqshi: {pattern}"
        return None

    # --- reading ------------------------------------------------------------------

    def read_text(self, path: Path | str) -> str | None:
        """File text, or None (reason recorded) for forbidden, binary or large files."""
        target = Path(path)
        target = target if target.is_absolute() else self.root / target
        reason = self.denied_reason(target)
        if reason:
            self._skip(target, reason)
            return None
        try:
            size = target.stat().st_size
        except OSError:
            self._skip(target, "fayl topilmadi")
            return None
        if size > self.max_bytes:
            self._skip(target, f"juda katta ({size // 1024} KB > {self.max_bytes // 1024} KB)")
            return None
        # builtins.open on purpose: tests watch it to prove forbidden files stay closed.
        with builtins.open(target, "rb") as fh:
            raw = fh.read()
        if b"\0" in raw[:8192]:
            self._skip(target, "binar fayl")
            return None
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("utf-8", errors="replace")
        return text.replace("\r\n", "\n")

    def exists(self, path: Path | str) -> bool:
        target = Path(path)
        target = target if target.is_absolute() else self.root / target
        return target.is_file() and self.denied_reason(target) is None

    def iter_files(
        self, suffixes: Iterable[str] | None = None, under: Path | None = None
    ) -> Iterator[Path]:
        """Allowed files (absolute paths), never descending into forbidden folders."""
        wanted = {s.lower() for s in suffixes} if suffixes else None
        start = (under or self.root).resolve()
        if not start.is_relative_to(self.root):
            return
        for dirpath, dirnames, filenames in os.walk(start, followlinks=False):
            here = Path(dirpath)
            keep: list[str] = []
            for d in sorted(dirnames):
                low = d.lower()
                if low in DENY_DIRS:
                    self._skip(here / d, f"taqiqlangan papka: {d}/")
                elif low in SKIP_DIRS:
                    self._skip(here / d, f"build natijasi: {d}/")
                elif (here / d).is_symlink():
                    self._skip(here / d, "symlink papka")
                else:
                    keep.append(d)
            dirnames[:] = keep
            for name in sorted(filenames):
                path = here / name
                if wanted is not None and path.suffix.lower() not in wanted:
                    continue
                reason = self.denied_reason(path)
                if reason:
                    self._skip(path, reason)
                    continue
                yield path
