"""Files the local app produces and a person uploads here (TZ FR-SV9, SEC-13).

* ``blueprint.json`` (mode A, A+B): size limit, JSON, the blueprint schema.
* ``bundle.zip`` (mode A'): size limit, zip slip, only json/png/jpg/webp, every file
  listed in the manifest with a matching sha256 (and nothing unlisted), capture.json and
  blueprint.json valid, every image the capture refers to present.

There is no automatic way in: the local app never connects to the server (rule 10).
"""

from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import IO

from django.conf import settings
from pydantic import ValidationError

from yoriqnoma_core.explorer.bundle import ALLOWED_SUFFIXES, verify_bundle
from yoriqnoma_schemas import Blueprint, CaptureRun


class UploadError(ValueError):
    """The uploaded file cannot be used; the message is shown to the user (Uzbek)."""


def _schema_error(what: str, exc: ValidationError) -> UploadError:
    errors = exc.errors()
    if not errors:
        return UploadError(f"{what} sxemaga mos emas")
    where = ".".join(str(p) for p in errors[0]["loc"]) or "-"
    return UploadError(f"{what} sxemaga mos emas ({where}: {errors[0]['msg']})")


def parse_blueprint(raw: bytes) -> Blueprint:
    limit = int(settings.YORIQNOMA_BLUEPRINT_MAX_BYTES)
    if len(raw) > limit:
        raise UploadError(f"blueprint.json juda katta (> {limit // (1024 * 1024)} MB)")
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UploadError("blueprint.json o'qilmadi: bu JSON fayl emas") from exc
    if not isinstance(data, dict) or "flows" not in data or "roles" not in data:
        raise UploadError(
            "Bu blueprint.json emas. Lokal dasturdagi «Blueprint» natijasini yuklang."
        )
    try:
        return Blueprint.model_validate(data)
    except ValidationError as exc:
        raise _schema_error("blueprint.json", exc) from exc


def read_blueprint(stream: IO[bytes]) -> Blueprint:
    limit = int(settings.YORIQNOMA_BLUEPRINT_MAX_BYTES)
    raw = stream.read(limit + 1)
    return parse_blueprint(raw)


@dataclass
class Bundle:
    capture: CaptureRun
    blueprint: Blueprint | None
    files: dict[str, bytes] = field(default_factory=dict)

    def extract(self, run_dir: Path) -> None:
        """Write the bundle into a run folder (names were checked, still resolved again)."""
        root = run_dir.resolve()
        for name, data in self.files.items():
            target = (run_dir / PurePosixPath(name)).resolve()
            if not target.is_relative_to(root):
                raise UploadError(f"xavfli fayl yo'li: {name}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)


def _check_names(path: Path) -> None:
    with zipfile.ZipFile(path) as zf:
        for info in zf.infolist():
            name = info.filename
            parts = PurePosixPath(name).parts
            if (
                name.startswith(("/", "\\"))
                or "\\" in name
                or ".." in parts
                or (parts and ":" in parts[0])
            ):
                raise UploadError(f"xavfli fayl yo'li bundle ichida: {name}")
            if info.is_dir():
                continue
            mode = (info.external_attr >> 16) & 0o170000
            if mode == 0o120000:
                raise UploadError(f"bundle ichida symlink bor: {name}")
            if PurePosixPath(name).suffix.lower() not in ALLOWED_SUFFIXES:
                raise UploadError(
                    f"ruxsat etilmagan fayl turi: {name} (faqat json, png, jpg, webp)"
                )


def read_bundle_file(path: Path) -> Bundle:
    limit = int(settings.YORIQNOMA_BUNDLE_MAX_BYTES)
    if path.stat().st_size > limit:
        raise UploadError(f"bundle.zip juda katta (> {limit // (1024 * 1024)} MB)")
    if not zipfile.is_zipfile(path):
        raise UploadError("Bu zip fayl emas. Lokal dasturdagi «Bundle» natijasini yuklang.")
    _check_names(path)
    try:
        with zipfile.ZipFile(path) as zf:
            manifest = json.loads(zf.read("manifest.json"))
    except KeyError as exc:
        raise UploadError("bundle ichida manifest.json yo'q") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise UploadError("manifest.json o'qilmadi") from exc
    if not isinstance(manifest, dict) or manifest.get("format") != "yoriqnoma-bundle":
        raise UploadError("Bu yoriqnoma bundle'i emas (manifest formati boshqa)")
    try:
        files = verify_bundle(path, max_bytes=limit)
    except (ValueError, zipfile.BadZipFile) as exc:
        raise UploadError(f"bundle tekshiruvdan o'tmadi: {exc}") from exc
    listed = set(manifest.get("files", {}))
    unlisted = sorted(set(files) - listed)
    if unlisted:
        raise UploadError(f"manifestda yo'q fayllar: {', '.join(unlisted[:5])}")
    if "capture/capture.json" not in files:
        raise UploadError("bundle ichida capture/capture.json yo'q")
    try:
        capture = CaptureRun.model_validate_json(files["capture/capture.json"])
    except ValidationError as exc:
        raise _schema_error("capture.json", exc) from exc
    blueprint = None
    if "blueprint.json" in files:
        blueprint = parse_blueprint(files["blueprint.json"])
        info = blueprint.role(capture.role)
        if info is None or info.kind != "role":
            raise UploadError(
                f"capture'dagi «{capture.role}» roli blueprint'da yo'q yoki taqiqlangan"
            )
    missing = sorted(
        {
            f"capture/{img}"
            for state in capture.states
            for img in state.images.values()
            if f"capture/{img}" not in files
        }
    )
    if missing:
        raise UploadError(f"bundle'da rasmlar yetishmaydi: {', '.join(missing[:5])}")
    return Bundle(capture=capture, blueprint=blueprint, files=files)


def read_bundle(stream: IO[bytes], tmp_dir: Path) -> Bundle:
    """Copy an upload to disk with the size limit, then check it."""
    limit = int(settings.YORIQNOMA_BUNDLE_MAX_BYTES)
    tmp_dir.mkdir(parents=True, exist_ok=True)
    target = tmp_dir / "bundle.zip"
    written = 0
    with target.open("wb") as out:
        while chunk := stream.read(1024 * 1024):
            written += len(chunk)
            if written > limit:
                raise UploadError(f"bundle.zip juda katta (> {limit // (1024 * 1024)} MB)")
            out.write(chunk)
    return read_bundle_file(target)
