"""SSRF protection on the server (TZ SEC-10, CLAUDE.md rule 6): ``allow_private=False`` always.

* ``check_public_url`` — job and domain URLs at creation time (every DNS answer checked).
* ``safe_get`` — the server's own HTTP requests (domain verification, robots.txt,
  sitemap, JS bundles and source maps in mode B). Every hop of a redirect is checked
  again, and the connection goes to the very address that was checked (DNS pinning):
  a second, different DNS answer (DNS rebinding) is never used. TLS still verifies the
  certificate for the host name (SNI).
* The browser is guarded in core: ``explorer.firewall`` checks every request's host with
  ``url_guard.HostGuard``. The worker's network egress rules are the last line
  (docs/DEPLOY.md).
"""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx
from django.conf import settings

from yoriqnoma_core.safety.url_guard import UrlBlocked, check_url, parse_ip_literal

Resolver = Callable[[str], list[str]]
REDIRECTS = {301, 302, 303, 307, 308}


def system_resolver(host: str) -> list[str]:
    infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    return sorted({str(info[4][0]) for info in infos})


# Tests replace this (no real DNS in unit tests).
resolver: Resolver = system_resolver


def private_allowed(url: str) -> bool:
    """Only the e2e test site (settings.YORIQNOMA_PRIVATE_ALLOWLIST, empty in prod)."""
    host = (urlsplit(url).hostname or "").lower()
    allow = [h.lower() for h in getattr(settings, "YORIQNOMA_PRIVATE_ALLOWLIST", [])]
    return bool(host) and host in allow


def check_public_url(url: str) -> str:
    """The URL if the server may visit it, else ``UrlBlocked`` with an Uzbek reason."""
    return check_url(url, allow_private=private_allowed(url), resolver=lambda h: resolver(h))


def resolve_checked(url: str) -> list[str]:
    """Check the URL and return the addresses that were checked (to connect to them)."""
    host = urlsplit(url).hostname or ""
    literal = parse_ip_literal(host)
    if literal is not None:
        check_url(url, allow_private=private_allowed(url))
        return [str(literal)]
    seen: list[str] = []

    def remember(h: str) -> list[str]:
        answers = resolver(h)
        seen.extend(answers)
        return answers

    check_url(url, allow_private=private_allowed(url), resolver=remember)
    return seen


@dataclass
class Fetched:
    url: str
    status: int
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes = b""

    @property
    def text(self) -> str:
        charset = "utf-8"
        ctype = self.headers.get("content-type", "")
        if "charset=" in ctype:
            charset = ctype.split("charset=", 1)[1].split(";")[0].strip() or "utf-8"
        return self.body.decode(charset, errors="replace")


def _pinned(url: str, address: str) -> tuple[str, str]:
    """URL that connects to ``address`` and the Host header of the original URL."""
    parts = urlsplit(url)
    host = parts.hostname or ""
    ip = ipaddress.ip_address(address)
    netloc = f"[{ip}]" if ip.version == 6 else str(ip)
    if parts.port:
        netloc += f":{parts.port}"
    host_header = host if not parts.port else f"{host}:{parts.port}"
    path = parts.path or "/"
    return urlunsplit((parts.scheme, netloc, path, parts.query, "")), host_header


def safe_get(
    url: str,
    *,
    max_bytes: int = 2 * 1024 * 1024,
    max_redirects: int = 3,
    timeout_s: float = 10.0,
    transport: httpx.BaseTransport | None = None,
) -> Fetched:
    """GET with SSRF checks on every hop, DNS pinning and a size limit."""
    current = url
    with httpx.Client(transport=transport, timeout=timeout_s, follow_redirects=False) as client:
        for _hop in range(max_redirects + 1):
            addresses = resolve_checked(current)
            pinned, host_header = _pinned(current, addresses[0])
            host = urlsplit(current).hostname or ""
            request = client.build_request(
                "GET",
                pinned,
                headers={
                    "Host": host_header,
                    "User-Agent": settings.YORIQNOMA_USER_AGENT,
                    "Accept": "*/*",
                },
                extensions={"sni_hostname": host},
            )
            response = client.send(request, stream=True)
            try:
                if response.status_code in REDIRECTS and "location" in response.headers:
                    current = urljoin(current, response.headers["location"])
                    continue
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > max_bytes:
                        raise UrlBlocked(f"javob juda katta (> {max_bytes} bayt): {current}")
                return Fetched(
                    url=current,
                    status=response.status_code,
                    headers={k.lower(): v for k, v in response.headers.items()},
                    body=bytes(body),
                )
            finally:
                response.close()
    raise UrlBlocked(f"juda ko'p yo'naltirish: {url}")
