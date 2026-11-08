"""Animated GIF per manual article (T30): the article's step images, one after another.

Frames are the manual's own step images (already annotated, blurred where FR-E10 says),
scaled to one width and padded to one height, with the step number in the corner.
"""

from __future__ import annotations

import re
from pathlib import Path

from PIL import Image, ImageDraw

from yoriqnoma_core.explorer.som import font

WIDTH = 960
FRAME_MS = 2200
MAX_FRAMES = 12


def _frame(path: Path, n: int) -> Image.Image:
    with Image.open(path) as raw:
        img = raw.convert("RGB")
    if img.width != WIDTH:
        size = (WIDTH, max(1, round(img.height * WIDTH / img.width)))
        img = img.resize(size, Image.Resampling.LANCZOS)
    draw = ImageDraw.Draw(img)
    label = f"{n}-qadam"
    fnt = font(20)
    tw = int(draw.textlength(label, font=fnt))
    top = img.height - 44  # bottom-left: the page's own menu stays visible
    draw.rounded_rectangle((10, top, tw + 34, top + 34), radius=8, fill=(230, 57, 70))
    draw.text((22, top + 5), label, fill="white", font=fnt)
    return img


def build_gif(frames: list[tuple[int, Path]], out: Path) -> Path | None:
    """Frames: (step number, image file). None when there is less than two images."""
    usable = [(n, p) for n, p in frames if p.is_file()][:MAX_FRAMES]
    if len(usable) < 2:
        return None
    images = [_frame(p, n) for n, p in usable]
    height = max(i.height for i in images)
    padded = []
    for img in images:
        canvas = Image.new("RGB", (WIDTH, height), (255, 255, 255))
        canvas.paste(img, (0, 0))
        padded.append(canvas.convert("P", palette=Image.Palette.ADAPTIVE, colors=200))
    out.parent.mkdir(parents=True, exist_ok=True)
    padded[0].save(
        out,
        save_all=True,
        append_images=padded[1:],
        duration=FRAME_MS,
        loop=0,
        optimize=True,
    )
    return out


def gif_name(flow_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", flow_id) + ".gif"
