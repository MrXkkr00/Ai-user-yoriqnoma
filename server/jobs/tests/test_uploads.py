"""Uploads from the local app (T25, TZ FR-SV9, SEC-13): what is accepted, what is refused."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest
from django.test import override_settings

from jobs.tests.samples import EXAMPLES
from jobs.uploads import UploadError, parse_blueprint, read_bundle_file


def test_example_blueprint_is_accepted(blueprint_bytes: bytes) -> None:
    bp = parse_blueprint(blueprint_bytes)
    assert {r.id for r in bp.roles if r.kind == "role"} >= {"customer", "manager"}


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (b"not json", "JSON"),
        (b'{"a": 1}', "blueprint.json emas"),
        (b'{"flows": [], "roles": [], "x": 1}', "sxemaga mos emas"),
    ],
)
def test_bad_blueprints(data: bytes, message: str) -> None:
    with pytest.raises(UploadError, match=message):
        parse_blueprint(data)


@override_settings(YORIQNOMA_BLUEPRINT_MAX_BYTES=100)
def test_blueprint_size_limit(blueprint_bytes: bytes) -> None:
    with pytest.raises(UploadError, match="katta"):
        parse_blueprint(blueprint_bytes)


def test_local_bundle_is_accepted(bundle_path: Path, tmp_path: Path) -> None:
    bundle = read_bundle_file(bundle_path)
    assert bundle.capture.role == "customer" and bundle.blueprint is not None
    bundle.extract(tmp_path / "run")
    assert (tmp_path / "run" / "capture" / "capture.json").is_file()


def _rewrite(src: Path, dst: Path, extra: dict[str, bytes], drop: set[str] | None = None) -> Path:
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w") as zout:
        for info in zin.infolist():
            if info.filename not in (drop or set()):
                zout.writestr(info, zin.read(info))
        for name, data in extra.items():
            zout.writestr(name, data)
    return dst


def test_zip_slip_is_refused(bundle_path: Path, tmp_path: Path) -> None:
    for evil in ("../evil.json", "/abs.json", "C:/x.json", "capture\\..\\x.json"):
        bad = _rewrite(bundle_path, tmp_path / "bad.zip", {evil: b"{}"})
        with pytest.raises(UploadError, match="xavfli"):
            read_bundle_file(bad)


def test_forbidden_types_and_unlisted_files(bundle_path: Path, tmp_path: Path) -> None:
    exe = _rewrite(bundle_path, tmp_path / "exe.zip", {"capture/run.exe": b"MZ"})
    with pytest.raises(UploadError, match="ruxsat etilmagan"):
        read_bundle_file(exe)
    extra = _rewrite(bundle_path, tmp_path / "extra.zip", {"capture/images/x.png": b"png"})
    with pytest.raises(UploadError, match="manifestda yo'q"):
        read_bundle_file(extra)


def test_manifest_mismatch_and_missing_images(bundle_path: Path, tmp_path: Path) -> None:
    changed = _rewrite(
        bundle_path,
        tmp_path / "changed.zip",
        {"capture/capture.json": (EXAMPLES / "capture.example.json").read_bytes() + b" "},
        drop={"capture/capture.json"},
    )
    with pytest.raises(UploadError, match="manifest"):
        read_bundle_file(changed)
    with zipfile.ZipFile(bundle_path) as zf:
        manifest = json.loads(zf.read("manifest.json"))
    image = next(n for n in manifest["files"] if n.endswith(".png"))
    manifest["files"].pop(image)
    missing = _rewrite(
        bundle_path,
        tmp_path / "missing.zip",
        {"manifest.json": json.dumps(manifest).encode()},
        drop={image, "manifest.json"},
    )
    with pytest.raises(UploadError, match="rasmlar yetishmaydi"):
        read_bundle_file(missing)


def test_not_a_zip_and_size_limit(bundle_path: Path, tmp_path: Path) -> None:
    fake = tmp_path / "fake.zip"
    fake.write_bytes(b"hello")
    with pytest.raises(UploadError, match="zip fayl emas"):
        read_bundle_file(fake)
    with (
        override_settings(YORIQNOMA_BUNDLE_MAX_BYTES=100),
        pytest.raises(UploadError, match="katta"),
    ):
        read_bundle_file(bundle_path)


def test_symlink_in_zip_is_refused(bundle_path: Path, tmp_path: Path) -> None:
    link = zipfile.ZipInfo("capture/images/link.png")
    link.external_attr = 0o120777 << 16
    dst = tmp_path / "link.zip"
    with zipfile.ZipFile(bundle_path) as zin, zipfile.ZipFile(dst, "w") as zout:
        for info in zin.infolist():
            zout.writestr(info, zin.read(info))
        zout.writestr(link, "/etc/passwd")
    with pytest.raises(UploadError, match="symlink"):
        read_bundle_file(dst)


def test_bundle_stream_copy_respects_limit(bundle_path: Path, tmp_path: Path) -> None:
    from jobs.uploads import read_bundle

    with override_settings(YORIQNOMA_BUNDLE_MAX_BYTES=50), pytest.raises(UploadError):
        read_bundle(io.BytesIO(bundle_path.read_bytes()), tmp_path / "x")
