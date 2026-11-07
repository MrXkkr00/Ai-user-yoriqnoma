"""bundle.zip for server mode A' (TZ FR-E11, SEC-13): only JSON and images, with a manifest.

The bundle holds blueprint.json, capture/capture.json and capture/images/*. The manifest
lists every file with its sha256 so the server can check integrity. No keys, no logs,
no progress files and no real values of other people are ever included.
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

ALLOWED_SUFFIXES = {".json", ".png", ".jpg", ".jpeg", ".webp"}


def make_bundle(run_dir: Path, out: Path | None = None) -> Path:
    capture = run_dir / "capture"
    files: list[tuple[str, Path]] = []
    blueprint = run_dir / "blueprint.json"
    if blueprint.is_file():
        files.append(("blueprint.json", blueprint))
    capture_json = capture / "capture.json"
    if not capture_json.is_file():
        raise FileNotFoundError(f"capture.json topilmadi: {capture_json}")
    files.append(("capture/capture.json", capture_json))
    for image in sorted((capture / "images").glob("*")):
        if image.suffix.lower() in ALLOWED_SUFFIXES and image.is_file():
            files.append((f"capture/images/{image.name}", image))
    manifest = {
        "format": "yoriqnoma-bundle",
        "version": "1.0",
        "files": {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in files},
    }
    target = out or run_dir / "bundle.zip"
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, path in files:
            zf.write(path, name)
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))
    return target


def verify_bundle(path: Path, max_bytes: int = 500 * 1024 * 1024) -> dict[str, bytes]:
    """Open a bundle safely (size limit, zip slip, allowed types, sha256 check)."""
    if path.stat().st_size > max_bytes:
        raise ValueError("bundle juda katta")
    out: dict[str, bytes] = {}
    with zipfile.ZipFile(path) as zf:
        total = 0
        for info in zf.infolist():
            name = info.filename
            if name.startswith("/") or ".." in Path(name).parts or "\\" in name:
                raise ValueError(f"xavfli fayl yo'li: {name}")
            if Path(name).suffix.lower() not in ALLOWED_SUFFIXES:
                raise ValueError(f"ruxsat etilmagan fayl turi: {name}")
            total += info.file_size
            if total > max_bytes:
                raise ValueError("bundle ichidagi fayllar juda katta")
            out[name] = zf.read(info)
    manifest = json.loads(out.pop("manifest.json", b"{}"))
    for name, digest in manifest.get("files", {}).items():
        if name not in out or hashlib.sha256(out[name]).hexdigest() != digest:
            raise ValueError(f"manifest mos emas: {name}")
    return out
