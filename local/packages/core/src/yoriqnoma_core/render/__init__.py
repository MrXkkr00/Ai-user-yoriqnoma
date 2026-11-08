"""Renderer (TZ FR-R): offline HTML with search, PDF via Playwright, DOCX via python-docx."""

from __future__ import annotations

import html as html_lib
import json
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from yoriqnoma_core.render.images import RenderedImage, render_step_image
from yoriqnoma_core.writer.templates_uz import PATCHED_NOTE
from yoriqnoma_schemas import CaptureRun, Manual, State, load_json

TEMPLATES = Path(__file__).parent / "templates"
DEFAULT_FORMATS = {"html", "pdf", "docx"}
FORMATS = DEFAULT_FORMATS | {"tour", "gif"}  # tour: Driver.js; gif: one per article


@dataclass
class RenderResult:
    out_dir: Path
    files: dict[str, Path] = field(default_factory=dict)
    images: int = 0
    warnings: list[str] = field(default_factory=list)


def anchor(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "a"


class ImageCache:
    def __init__(self, capture_dir: Path, states: dict[str, State], out_dir: Path) -> None:
        self.capture_dir = capture_dir
        self.states = states
        self.out_dir = out_dir
        self.done: dict[tuple[str, tuple[int, ...]], RenderedImage] = {}

    def get(
        self, state_id: str | None, image: str | None, markers: list[int], patched: bool = False
    ) -> dict[str, Any] | None:
        if not image:
            return None
        state = self.states.get(state_id or "") or next(
            (s for s in self.states.values() if image in s.images.values()), None
        )
        source = self.capture_dir / image
        if state is None or not source.is_file():
            return None
        key = (state.id, tuple(markers))
        if key not in self.done:
            name = f"{state.id}" + ("_" + "-".join(map(str, markers)) if markers else "")
            label = "Namuna ko'rinish" if patched or state.patched else None
            self.done[key] = render_step_image(source, state, markers, self.out_dir / name, label)
        img = self.done[key]
        return {
            "png": f"images/{img.png.name}",
            "webp": f"images/{img.webp.name}",
            "width": min(round(img.width / img.scale), 860),
            "path": img.png,
        }


def build_context(
    manual: Manual, capture: CaptureRun, capture_dir: Path, html_dir: Path
) -> tuple[dict[str, Any], ImageCache]:
    images = ImageCache(capture_dir, {s.id: s for s in capture.states}, html_dir / "images")
    sections = []
    for s in manual.sections:
        articles = []
        for a in s.articles:
            steps = [
                {"n": st.n, "text": st.text, "img": images.get(st.state_id, st.image, st.markers)}
                for st in a.steps
            ]
            statuses = []
            for row in a.statuses:
                state = next(
                    (x for x in capture.states if x.images.get("clean") == row.image), None
                )
                statuses.append(
                    {
                        **row.model_dump(),
                        "img": images.get(
                            state.id if state else None, row.image, [], row.patched_image
                        ),
                    }
                )
            notes = list(a.notes)
            if any(r["patched_image"] for r in statuses) and PATCHED_NOTE not in notes:
                notes.append(PATCHED_NOTE)
            articles.append(
                {
                    **a.model_dump(),
                    "anchor": anchor(a.flow_id),
                    "steps": steps,
                    "statuses": statuses,
                    "notes": notes,
                }
            )
        sections.append({**s.model_dump(), "articles": articles})
    ctx = {
        "manual": manual,
        "sections": sections,
        "reference": manual.reference,
        "faq": manual.faq,
        "generated": manual.generated_at.strftime("%Y-%m-%d %H:%M"),
        "coverage_total": manual.coverage.percent.get("total", 0),
    }
    return ctx, images


def search_index(ctx: dict[str, Any]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for s in ctx["sections"]:
        out.append({"id": s["id"], "title": s["title"], "text": s["intro"]})
        for a in s["articles"]:
            text = " ".join([a["purpose"], *[st["text"] for st in a["steps"]], *a["notes"]])
            out.append({"id": a["anchor"], "title": a["title"], "text": text})
    return out


def render_html(
    manual: Manual, capture: CaptureRun, capture_dir: Path, out_dir: Path
) -> tuple[Path, dict[str, Any], ImageCache]:
    html_dir = out_dir / "html"
    if html_dir.exists():
        shutil.rmtree(html_dir)
    (html_dir / "assets").mkdir(parents=True)
    ctx, images = build_context(manual, capture, capture_dir, html_dir)
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES)), autoescape=select_autoescape(["html", "j2"])
    )
    index = html_dir / "index.html"
    index.write_text(env.get_template("manual.html.j2").render(**ctx), encoding="utf-8")
    shutil.copy(TEMPLATES / "style.css", html_dir / "assets" / "style.css")
    shutil.copy(TEMPLATES / "search.js", html_dir / "assets" / "search.js")
    entries = search_index(ctx)
    (html_dir / "assets" / "search_index.json").write_text(
        json.dumps(entries, ensure_ascii=False), encoding="utf-8"
    )
    (html_dir / "assets" / "search_index.js").write_text(
        "window.SEARCH_INDEX = " + json.dumps(entries, ensure_ascii=False) + ";\n", encoding="utf-8"
    )
    return index, ctx, images


