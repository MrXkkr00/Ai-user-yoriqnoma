"""Trusted sign-in hosts (single sign-on).

Some sites sign users in on another domain (``app.example.uz`` -> ``auth.example.uz``).
By default every request to another domain is blocked (TZ SEC-4, SEC-10 and the admin
session's firewall), so such a login would never complete. The user may name the sign-in
domain of the site explicitly (project settings); only these exact hosts are trusted, and
only for what a sign-in needs:

* reading (GET, HEAD, OPTIONS): pages, scripts, ``.well-known`` discovery, user info;
* sending a form or token request whose path is a sign-in step (``/Account/Login``,
  ``/connect/token``, ``/signin-oidc``);
* never: logout, password changes, registration, resets, deleting, and every other change.

The password is typed only into pages of the site itself or of these named hosts.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from urllib.parse import urlsplit

AUTH_STEP = re.compile(
    r"(login|log-in|signin|sign-in|connect/|token|callback|authorize|oidc|externallogin|"
    r"consent|mfa|2fa|verify|kirish)",
    re.I,
)
FORBIDDEN = re.compile(
    r"(password|parol|delete|remove|register|reset|forgot|logout|log-out|signout|sign-out|"
    r"chiqish|profile)",
    re.I,
)
HOST = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+$")


def parse_hosts(value: str | Iterable[str] | None) -> tuple[str, ...]:
    """Host names from ``"auth.x.uz, https://sso.y.uz/login"`` (a list works too)."""
    if not value:
        return ()
    parts = re.split(r"[,\s;]+", value) if isinstance(value, str) else list(value)
    hosts: list[str] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        host = (urlsplit(part if "://" in part else f"//{part}").hostname or "").lower()
        if HOST.match(host) and not host.rsplit(".", 1)[-1].isdigit() and host not in hosts:
            hosts.append(host)
    return tuple(hosts)


def invalid_entries(value: str) -> list[str]:
    """Entries of ``value`` that are not a host name (for a form error)."""
    bad = []
    for part in re.split(r"[,\s;]+", value):
        if part.strip() and not parse_hosts(part):
            bad.append(part.strip())
    return bad


def is_trusted(url: str, hosts: Iterable[str]) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    return bool(host) and host in set(hosts)


LOGOUT = re.compile(r"(log-?out|sign-?out|chiqish)", re.I)
READ = {"GET", "HEAD", "OPTIONS"}


def trusted_decision(
    method: str, url: str, resource_type: str, hosts: Iterable[str]
) -> tuple[bool, str] | None:
    """``None`` when ``url`` is not on a trusted host; else (allowed, rule)."""
    if not is_trusted(url, hosts):
        return None
    path = urlsplit(url).path or "/"
    method = method.upper()
    if LOGOUT.search(path):
        return False, f"kirish domeni: chiqish taqiqlangan ({path})"
    if method in READ:
        return True, "ishonchli kirish domeni (SSO): o'qish"
    if method == "POST" and AUTH_STEP.search(path) and not FORBIDDEN.search(path):
        return True, "ishonchli kirish domeni (SSO): kirish qadami"
    return False, f"kirish domeni: {method} {path} taqiqlangan"
