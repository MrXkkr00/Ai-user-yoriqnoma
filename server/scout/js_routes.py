"""Routes from the site's own JavaScript bundles and public source maps (ARCHITECTURE §7.6).

Only files of the site itself (same origin) are read, through ``safe_get``. Strings that
look like router paths are collected: ``path: "/app/orders"``, ``<Route path="...">``,
``to="/..."``, ``navigate("/...")``, ``href: "/..."``. API paths (``/api/...``) are kept
apart: they hint at entities, not pages.
"""

from __future__ import annotations

import json
import re
from urllib.parse import urljoin

from scout.urls import is_route_like, same_site

PATTERNS = [
    re.compile(r"""\bpath\s*:\s*["'`](/[^"'`\s]*)["'`]"""),
    re.compile(r"""<Route[^>]*?\bpath\s*=\s*\{?\s*["'`](/[^"'`\s]*)["'`]"""),
    re.compile(r"""\b(?:to|href)\s*[:=]\s*\{?\s*["'`](/[^"'`\s?#]*)["'`]"""),
    re.compile(r"""\b(?:navigate|push|replace|redirect)\(\s*["'`](/[^"'`\s?#]*)["'`]"""),
    re.compile(r"""\bjsx\(\s*\w+\s*,\s*\{\s*path\s*:\s*["'`](/[^"'`\s]*)["'`]"""),
]
API_PATTERN = re.compile(r"""["'`](/api/[A-Za-z0-9_\-/:{}$.]*)["'`]""")
MAP_PATTERN = re.compile(r"//[#@]\s*sourceMappingURL=([^\s'\"]+)")


def routes_from_js(text: str) -> set[str]:
    found: set[str] = set()
    for pattern in PATTERNS:
        for match in pattern.finditer(text):
            path = match.group(1).rstrip("/") or "/"
            if is_route_like(path) and not path.startswith("/api"):
                found.add(path)
    return found


def api_paths_from_js(text: str) -> set[str]:
    out = set()
    for match in API_PATTERN.finditer(text):
        path = re.sub(r"\$\{[^}]*\}", ":id", match.group(1)).rstrip("/")
        out.add(path)
    return out


def source_map_url(js_text: str, js_url: str) -> str | None:
    match = MAP_PATTERN.search(js_text[-2000:])
    if not match or match.group(1).startswith("data:"):
        return None
    url = urljoin(js_url, match.group(1))
    return url if same_site(url, js_url) else None


def routes_from_source_map(raw: str) -> tuple[set[str], set[str]]:
    """(page routes, api paths) from the original sources inside a source map."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return set(), set()
    pages: set[str] = set()
    apis: set[str] = set()
    for source in data.get("sourcesContent") or []:
        if isinstance(source, str):
            pages |= routes_from_js(source)
            apis |= api_paths_from_js(source)
    return pages, apis
