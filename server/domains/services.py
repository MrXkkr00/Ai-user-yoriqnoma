"""Domains: add, verify ownership (TZ SEC-9) and match a job URL to a domain.

Verification methods, any one is enough:
* ``https://<host>/.well-known/yoriqnoma-verify.txt`` contains the token;
* the home page has ``<meta name="yoriqnoma-verify" content="<token>">``;
* a DNS TXT record ``yoriqnoma-verify=<token>`` on the host.

Every HTTP request goes through ``security.ssrf.safe_get`` (no private addresses, every
redirect checked, DNS pinned).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from html.parser import HTMLParser
from urllib.parse import urlsplit

import httpx
from django.conf import settings
from django.contrib.auth.models import User
from django.utils import timezone

from domains.models import Domain
from security.ssrf import safe_get
from yoriqnoma_core.safety.url_guard import UrlBlocked, parse_ip_literal

HOST_RE = re.compile(
    r"^(?=.{1,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z][a-z0-9-]{1,62}$"
)


class DomainError(ValueError):
    pass


def normalize_host(raw: str) -> str:
    """ "https://Shop.Example.uz/x" or "shop.example.uz" -> "shop.example.uz"."""
    text = raw.strip()
    if not text:
        raise DomainError("Domen kiritilmagan")
    host = urlsplit(text if "://" in text else f"https://{text}").hostname or ""
    try:
        host = host.encode("idna").decode("ascii").lower().rstrip(".")
    except UnicodeError as exc:
        raise DomainError(f"Domen nomi noto'g'ri: {raw}") from exc
    allow = [h.lower() for h in getattr(settings, "YORIQNOMA_PRIVATE_ALLOWLIST", [])]
    if host in allow:  # only the e2e test site ("demo_shop"); empty in production
        return host
    if parse_ip_literal(host) is not None:
        raise DomainError("IP manzil emas, domen nomini kiriting (masalan, shop.example.uz)")
    if host in {"localhost"} or host.endswith((".localhost", ".local", ".internal")):
        raise DomainError("Ichki tarmoq nomlarini qo'shib bo'lmaydi")
    if not HOST_RE.match(host):
        raise DomainError(f"Domen nomi noto'g'ri: {raw}")
    return host


def add_domain(owner: User, raw_host: str) -> Domain:
    host = normalize_host(raw_host)
    domain, _ = Domain.objects.get_or_create(owner=owner, host=host)
    return domain


class _MetaFinder(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.values: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "meta":
            return
        data = {k.lower(): (v or "") for k, v in attrs}
        if data.get("name", "").lower() == "yoriqnoma-verify":
            self.values.append(data.get("content", "").strip())


def _http_text(url: str) -> str | None:
    try:
        answer = safe_get(url, max_bytes=256 * 1024)
    except (UrlBlocked, httpx.HTTPError, OSError, ValueError):
        return None
    return answer.text if answer.status == 200 else None


def dns_txt(host: str) -> list[str]:
    import dns.exception
    import dns.resolver

    try:
        answers = dns.resolver.resolve(host, "TXT", lifetime=5.0)
    except (dns.exception.DNSException, OSError):
        return []
    out = []
    for record in answers:
        strings = getattr(record, "strings", [])
        out.append(b"".join(strings).decode("utf-8", errors="replace"))
    return out


def check_methods(
    domain: Domain,
    http_text: Callable[[str], str | None] = _http_text,
    txt: Callable[[str], list[str]] = dns_txt,
) -> str | None:
    """The first method that proves ownership, or None."""
    token = domain.token
    for scheme in ("https", "http"):
        body = http_text(f"{scheme}://{domain.host}/.well-known/yoriqnoma-verify.txt")
        if body is not None and token in body.split():
            return "wellknown"
    for scheme in ("https", "http"):
        page = http_text(f"{scheme}://{domain.host}/")
        if page is not None:
            finder = _MetaFinder()
            finder.feed(page)
            if token in finder.values:
                return "meta"
    if f"yoriqnoma-verify={token}" in [t.strip() for t in txt(domain.host)]:
        return "dns"
    return None


def verify(
    domain: Domain,
    http_text: Callable[[str], str | None] = _http_text,
    txt: Callable[[str], list[str]] = dns_txt,
) -> Domain:
    method = check_methods(domain, http_text, txt)
    if method is None:
        raise DomainError(
            "Tasdiqlash topilmadi: fayl, meta teg yoki DNS TXT yozuvini joylab, qayta urining. "
            "DNS o'zgarishi bir necha daqiqadan keyin ko'rinadi."
        )
    domain.verified_at = timezone.now()
    domain.method = method
    domain.save(update_fields=["verified_at", "method"])
    return domain


def domain_for(owner: User, url: str) -> Domain | None:
    """The owner's domain for a job URL: the same host, or "www." of it.

    A subdomain is covered only when its parent was verified through DNS (DNS control
    of the zone covers its subdomains; a file on one web server does not).
    """
    host = (urlsplit(url).hostname or "").lower().rstrip(".")
    if not host:
        return None
    domains = list(Domain.objects.filter(owner=owner))
    bare = host.removeprefix("www.")
    for d in domains:
        if d.host in {host, bare} or d.host.removeprefix("www.") == bare:
            return d
    for d in domains:
        if d.method == "dns" and d.verified and host.endswith("." + d.host):
            return d
    return None
