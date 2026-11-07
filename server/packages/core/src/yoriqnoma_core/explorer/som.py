"""Set-of-Mark image for the model: numbered markers and thin frames over the clean image."""

from __future__ import annotations

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from yoriqnoma_schemas import BBox, Element

PALETTE = [
    (220, 38, 38),
    (37, 99, 235),
    (22, 163, 74),
    (217, 119, 6),
    (147, 51, 234),
    (8, 145, 178),
    (219, 39, 119),
    (77, 124, 15),
]


def font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # very old Pillow
        return ImageFont.load_default()


def blur_areas(image: Image.Image, boxes: list[BBox], scale: float) -> Image.Image:
    """Make each box unreadable: pixelate, then blur (FR-E10 «xiralashtirish»)."""
    out = image.copy()
    for b in boxes:
        x0, y0 = max(0, int(b.x * scale)), max(0, int(b.y * scale))
        x1, y1 = min(out.width, int((b.x + b.w) * scale)), min(out.height, int((b.y + b.h) * scale))
        if x1 - x0 < 2 or y1 - y0 < 2:
            continue
        region = out.crop((x0, y0, x1, y1))
        small = region.resize((max(1, (x1 - x0) // 12), max(1, (y1 - y0) // 12)))
        region = small.resize(region.size, Image.Resampling.NEAREST).filter(
            ImageFilter.GaussianBlur(6)
        )
        out.paste(region, (x0, y0))
    return out


def draw_som(image: Image.Image, elements: list[Element], scale: float) -> Image.Image:
    out = image.convert("RGB").copy()
    draw = ImageDraw.Draw(out)
    fnt = font(max(12, int(13 * scale)))
    placed: list[tuple[int, int, int, int]] = []
    for el in elements:
        color = PALETTE[el.marker % len(PALETTE)]
        b = el.bbox
        x0, y0 = int(b.x * scale), int(b.y * scale)
        x1, y1 = int((b.x + b.w) * scale), int((b.y + b.h) * scale)
        draw.rectangle((x0, y0, x1, y1), outline=color, width=max(1, int(scale)))
        label = str(el.marker)
        tw = int(draw.textlength(label, font=fnt)) + 8
        th = int(16 * scale)
        lx, ly = x0, max(0, y0 - th)
        for _ in range(4):  # avoid covering a previous label
            box = (lx, ly, lx + tw, ly + th)
            if not any(
                not (box[2] <= p[0] or box[0] >= p[2] or box[3] <= p[1] or box[1] >= p[3])
                for p in placed
            ):
                break
            lx += tw + 2
        placed.append((lx, ly, lx + tw, ly + th))
        draw.rectangle((lx, ly, lx + tw, ly + th), fill=color)
        draw.text((lx + 4, ly + 1), label, fill=(255, 255, 255), font=fnt)
    return out
