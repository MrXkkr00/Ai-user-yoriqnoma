"""robots.txt (TZ SEC-14), fetched through ``safe_get`` with our User-Agent.

Mode B's crawler never visits a disallowed path. In passive mode (unverified domain) the
disallowed paths are also added to the explorer's ``deny_paths``. A missing or broken
robots.txt allows everything (the usual reading); a 401/403 answer disallows everything.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx
from django.conf import settings

from security.ssrf import safe_get
from yoriqnoma_core.safety.url_guard import UrlBlocked


@dataclass
class Robots:
    parser: RobotFileParser | None = None
    disallow_all: bool = False
    sitemaps: list[str] = field(default_factory=list)
    disallowed_paths: list[str] = field(default_factory=list)

    def allowed(self, url: str) -> bool:
        if self.disallow_all:
            return False
        if self.parser is None:
            return True
        return self.parser.can_fetch(settings.YORIQNOMA_USER_AGENT, url)


def parse_robots(text: str, status: int = 200) -> Robots:
    if status in {401, 403}:
        return Robots(disallow_all=True)
    if status >= 400:
        return Robots()
    parser = RobotFileParser()
    lines = text.splitlines()
    parser.parse(lines)
    sitemaps = [ln.split(":", 1)[1].strip() for ln in lines if ln.lower().startswith("sitemap:")]
    disallowed: list[str] = []
    applies = False
    for raw in lines:
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, value = (p.strip() for p in line.split(":", 1))
        if key.lower() == "user-agent":
            applies = value == "*" or value.lower().startswith("ai-user-yoriqnoma")
        elif key.lower() == "disallow" and applies and value:
            disallowed.append(value)
    return Robots(parser=parser, sitemaps=sitemaps, disallowed_paths=sorted(set(disallowed)))


def fetch_robots(base_url: str) -> Robots:
    parts = urlsplit(base_url)
    url = f"{parts.scheme}://{parts.netloc}/robots.txt"
    try:
        answer = safe_get(url, max_bytes=512 * 1024)
    except (UrlBlocked, httpx.HTTPError, OSError, ValueError):
        return Robots()
    return parse_robots(answer.text, answer.status)


def deny_globs(robots: Robots) -> list[str]:
    """Disallowed paths as ``deny_paths`` globs ("/private" -> "/private*")."""
    out = []
    for path in robots.disallowed_paths:
        clean = path.split("$")[0]
        out.append(clean if clean.endswith("*") else clean + "*")
    return out
