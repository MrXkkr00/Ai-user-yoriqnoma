"""SSRF protection (TZ SEC-10, CLAUDE.md rule 6).

Every external URL goes through ``check_url``. Only http/https; every DNS answer of the
host is checked; IP literals in any notation (decimal, octal, hex, short forms, IPv6,
IPv4-mapped IPv6) are caught. ``allow_private=True`` is for the local app only (the
studied site may run on 127.0.0.1); the server never passes it.
"""

from __future__ import annotations

import ipaddress
import re
import socket
from collections.abc import Callable
from urllib.parse import urlsplit

PRIVATE_NETWORKS = [
    ipaddress.ip_network(n)
    for n in (
        "0.0.0.0/8",
        "10.0.0.0/8",
        "100.64.0.0/10",
        "127.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "::1/128",
        "::/128",
        "fc00::/7",
    )
]
# Blocked even for the local app: cloud metadata, multicast, reserved.
ALWAYS_BLOCKED = [
    ipaddress.ip_network(n)
    for n in ("169.254.0.0/16", "224.0.0.0/4", "240.0.0.0/4", "fe80::/10", "ff00::/8")
]

Resolver = Callable[[str], list[str]]


class UrlBlocked(ValueError):
    """The URL may not be fetched."""


def _system_resolver(host: str) -> list[str]:
    infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    return sorted({str(info[4][0]) for info in infos})


def parse_ip_literal(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """IP in any notation browsers and C libraries accept, or None for a host name."""
    candidate = host.strip("[]")
    try:
        return ipaddress.ip_address(candidate)
    except ValueError:
        pass
    if re.fullmatch(r"[0-9a-fA-Fx.]+", candidate) and re.search(r"\d", candidate):
        try:
            return ipaddress.IPv4Address(socket.inet_aton(candidate))
        except OSError:
            return None
    return None


def check_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address, *, allow_private: bool) -> None:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    for net in ALWAYS_BLOCKED:
        if ip.version == net.version and ip in net:
            raise UrlBlocked(f"taqiqlangan manzil: {ip} ({net})")
    if allow_private:
        return
    for net in PRIVATE_NETWORKS:
        if ip.version == net.version and ip in net:
            raise UrlBlocked(f"ichki tarmoq manzili: {ip} ({net})")


def check_url(url: str, *, allow_private: bool, resolver: Resolver | None = None) -> str:
    """Return the URL if it may be fetched, otherwise raise ``UrlBlocked``."""
    parts = urlsplit(url.strip())
    if parts.scheme.lower() not in {"http", "https"}:
        raise UrlBlocked(f"faqat http va https ruxsat etilgan: {parts.scheme or '-'}")
    host = parts.hostname
    if not host:
        raise UrlBlocked("URL'da host yo'q")
    if parts.username or parts.password:
        raise UrlBlocked("URL ichida login/parol bo'lmasligi kerak")
    literal = parse_ip_literal(host)
    if literal is not None:
        check_ip(literal, allow_private=allow_private)
        return url.strip()
    if host.lower() in {"localhost", "localhost.localdomain"} or host.lower().endswith(
        ".localhost"
    ):
        if not allow_private:
            raise UrlBlocked(f"ichki host: {host}")
    try:
        addresses = (resolver or _system_resolver)(host)
    except OSError as exc:
        raise UrlBlocked(f"host topilmadi: {host} ({exc})") from exc
    if not addresses:
        raise UrlBlocked(f"host topilmadi: {host}")
    for address in addresses:
        check_ip(ipaddress.ip_address(address), allow_private=allow_private)
    return url.strip()


def same_origin(url: str, base_url: str) -> bool:
    a, b = urlsplit(url), urlsplit(base_url)
    return (a.scheme, a.hostname, a.port or _default_port(a.scheme)) == (
        b.scheme,
        b.hostname,
        b.port or _default_port(b.scheme),
    )


def _default_port(scheme: str) -> int:
    return 443 if scheme == "https" else 80