def render_coverage(manual: Manual, out_dir: Path) -> Path:
    rows = "".join(
        f"<tr class='{'ok' if i.covered else 'no'}'><td>{html_lib.escape(i.kind)}</td>"
        f"<td>{html_lib.escape(i.key)}</td><td>{'ha' if i.covered else 'yo‘q'}</td>"
        f"<td>{html_lib.escape(i.reason or '')}</td></tr>"
        for i in sorted(manual.coverage.items, key=lambda x: (x.covered, x.kind, x.key))
    )
    percent = "".join(f"<li>{k}: <b>{v}%</b></li>" for k, v in manual.coverage.percent.items())
    page = (
        "<!doctype html><html lang='uz'><meta charset='utf-8'>"
        f"<title>Qamrov hisoboti — {html_lib.escape(manual.project)}</title>"
        "<style>body{font:15px/1.5 system-ui,sans-serif;margin:2rem;max-width:980px}"
        "table{border-collapse:collapse;width:100%}td,th{border:1px solid #ddd;padding:4px 8px}"
        ".no{background:#fff1f0}</style>"
        f"<h1>Qamrov hisoboti: {html_lib.escape(manual.role_label)}</h1><ul>{percent}</ul>"
        "<table><tr><th>Turi</th><th>Kalit</th><th>Qamralgan</th><th>Sabab</th></tr>"
        f"{rows}</table><p><a href='html/index.html'>Yo'riqnomaga qaytish</a></p></html>"
    )
    path = out_dir / "coverage_report.html"
    path.write_text(page, encoding="utf-8")
    (out_dir / "html" / "coverage_report.html").write_text(
        page.replace("href='html/index.html'", "href='index.html'"), encoding="utf-8"
    )
    return path


def _gifs(ctx: dict[str, Any], gif_dir: Path) -> int:
    from yoriqnoma_core.render.gif import build_gif, gif_name

    if gif_dir.exists():
        shutil.rmtree(gif_dir)
    made = 0
    for section in ctx["sections"]:
        if section["stage"] in {"reference", "faq", "unverified"}:
            continue
        for article in section["articles"]:
            frames = [(st["n"], st["img"]["path"]) for st in article["steps"] if st["img"]]
            if build_gif(frames, gif_dir / gif_name(article["flow_id"])) is not None:
                made += 1
    return made


def build(run_dir: Path, formats: set[str] | None = None) -> RenderResult:
    """Render dist/ for a run folder that has manual.json and capture/."""
    wanted = (formats or DEFAULT_FORMATS) & FORMATS
    manual = load_json(run_dir / "manual.json", Manual)
    capture = load_json(run_dir / "capture" / "capture.json", CaptureRun)
    out_dir = run_dir / "dist"
    out_dir.mkdir(parents=True, exist_ok=True)
    result = RenderResult(out_dir)
    index, ctx, images = render_html(manual, capture, run_dir / "capture", out_dir)
    result.files["html"] = index
    result.files["coverage"] = render_coverage(manual, out_dir)
    result.images = len(images.done)
    if "pdf" in wanted:
        from yoriqnoma_core.render.pdf import html_to_pdf

        result.files["pdf"] = html_to_pdf(index, out_dir / "manual.pdf", manual)
    if "docx" in wanted:
        from yoriqnoma_core.render.docx import build_docx

        result.files["docx"] = build_docx(manual, ctx, out_dir / "manual.docx")
    if "tour" in wanted:
        from yoriqnoma_core.render.tour import build_tours

        result.files["tour"] = build_tours(manual, capture, out_dir)
    if "gif" in wanted:
        made = _gifs(ctx, out_dir / "gif")
        if made:
            result.files["gif"] = out_dir / "gif"
    changelog = run_dir / "changelog.md"
    if changelog.is_file():  # incremental update (T30)
        result.files["changelog"] = Path(shutil.copy(changelog, out_dir / "changelog.md"))
    (out_dir / "render_info.json").write_text(
        json.dumps(
            {
                "rendered_at": datetime.now().isoformat(timespec="seconds"),
                "files": {k: v.name for k, v in result.files.items()},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return result
