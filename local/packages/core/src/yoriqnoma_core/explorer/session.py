"""Playwright session: one clean browser context per account (A, B, helper roles, guest)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    Response,
    async_playwright,
)

from yoriqnoma_core.explorer.firewall import Firewall
from yoriqnoma_core.explorer.options import ExploreOptions
from yoriqnoma_core.safety.url_guard import same_origin
from yoriqnoma_schemas import NetCall

ID_SEG = re.compile(r"^(\d+|[0-9a-fA-F-]{20,})$")


def path_template(path: str) -> str:
    return "/".join(":id" if ID_SEG.match(s) else s for s in path.split("/"))


@dataclass
class AccountContext:
    key: str  # "guest", "customer:A", "manager:A"
    context: BrowserContext
    page: Page
    firewall: Firewall
    network: list[NetCall] = field(default_factory=list)
    responses: list[tuple[str, str, int, str]] = field(default_factory=list)  # method,url,status,ct


class BrowserSession:
    def __init__(self, opts: ExploreOptions, make_firewall: object) -> None:
        self.opts = opts
        self._make_firewall = make_firewall
        self._pw: Playwright | None = None
        self._browser: Browser | None = None
        self.contexts: dict[str, AccountContext] = {}

    async def start(self) -> None:
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(headless=self.opts.headless)

    async def close(self) -> None:
        for acc in list(self.contexts.values()):
            try:
                await acc.context.close()
            except Exception:  # noqa: BLE001
                pass
        self.contexts.clear()
        if self._browser is not None:
            await self._browser.close()
        if self._pw is not None:
            await self._pw.stop()

    async def account(self, key: str) -> AccountContext:
        if key in self.contexts:
            return self.contexts[key]
        assert self._browser is not None, "session not started"
        width, height = self.opts.viewport
        context = await self._browser.new_context(
            viewport={"width": width, "height": height},
            locale=self.opts.locale,
            timezone_id=self.opts.timezone,
            accept_downloads=True,
            base_url=self.opts.base_url,
            device_scale_factor=self.opts.device_scale_factor,
        )
        context.set_default_timeout(self.opts.step_timeout_ms)
        firewall: Firewall = self._make_firewall()  # type: ignore[operator]
        await context.route("**/*", firewall.handle)
        page = await context.new_page()
        acc = AccountContext(key, context, page, firewall)

        def on_response(response: Response) -> None:
            url = response.url
            if not same_origin(url, self.opts.base_url):
                return
            path = urlsplit(url).path
            req = response.request
            acc.responses.append(
                (req.method, url, response.status, response.headers.get("content-type", ""))
            )
            if req.resource_type in {"fetch", "xhr", "document"}:
                acc.network.append(
                    NetCall(
                        method=req.method, path_template=path_template(path), status=response.status
                    )
                )

        page.on("response", on_response)
        self.contexts[key] = acc
        return acc

    async def reset(self, key: str) -> None:
        """Drop an account's context (after logout or account deletion)."""
        acc = self.contexts.pop(key, None)
        if acc is not None:
            await acc.context.close()
