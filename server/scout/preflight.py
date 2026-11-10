"""Preflight of mode B (ARCHITECTURE §7.6): what the site is before any browser opens.

url_guard; whether the domain is verified (otherwise passive); robots.txt; sitemap.xml
(an index too, a few levels, a limited number of URLs); language and technology hints.
Every request goes through ``safe_get``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urljoin
from xml.etree import ElementTree

import httpx

from security.robots import Robots, fetch_robots
from security.ssrf import check_public_url, safe_get
from yoriqnoma_core.discovery.urls import clean_url, origin
from yoriqnoma_core.safety.url_guard import UrlBlocked

TECH_HINTS = {
    "react": re.compile(r"react|__NEXT_DATA__|data-reactroot", re.I),
    "next.js": re.compile(r"__NEXT_DATA__|/_next/", re.I),
    "vue": re.compile(r"data-v-[0-9a-f]{6,}|__vue__|vue(\.runtime)?(\.min)?\.js", re.I),
    "django": re.compile(r"csrfmiddlewaretoken", re.I),
    "laravel": re.compile(r"laravel_session|XSRF-TOKEN", re.I),
    "wordpress": re.compile(r"wp-content|wp-json", re.I),
}


@dataclass
class Preflight:
    base_url: str
    robots: Robots
    sitemap_urls: list[str] = field(default_factory=list)
    lang: str = ""
    tech: list[str] = field(default_factory=list)
    generator: str = ""
    passive: bool = False


class _Head(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.lang = ""
        self.generator = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        data = {k.lower(): (v or "") for k, v in attrs}
        if tag == "html" and not self.lang:
            self.lang = data.get("lang", "")
        if tag == "meta" and data.get("name", "").lower() == "generator":
            self.generator = data.get("content", "")


def parse_sitemap(xml: str) -> tuple[list[str], list[str]]:
    """(page URLs, nested sitemap URLs)."""
    try:
        root = ElementTree.fromstring(xml)  # size-limited; expat refuses entity expansion bombs
    except ElementTree.ParseError:
        return [], []
    pages: list[str] = []
    nested: list[str] = []
    for loc in root.iter():
        if not loc.tag.endswith("loc") or not loc.text:
            continue
        text = loc.text.strip()
        (nested if text.endswith(".xml") or "sitemap" in text.lower() else pages).append(text)
    return pages, nested


def _get_text(url: str, max_bytes: int) -> str | None:
    try:
        answer = safe_get(url, max_bytes=max_bytes)
    except (UrlBlocked, httpx.HTTPError, OSError, ValueError):
        return None
    return answer.text if answer.status == 200 else None


def sitemap_pages(base_url: str, robots: Robots, limit: int = 200) -> list[str]:
    queue = list(robots.sitemaps) or [urljoin(origin(base_url) + "/", "sitemap.xml")]
    seen: set[str] = set()
    pages: list[str] = []
    while queue and len(seen) < 5 and len(pages) < limit:
        url = queue.pop(0)
        if url in seen or not url.lower().startswith(origin(base_url)):
            continue
        seen.add(url)
        text = _get_text(url, 2 * 1024 * 1024)
        if not text:
            continue
        found, nested = parse_sitemap(text)
        pages.extend(p for p in (clean_url(u, base_url) for u in found) if p)
        queue.extend(n for n in nested if n.startswith(origin(base_url)))
    return pages[:limit]


def preflight(base_url: str, verified: bool) -> Preflight:
    check_public_url(base_url)
    robots = fetch_robots(base_url)
    home = _get_text(base_url, 2 * 1024 * 1024) or ""
    head = _Head()
    try:
        head.feed(home[:200_000])
    except Exception:  # noqa: BLE001 - broken HTML: no hints, nothing else breaks
        pass
    tech = [name for name, rx in TECH_HINTS.items() if rx.search(home[:500_000])]
    return Preflight(
        base_url=base_url,
        robots=robots,
        sitemap_urls=sitemap_pages(base_url, robots),
        lang=head.lang,
        tech=tech,
        generator=head.generator,
        passive=not verified,
    )
