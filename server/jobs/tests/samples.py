"""Samples of the local app's output (blueprint and bundle formats) for server tests."""

from __future__ import annotations

import io
import json
import shutil
from pathlib import Path

from PIL import Image

from yoriqnoma_core.explorer.bundle import make_bundle

EXAMPLES = Path(__file__).resolve().parents[3] / "docs" / "schemas" / "examples"


def build_bundle(target_dir: Path) -> Path:
    """A bundle.zip exactly as the local app makes it (core make_bundle)."""
    run = target_dir / "run"
    (run / "capture" / "images").mkdir(parents=True, exist_ok=True)
    shutil.copy(EXAMPLES / "blueprint.example.json", run / "blueprint.json")
    shutil.copy(EXAMPLES / "capture.example.json", run / "capture" / "capture.json")
    capture = json.loads((EXAMPLES / "capture.example.json").read_text(encoding="utf-8"))
    for state in capture["states"]:
        for rel in state["images"].values():
            Image.new("RGB", (1280, 800), "white").save(run / "capture" / rel)
    return make_bundle(run, target_dir / "bundle.zip")


def named(data: bytes, name: str) -> io.BytesIO:
    stream = io.BytesIO(data)
    stream.name = name
    return stream
