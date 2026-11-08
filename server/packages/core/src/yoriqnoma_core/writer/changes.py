"""Incremental update (T30): what changed since the previous run of the same role.

Screens are compared by state hash (the DOM hash without numbers, times and tokens), flows
by their result and the hashes of their screens, articles by their text. Unchanged screens
give the same LLM prompts, so their texts come from the writer's cache and are not paid for
again; ``changelog.md`` lists what is new, gone or different.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from yoriqnoma_core.explorer.session import path_template
from yoriqnoma_schemas import Article, CaptureRun, Manual, State, load_json


@dataclass
class Changes:
    added_flows: list[str] = field(default_factory=list)
    removed_flows: list[str] = field(default_factory=list)
    changed_screens: list[str] = field(default_factory=list)  # flows whose screens changed
    changed_texts: list[str] = field(default_factory=list)  # articles whose text changed
    status_changes: list[str] = field(default_factory=list)  # "flow: verified -> failed"
    added_pages: list[str] = field(default_factory=list)
    removed_pages: list[str] = field(default_factory=list)
    unchanged: int = 0
    coverage: tuple[float, float] = (0.0, 0.0)

    @property
    def empty(self) -> bool:
        return not (
            self.added_flows
            or self.removed_flows
            or self.changed_screens
            or self.changed_texts
            or self.status_changes
            or self.added_pages
            or self.removed_pages
        )


def _articles(manual: Manual) -> dict[str, Article]:
    return {a.flow_id: a for s in manual.sections for a in s.articles}


def signature(state: State) -> str:
    """What the screen offers, without its data: page template + controls.

    The DOM hash changes with every run's test accounts and fakes; this does not.
    """
    controls = sorted(
        {
            f"{e.kind}:{re.sub(r'[0-9]+', '#', e.name.lower())}"
            for e in state.elements
            if e.kind != "other" and "@" not in e.name
        }
    )
    raw = path_template(urlsplit(state.url).path) + "|" + "|".join(controls)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _screens(capture: CaptureRun) -> dict[str, list[str]]:
    sigs = {s.id: signature(s) for s in capture.states}
    return {f.flow_id: [sigs.get(i, "") for i in f.state_ids] for f in capture.flows}


def _pages(capture: CaptureRun) -> set[str]:
    return {path_template(urlsplit(s.url).path) for s in capture.states if not s.patched}


def _text(article: Article) -> str:
    return "\n".join([article.title, article.purpose, *(s.text for s in article.steps)])


def compare(prev_dir: Path, run_dir: Path) -> Changes:
    old_cap = load_json(prev_dir / "capture" / "capture.json", CaptureRun)
    new_cap = load_json(run_dir / "capture" / "capture.json", CaptureRun)
    old_man = load_json(prev_dir / "manual.json", Manual)
    new_man = load_json(run_dir / "manual.json", Manual)
    changes = Changes(
        coverage=(
            old_man.coverage.percent.get("total", 0.0),
            new_man.coverage.percent.get("total", 0.0),
        )
    )
    old_flows = {f.flow_id: f.status for f in old_cap.flows}
    new_flows = {f.flow_id: f.status for f in new_cap.flows}
    changes.added_flows = sorted(set(new_flows) - set(old_flows))
    changes.removed_flows = sorted(set(old_flows) - set(new_flows))
    old_screens, new_screens = _screens(old_cap), _screens(new_cap)
    old_articles, new_articles = _articles(old_man), _articles(new_man)
    for flow in sorted(set(old_flows) & set(new_flows)):
        if old_flows[flow] != new_flows[flow]:
            changes.status_changes.append(f"{flow}: {old_flows[flow]} -> {new_flows[flow]}")
        screens_changed = old_screens.get(flow) != new_screens.get(flow)
        if screens_changed:
            changes.changed_screens.append(flow)
        old_a, new_a = old_articles.get(flow), new_articles.get(flow)
        text_changed = (old_a is None) != (new_a is None) or (
            old_a is not None and new_a is not None and _text(old_a) != _text(new_a)
        )
        if text_changed:
            changes.changed_texts.append(flow)
        if not screens_changed and not text_changed and old_flows[flow] == new_flows[flow]:
            changes.unchanged += 1
    old_pages, new_pages = _pages(old_cap), _pages(new_cap)
    changes.added_pages = sorted(new_pages - old_pages)
    changes.removed_pages = sorted(old_pages - new_pages)
    return changes


def render_changelog(
    changes: Changes, prev_name: str, run_name: str, titles: dict[str, str]
) -> str:
    def name(flow: str) -> str:
        return f"{titles.get(flow, flow)} (`{flow}`)"

    lines = [
        f"# O'zgarishlar: {prev_name} → {run_name}",
        "",
        f"- O'zgarmagan vazifalar: {changes.unchanged} ta",
        f"- Qamrov: {changes.coverage[0]}% → {changes.coverage[1]}%",
        "",
    ]
    if changes.empty:
        lines.append("Saytda yo'riqnomaga ta'sir qiladigan o'zgarish topilmadi.")
        return "\n".join(lines) + "\n"
    blocks = [
        ("Yangi vazifalar", [name(f) for f in changes.added_flows]),
        ("Olib tashlangan vazifalar", [name(f) for f in changes.removed_flows]),
        ("Ekrani o'zgargan vazifalar", [name(f) for f in changes.changed_screens]),
        ("Matni yangilangan maqolalar", [name(f) for f in changes.changed_texts]),
        ("Natijasi o'zgargan vazifalar", changes.status_changes),
        ("Yangi sahifalar", [f"`{p}`" for p in changes.added_pages]),
        ("Endi ko'rinmaydigan sahifalar", [f"`{p}`" for p in changes.removed_pages]),
    ]
    for title, items in blocks:
        if items:
            lines += [f"## {title}", "", *[f"- {i}" for i in items], ""]
    return "\n".join(lines)


def write_changelog(prev_dir: Path, run_dir: Path) -> Path | None:
    """``run_dir/changelog.md`` against ``prev_dir``; None when the previous run is unusable."""
    needed = ("manual.json", "capture/capture.json")
    if not all((prev_dir / n).is_file() for n in needed):
        return None
    changes = compare(prev_dir, run_dir)
    manual = load_json(run_dir / "manual.json", Manual)
    titles = {a.flow_id: a.title for a in _articles(manual).values()}
    text = render_changelog(changes, prev_dir.name, run_dir.name, titles)
    out = run_dir / "changelog.md"
    out.write_text(text, encoding="utf-8")
    return out
