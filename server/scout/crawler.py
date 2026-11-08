"""Breadth-first crawl of one site in one browser context (ARCHITECTURE §7.6).

Only the same origin; paths are templated (/x/123 -> /x/:id) and at most two samples of
each template are opened; deny_paths, robots.txt, the per-domain rate limit and a page
limit apply. For every page: final URL (was it a redirect to the login page?), title,
links (and which of them are in the navigation), forms, the site's own scripts and the
API calls the page made (method, path, status and JSON key names only).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page, Response

from scout.forms import FORMS_JS
from scout.network_infer import ApiCall, json_key_names
from scout.urls import clean_url, path_of, same_site, template_path
from security.ratelimit import wait_turn
from security.robots import Robots
from yoriqnoma_core.explorer.options import CancelToken
from yoriqnoma_core.safety.policy_engine import PolicyEngine

PAGE_INFO_JS = r"""
() => {
  const text = (el) => (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
  const links = Array.from(document.querySelectorAll('a[href]')).slice(0, 400).map(a => ({
    href: a.getAttribute('href'),
    text: text(a).slice(0, 80),
    nav: !!a.closest('nav, header, [role=navigation], aside'),
  }));
  const scripts = Array.from(document.scripts).map(s => s.src).filter(Boolean).slice(0, 40);
  const hasPassword = !!document.querySelector('input[type=password]');
  const h1 = document.querySelector('h1');
  return {title: document.title || '', h1: h1 ? text(h1).slice(0, 120) : '',
          links, scripts, hasPassword};
}
"""


@dataclass
class PageSeen:
    url: str
    template: str
    title: str
    h1: str = ""
    links: list[dict[str, Any]] = field(default_factory=list)
    forms: list[dict[str, Any]] = field(default_factory=list)
    redirected_to: str | None = None  # template of the page it ended on
    login_wall: bool = False  # sent to a page with a password field


@dataclass
class CrawlResult:
    pages: dict[str, PageSeen] = field(default_factory=dict)  # template -> first sample
    api_calls: list[ApiCall] = field(default_factory=list)
    scripts: set[str] = field(default_factory=set)
    nav: list[dict[str, str]] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)  # "path: reason"


def _host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


async def crawl(
    page: Page,
    base_url: str,
    engine: PolicyEngine,
    robots: Robots,
    *,
    start: list[str],
    max_pages: int,
    cancel: CancelToken | None = None,
    settle: Any = None,
) -> CrawlResult:
    result = CrawlResult()
    samples: dict[str, int] = {}
    queue: deque[str] = deque()
    queued: set[str] = set()
    for url in [base_url, *start]:
        clean = clean_url(url, base_url)
        if clean and clean not in queued:
            queue.append(clean)
            queued.add(clean)

    async def on_response(response: Response) -> None:
        request = response.request
        if request.resource_type not in {"xhr", "fetch"} or not same_site(response.url, base_url):
            return
        keys: list[str] = []
        if "json" in response.headers.get("content-type", ""):
            try:
                keys = json_key_names(await response.json())  # values dropped at once
            except Exception:  # noqa: BLE001 - not JSON after all
                keys = []
        result.api_calls.append(
            ApiCall(request.method, path_of(response.url), response.status, keys)
        )

    page.on("response", on_response)
    opened = 0
    try:
        while queue and opened < max_pages:
            if cancel is not None and cancel.is_cancelled():
                break
            url = queue.popleft()
            path = path_of(url)
            tpl = template_path(path)
            if samples.get(tpl, 0) >= 2:
                continue
            if not engine.allows_path(path):
                result.skipped.append(f"{path}: deny_paths")
                continue
            if not robots.allowed(url):
                result.skipped.append(f"{path}: robots.txt")
                continue
            samples[tpl] = samples.get(tpl, 0) + 1
            await wait_turn(_host(url))
            try:
                await page.goto(url, wait_until="domcontentloaded")
                if settle is not None:
                    await settle(page)
                info: dict[str, Any] = await page.evaluate(PAGE_INFO_JS)
                forms: list[dict[str, Any]] = await page.evaluate(FORMS_JS)
            except PlaywrightError as exc:
                result.skipped.append(f"{path}: {str(exc).splitlines()[0][:120]}")
                continue
            opened += 1
            final_tpl = template_path(path_of(page.url))
            seen = PageSeen(
                url=url,
                template=tpl,
                title=str(info.get("title", "")),
                h1=str(info.get("h1", "")),
                links=list(info.get("links", [])),
                forms=forms,
                redirected_to=final_tpl if final_tpl != tpl else None,
                login_wall=final_tpl != tpl and bool(info.get("hasPassword")),
            )
            result.pages.setdefault(tpl, seen)
            if seen.redirected_to and seen.redirected_to not in result.pages:
                result.pages[seen.redirected_to] = PageSeen(
                    url=page.url,
                    template=seen.redirected_to,
                    title=seen.title,
                    h1=seen.h1,
                    links=seen.links,
                    forms=forms,
                )
            for src in info.get("scripts", []):
                if same_site(str(src), base_url):
                    result.scripts.add(str(src))
            for link in seen.links:
                target = clean_url(str(link.get("href") or ""), page.url)
                if target is None:
                    continue
                if link.get("nav") and link.get("text"):
                    entry = {"label": str(link["text"]), "path": path_of(target)}
                    if entry not in result.nav:
                        result.nav.append(entry)
                if target not in queued:
                    queued.add(target)
                    queue.append(target)
    finally:
        page.remove_listener("response", on_response)
    return result
