"""PDF from the HTML (TZ FR-R3): Playwright page.pdf, A4, page numbers. No WeasyPrint."""

from __future__ import annotations

import asyncio
import html
from pathlib import Path

from playwright.async_api import async_playwright

from yoriqnoma_schemas import Manual


async def _pdf(index: Path, out: Path, title: str) -> Path:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page()
        await page.goto(index.resolve().as_uri())
        await page.emulate_media(media="print")
        await page.wait_for_load_state("load")
        await page.pdf(
            path=str(out),
            format="A4",
            print_background=True,
            display_header_footer=True,
            header_template=(
                "<div style='font-size:8px;width:100%;text-align:center;color:#888'>"
                f"{html.escape(title)}</div>"
            ),
            footer_template=(
                "<div style='font-size:8px;width:100%;text-align:center;color:#888'>"
                "<span class='pageNumber'></span> / <span class='totalPages'></span></div>"
            ),
            margin={"top": "18mm", "bottom": "16mm", "left": "14mm", "right": "14mm"},
        )
        await browser.close()
    return out


def html_to_pdf(index: Path, out: Path, manual: Manual) -> Path:
    title = f"{manual.project} — «{manual.role_label}» uchun yo'riqnoma"
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_pdf(index, out, title))
    # called from inside an event loop: run in a helper thread with its own loop
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(1) as pool:
        return pool.submit(lambda: asyncio.run(_pdf(index, out, title))).result()
