"""Privilege check after login (TZ SEC-6), on a separate probe page with capture off.

* admin API routes must answer 401/403/404;
* admin pages must not show admin content (SPA: the rendered page is checked, not only
  the status code);
* the account must really be in the chosen role: the role's own API routes answer 200.

Only yes/no is kept; page contents are never stored.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from playwright.async_api import BrowserContext
from playwright.async_api import Error as PlaywrightError

from yoriqnoma_core.explorer.firewall import Firewall
from yoriqnoma_schemas import Blueprint

ADMIN_MARKERS = re.compile(
    r"\b(admin|administrator|admin panel|users|roles|permissions|foydalanuvchilar|rollar|"
    r"huquqlar|админ|пользователи|роли)\b",
    re.I,
)


class PrivilegedAccountError(Exception):
    """The account sees admin content or is not in the chosen role: the run stops."""


def _concrete(path: str) -> str:
    return re.sub(r":[^/]+", "1", path)


def _path(url: str) -> str:
    return "/" + urlsplit(url).path.strip("/")


HAS_PASSWORD = "() => !!document.querySelector('input[type=password]')"


async def privilege_check(
    context: BrowserContext, firewall: Firewall, bp: Blueprint, role: str, base_url: str
) -> None:
    base = base_url.rstrip("/")
    page = await context.new_page()
    firewall.probe = True
    try:
        for route in bp.excluded:
            if route.kind != "api" or "GET" not in route.methods:
                continue
            target = _concrete(route.path)
            resp = await page.request.get(base + target, fail_on_status_code=False)
            # A redirect to the login page (server-rendered sites) is a refusal too.
            if resp.status < 400 and _path(resp.url) == _path(base + target):
                raise PrivilegedAccountError(
                    f"akkauntga admin API ochiq: {route.path} ({resp.status})"
                )
        excluded_pages = [r.path for r in bp.excluded if r.kind == "page"]
        for path in excluded_pages[:6]:
            target = _concrete(path)
            try:
                await page.goto(base + target)
                await page.wait_for_load_state("networkidle", timeout=6000)
            except PlaywrightError:
                continue
            if firewall.engine.allows_path(_path(page.url)):
                continue  # sent away from the admin part (login page, home): refused
            if await page.evaluate(HAS_PASSWORD):
                continue  # the admin part's own login form: refused
            hrefs: list[str] = await page.evaluate(
                "() => [...document.querySelectorAll('a[href]')].map(a => a.getAttribute('href'))"
            )
            others = {_concrete(p) for p in excluded_pages} - {target}
            if any(h in others for h in hrefs):
                raise PrivilegedAccountError(f"admin sahifasi ochildi: {path}")
            headings: list[str] = await page.evaluate(
                "() => [...document.querySelectorAll('h1, h2')].map(h => h.innerText)"
            )
            on_target = page.url.split("?")[0].rstrip("/").endswith(target.rstrip("/"))
            if on_target and any(ADMIN_MARKERS.search(h or "") for h in headings):
                raise PrivilegedAccountError(f"admin sahifasi ochildi: {path}")
        own_api = [
            r.path
            for r in bp.pages
            if r.kind == "api"
            and "GET" in r.methods
            and ":" not in r.path
            and r.access == "roles"
            and role in r.roles
            and len(r.roles) < len(bp.selectable_roles())
        ]
        statuses = []
        for path in own_api[:5]:
            resp = await page.request.get(base + path, fail_on_status_code=False)
            statuses.append(resp.status)
        if statuses and all(s in (401, 403) for s in statuses):
            raise PrivilegedAccountError(
                f"akkaunt «{role}» rolida emas: rolning o'z yo'llari yopiq ({own_api[0]})"
            )
    finally:
        firewall.probe = False
        await page.close()
