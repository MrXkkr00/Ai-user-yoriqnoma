"""Text inside images (TZ FR-E10): RapidOCR, offline, CPU. Results cached by image hash.

A personal value read from an image in a foreign or unknown zone cannot be replaced, so
only that text box is blurred (``State.hidden`` with a reason). In organization or
published zones it is kept and recorded as public.
"""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from typing import Any

from PIL import Image

from yoriqnoma_core.safety.pii import find_pii


@dataclass
class OcrLine:
    text: str
    box: tuple[float, float, float, float]  # x0, y0, x1, y1 in crop pixels
    score: float


class OcrEngine:
    def __init__(self) -> None:
        self._engine: Any = None
        self._cache: dict[str, list[OcrLine]] = {}

    def _load(self) -> Any:
        if self._engine is None:
            from rapidocr_onnxruntime import RapidOCR

            self._engine = RapidOCR()
        return self._engine

    def read(self, image: Image.Image) -> list[OcrLine]:
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        key = hashlib.sha256(buf.getvalue()).hexdigest()
        if key in self._cache:
            return self._cache[key]
        import numpy as np

        result, _ = self._load()(np.asarray(image.convert("RGB"))[:, :, ::-1])
        lines: list[OcrLine] = []
        for box, text, score in result or []:
            if float(score) < 0.5:
                continue
            xs = [float(p[0]) for p in box]
            ys = [float(p[1]) for p in box]
            lines.append(OcrLine(str(text), (min(xs), min(ys), max(xs), max(ys)), float(score)))
        self._cache[key] = lines
        return lines


@dataclass
class OcrHit:
    kind: str
    zone: str
    decision: str  # "kept" | "blurred"
    box: tuple[float, float, float, float]  # document CSS px
    value: str | None = None  # only for kept (public) values


def check_images(
    engine: OcrEngine,
    screenshot: Image.Image,
    images: list[dict[str, Any]],
    scale: float,
    ignore: set[str],
    is_org_email: Any,
) -> tuple[list[OcrHit], int]:
    """OCR every image box of the screenshot; return hits and the number of lines read."""
    hits: list[OcrHit] = []
    lines_read = 0
    for img in images:
        x, y, w, h = (float(img[k]) for k in ("x", "y", "w", "h"))
        box = (int(x * scale), int(y * scale), int((x + w) * scale), int((y + h) * scale))
        if box[2] <= box[0] or box[3] <= box[1] or box[1] >= screenshot.height:
            continue
        crop = screenshot.crop(box)
        zone = str(img.get("zone", "other"))
        for line in engine.read(crop):
            lines_read += 1
            for m in find_pii(line.text, ignore):
                x0, y0, x1, y1 = line.box
                doc = (
                    x + x0 / scale - 4,
                    y + y0 / scale - 4,
                    x + x1 / scale + 4,
                    y + y1 / scale + 4,
                )
                public = zone in {"org", "editorial"} or (
                    m.kind == "email" and is_org_email(m.value)
                )
                hits.append(
                    OcrHit(
                        m.kind,
                        zone,
                        "kept" if public else "blurred",
                        doc,
                        m.value if public else None,
                    )
                )
    return hits, lines_read
