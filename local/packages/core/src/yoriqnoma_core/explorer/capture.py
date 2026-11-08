"""State snapshots (TZ FR-E9, FR-E10): replace, blur, screenshot, elements, SoM, aria.

Order matters: other people's data is replaced in the page BEFORE the screenshot; areas
that cannot be replaced (text in images, the role's foreign elements) are blurred in the
image before it is saved. Only then are the image, elements and aria text stored.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from PIL import Image
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page

from yoriqnoma_core.explorer import js
from yoriqnoma_core.explorer.ocr import OcrEngine, check_images
from yoriqnoma_core.explorer.pseudonymize import NEUTRAL_AVATAR, PrivacyLedger
from yoriqnoma_core.explorer.session import path_template
from yoriqnoma_core.explorer.som import blur_areas, draw_som
from yoriqnoma_core.safety.pii import NAME_HEADERS, find_pii, mask_text
from yoriqnoma_schemas import BBox, Element, HiddenArea, NetCall, State, Target

MAX_ELEMENTS = 80


def normalize_for_hash(aria: str) -> str:
    text = re.sub(r"\d+", "#", aria)
    return re.sub(r"\s+", " ", text)


@dataclass
class CaptureStats:
    ocr_images: int = 0
    ocr_lines: int = 0
    leftovers_masked: int = 0


@dataclass
class Capturer:
    run_dir: Path
    ledger: PrivacyLedger
    forbidden_patterns: list[str]
    max_height: int
    ocr: OcrEngine | None
    states: list[State] = field(default_factory=list)
    stats: CaptureStats = field(default_factory=CaptureStats)
    _counter: int = 0

    @property
    def images_dir(self) -> Path:
        path = self.run_dir / "capture" / "images"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def next_id(self) -> str:
        self._counter = max(self._counter, len(self.states)) + 1
        return f"s{self._counter:03d}"

    async def settle(self, page: Page) -> None:
        try:
            await page.wait_for_load_state("networkidle", timeout=6000)
        except PlaywrightError:
            pass
        try:
            await page.evaluate(
                "() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))"
            )
        except PlaywrightError:
            pass
        await asyncio.sleep(0.15)

    async def snapshot(
        self,
        page: Page,
        *,
        account: str,
        network: list[NetCall],
        flow_id: str | None = None,
        step_index: int | None = None,
        entity: str | None = None,
        entity_status: str | None = None,
        patched: bool = False,
        parent_id: str | None = None,
        trigger: str | None = None,
    ) -> State:
        await self.settle(page)
        names = sorted(NAME_HEADERS)
        args = {
            "nameHeaders": names,
            "editorialIsUgc": self.ledger.editorial_is_ugc,
            "ugcHeaders": sorted(self.ledger.ugc_headers),
        }
        scan: dict[str, Any] = await page.evaluate(js.PRIVACY_SCAN, args)
        # input hints («+998901234567» as a format example) are the site's own UI text
        self.ledger.public_values.update(str(p) for p in scan.get("placeholders", []) if p)
        decision = self.ledger.decide_dom(scan)
        if decision.nodes or decision.inputs or decision.avatar:
            await page.evaluate(
                js.APPLY_REPLACEMENTS,
                {
                    "nodes": decision.nodes,
                    "inputs": decision.inputs,
                    "neutralAvatar": NEUTRAL_AVATAR if decision.avatar else "",
                },
            )
        counts = self.ledger.take_counts()
        for key, n in decision.counts.items():
            counts[key] = counts.get(key, 0) + n

        hidden: list[HiddenArea] = []
        # what is still foreign after replacement cannot be shown: blur it
        rescan: dict[str, Any] = await page.evaluate(js.PRIVACY_SCAN, args)
        ignore = self.ledger.ignore()
        for node in rescan.get("nodes", []):
            if node["zone"] in {"org", "editorial"}:
                continue
            if find_pii(str(node["text"]), ignore):
                hidden.append(
                    HiddenArea(
                        x=node["x"],
                        y=node["y"],
                        w=node["w"],
                        h=node["h"],
                        reason="almashtirib bo'lmagan begona qiymat",
                    )
                )
                counts["other:blurred"] = counts.get("other:blurred", 0) + 1
        for link in await page.evaluate(js.FORBIDDEN_LINKS, self.forbidden_patterns):
            hidden.append(
                HiddenArea(
                    x=link["x"],
                    y=link["y"],
                    w=link["w"],
                    h=link["h"],
                    reason="maqsadli rolga tegishli emas",
                )
            )

        raw_elements: list[dict[str, Any]] = await page.evaluate(
            js.COLLECT_ELEMENTS, self.max_height
        )
        elements = self._elements(raw_elements, hidden)

        height = await page.evaluate("() => document.documentElement.scrollHeight")
        width = page.viewport_size["width"] if page.viewport_size else 1280
        clip_h = max(200, min(int(height), self.max_height))
        png = await page.screenshot(
            full_page=True, clip={"x": 0, "y": 0, "width": width, "height": clip_h}
        )
        image = Image.open(io.BytesIO(png)).convert("RGB")
        scale = image.width / width

        if self.ocr is not None and scan.get("images"):
            hits, lines = check_images(
                self.ocr, image, scan["images"], scale, ignore, self.ledger.is_org_email
            )
            self.stats.ocr_images += len(scan["images"])
            self.stats.ocr_lines += lines
            for hit in hits:
                key = f"{hit.zone}:{'kept' if hit.decision == 'kept' else 'blurred'}"
                counts[key] = counts.get(key, 0) + 1
                if hit.decision == "kept" and hit.value:
                    self.ledger.public_values.add(hit.value)
                else:
                    x0, y0, x1, y1 = hit.box
                    hidden.append(
                        HiddenArea(
                            x=x0,
                            y=y0,
                            w=x1 - x0,
                            h=y1 - y0,
                            reason=f"rasm ichidagi begona matn ({hit.kind}, OCR)",
                        )
                    )
        image = blur_areas(image, list(hidden), scale)

        aria = ""
        try:
            aria = await page.locator("body").aria_snapshot(timeout=5000)
        except PlaywrightError:
            aria = await page.evaluate(js.PAGE_TEXT)
        ignore = self.ledger.ignore()
        leftovers = find_pii(aria, ignore)
        if leftovers:
            aria = mask_text(aria, leftovers)
            self.stats.leftovers_masked += len(leftovers)
            counts["other:masked"] = counts.get("other:masked", 0) + len(leftovers)
        for el in elements:
            found = find_pii(el.name, ignore)
            if found:
                el.name = mask_text(el.name, found)

        state_id = self.next_id()
        clean = self.images_dir / f"{state_id}_clean.png"
        som = self.images_dir / f"{state_id}_som.png"
        image.save(clean, optimize=True)
        draw_som(image, elements, scale).save(som, optimize=True)

        url = page.url
        title = ""
        try:
            title = await page.title()
        except PlaywrightError:
            pass
        digest = hashlib.sha256(
            (path_template(urlsplit(url).path) + "\n" + normalize_for_hash(aria)).encode()
        ).hexdigest()[:16]
        state = State(
            id=state_id,
            hash=digest,
            url=url,
            title=title,
            flow_id=flow_id,
            step_index=step_index,
            account="guest" if account == "guest" else ("B" if account.endswith(":B") else "A"),
            images={"clean": f"images/{clean.name}", "som": f"images/{som.name}"},
            elements=elements,
            aria=aria[:20000],
            entity=entity,
            entity_status=entity_status,
            patched=patched,
            network=list(network)[-60:],
            hidden=hidden,
            substituted=sum(v for k, v in counts.items() if k.endswith(":substituted")),
            kept_public=sum(v for k, v in counts.items() if k.endswith(":kept")),
            privacy=counts,
            parent_id=parent_id,
            trigger=trigger,
            viewport=(width, clip_h),
        )
        self.states.append(state)
        return state

    @staticmethod
    def _elements(raw: list[dict[str, Any]], hidden: list[HiddenArea]) -> list[Element]:
        out: list[Element] = []
        for item in raw:
            box = BBox(x=item["x"], y=item["y"], w=item["w"], h=item["h"])
            if any(box.intersects(h) for h in hidden if h.reason.startswith("maqsadli")):
                continue
            name = str(item.get("name") or "")
            role = str(item.get("role") or "generic")
            if item.get("label"):
                target = Target(label=str(item["label"]))
            elif name and role not in {"generic"}:
                target = Target(role=role, name=name)
            elif item.get("testid"):
                target = Target(testid=str(item["testid"]))
            else:
                target = Target(css=str(item.get("css") or item.get("tag") or "body"))
            out.append(
                Element(
                    marker=len(out) + 1,
                    role=role,
                    name=name,
                    bbox=box,
                    selector=target,
                    kind=item.get("kind", "other"),
                    enabled=bool(item.get("enabled", True)),
                )
            )
            if len(out) >= MAX_ELEMENTS:
                break
        return out
