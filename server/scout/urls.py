"""URL helpers of the scout: same-site check and path templates (/x/123 -> /x/:id)."""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlsplit, urlunsplit

ID_RE = re.compile(r"^(\d+|[0-9a-fA-F]{8}-[0-9a-fA-F-]{27,}|[0-9a-fA-F]{24,})$")
# long hyphenated words with a number or many parts look like slugs of single items
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+){2,}$")
STATIC_SUFFIXES = (
    ".css",
    ".js",
    ".mjs",
    ".map",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".webp",
    ".ico",
    ".woff",
    ".woff2",
    ".ttf",
    ".pdf",
    ".zip",
    ".mp4",
    ".mp3",
    ".xml",
    ".txt",
    ".json",
)


def template_path(path: str) -> str:
    parts = []
    for segment in (path or "/").split("/"):
        if not segment:
            continue
        if ID_RE.match(segment):
            parts.append(":id")
        elif SLUG_RE.match(segment) and any(ch.isdigit() for ch in segment):
            parts.append(":slug")
        else:
            parts.append(segment)
    return "/" + "/".join(parts)


def origin(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}".lower()


def same_site(url: str, base: str) -> bool:
    return origin(url) == origin(base)


def clean_url(url: str, base: str) -> str | None:
    """Absolute same-site page URL without fragment, or None (other site, file, mailto)."""
    absolute = urljoin(base, url.strip())
    parts = urlsplit(absolute)
    if parts.scheme not in {"http", "https"} or not same_site(absolute, base):
        return None
    if parts.path.lower().endswith(STATIC_SUFFIXES):
        return None
    return urlunsplit((parts.scheme, parts.netloc, parts.path or "/", parts.query, ""))


def path_of(url: str) -> str:
    return urlsplit(url).path or "/"


def is_route_like(path: str) -> bool:
    """A string from JS that looks like an app route ("/app/orders/:id", not "/api/x.js")."""
    if not path.startswith("/") or path.startswith("//") or len(path) > 120:
        return False
    if path.lower().endswith(STATIC_SUFFIXES) or " " in path:
        return False
    return bool(re.fullmatch(r"/[A-Za-z0-9_\-/:.*]*", path))
