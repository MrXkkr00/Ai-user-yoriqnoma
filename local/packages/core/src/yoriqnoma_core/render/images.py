"""Manual images (TZ FR-R1), drawn separately from the model's SoM image.

Crop around the step's target with context, a soft spotlight (the rest stays readable),
a numbered circle and an arrow. Blur only where the capture marked hidden areas
(FR-E10; the capture image is already blurred there, this is a second safety net).
Patched states get a «Namuna ko'rinish» label.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance

from yoriqnoma_core.explorer.som import blur_areas, font
from yoriqnoma_schemas import BBox, State

ACCENT = (230, 57, 70)
PAD_X, PAD_Y = 260, 170


@dataclass
class RenderedImage:
    png: Path
    webp: Path
    width: int
    height: int


def _union(boxes: list[BBox]) -> BBox:
    x0 = min(b.x for b in boxes)
    y0 = min(b.y for b in boxes)
    x1 = max(b.x + b.w for b in boxes)
    y1 = max(b.y + b.h for b in boxes)
    return BBox(x=x0, y=y0, w=x1 - x0, h=y1 - y0)


def render_step_image(
    source: Path,
    state: State,
    markers: list[int],
    out_base: Path,
    patched_label: str | None = None,
) -> RenderedImage:
    with Image.open(source) as raw:
        img = raw.convert("RGB")
    scale = img.width / max(1, state.viewport[0])
    if state.hidden:
        img = blur_areas(img, list(state.hidden), scale)
    targets = [el.bbox for el in state.elements if el.marker in markers]
    if targets:
        box = _union(targets)
        x0 = max(0, int((box.x - PAD_X) * scale))
        y0 = max(0, int((box.y - PAD_Y) * scale))
        x1 = min(img.width, int((box.x + box.w + PAD_X) * scale))
        y1 = min(img.height, int((box.y + box.h + PAD_Y) * scale))
        if x1 - x0 < 640 * scale:  # keep enough context
            grow = int((640 * scale - (x1 - x0)) / 2)
            x0, x1 = max(0, x0 - grow), min(img.width, x1 + grow)
        dim = ImageEnhance.Brightness(img).enhance(0.72)
        mask = Image.new("L", img.size, 0)
        mdraw = ImageDraw.Draw(mask)
        for b in targets:
            mdraw.rounded_rectangle(
                (
                    int((b.x - 6) * scale),
                    int((b.y - 6) * scale),
                    int((b.x + b.w + 6) * scale),
                    int((b.y + b.h + 6) * scale),
                ),
                radius=int(8 * scale),
                fill=255,
            )
        img = Image.composite(img, dim, mask)
        draw = ImageDraw.Draw(img)
        fnt = font(int(18 * scale))
        for n, b in zip(markers, targets, strict=False):
            bx0, by0 = int((b.x - 6) * scale), int((b.y - 6) * scale)
            bx1, by1 = int((b.x + b.w + 6) * scale), int((b.y + b.h + 6) * scale)
            draw.rounded_rectangle(
                (bx0, by0, bx1, by1),
                radius=int(8 * scale),
                outline=ACCENT,
                width=max(2, int(3 * scale)),
            )
            r = int(15 * scale)
            cx, cy = max(r + 2, bx0 - r - 6), max(r + 2, by0 - 2)
            # arrow from the circle to the element
            draw.line(
                (cx + r, cy, bx0, (by0 + by1) // 2), fill=ACCENT, width=max(2, int(2 * scale))
            )
            draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=ACCENT)
            label = str(n)
            tw = draw.textlength(label, font=fnt)
            draw.text((cx - tw / 2, cy - r * 0.62), label, fill="white", font=fnt)
        img = img.crop((x0, y0, x1, y1))
    else:
        max_h = int(900 * scale)
        if img.height > max_h:
            img = img.crop((0, 0, img.width, max_h))
    if patched_label:
        draw = ImageDraw.Draw(img)
        fnt = font(int(16 * scale))
        tw = int(draw.textlength(patched_label, font=fnt)) + 20
        draw.rectangle(
            (img.width - tw - 10, 10, img.width - 10, 10 + int(28 * scale)), fill=(255, 196, 0)
        )
        draw.text((img.width - tw, 14), patched_label, fill=(30, 30, 30), font=fnt)
    out_base.parent.mkdir(parents=True, exist_ok=True)
    png = out_base.with_suffix(".png")
    webp = out_base.with_suffix(".webp")
    img.save(png, optimize=True)
    img.save(webp, quality=82)
    return RenderedImage(png, webp, img.width, img.height)
