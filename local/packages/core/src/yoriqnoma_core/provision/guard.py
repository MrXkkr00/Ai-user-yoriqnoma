"""Firewall of the admin session: an admin login must not be able to harm the site.

Every request of the admin browser context passes here:

* other sites: only static resources (styles, scripts, fonts, images);
* SSRF host check as everywhere (``HostGuard``);
* reading (GET, HEAD, OPTIONS) of the site: allowed, except logging out;
* writing (POST, PUT, PATCH, DELETE):
  - the login form of the admin panel, until signed in;
  - creating a user: a path of a user-like collection (``/admin/app/user/add/``,
    ``POST /api/admin/users``);
  - changing or deleting an object only when its (model, id) pair was created by the
    tool in this job: the test users and the objects the test users created;
  - everything else (settings, other people's records, roles, permissions) is blocked
    and logged.

New ids are learned from the answers to allowed create requests (the ``Location`` of a
redirect, the page it lands on, or ``id`` in a JSON answer).
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from playwright.async_api import Request, Response, Route

from yoriqnoma_core.safety.url_guard import HostGuard, same_origin

STATIC = {"stylesheet", "script", "font", "image", "media"}
ID_RE = re.compile(r"^(\d+|[0-9a-fA-F]{8}-[0-9a-fA-F-]{27,}|[0-9a-fA-F]{24})$")
USERISH = re.compile(
    r"^(users?|accounts?|members?|customers?|staff|employees?|xodim\w*|foydalanuvchi\w*|"
    r"customuser|profiles?|people|persons?|clients?|mijoz\w*)$",
    re.I,
)
CREATE_WORDS = {"add", "new", "create", "yangi", "qoshish", "register"}
# bulk actions of a list page (Django "delete selected", "action=...")
BULK = re.compile(r"(^|&)(_selected_action|action|index|select_across)=", re.I)
LOGIN_WORDS = ("login", "signin", "sign-in", "auth", "kirish", "session", "token")


def singular(word: str) -> str:
    word = word.lower()
    if word.endswith("ies"):
        return word[:-3] + "y"
    if word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def object_key(path: str) -> tuple[str, str] | None:
    """("user", "17") from ``/admin/app/user/17/delete/`` or ``/api/admin/users/17``."""
    parts = [p for p in path.split("/") if p]
    for i, part in enumerate(parts):
        if ID_RE.match(part) and i > 0:
            return singular(parts[i - 1]), part
    return None


def create_target(path: str) -> str | None:
    """The user-like collection a create request goes to, or None."""
    parts = [p.lower() for p in path.split("/") if p]
    if not parts:
        return None
    if parts[-1] in CREATE_WORDS and len(parts) >= 2 and USERISH.match(parts[-2]):
        return singular(parts[-2])
    if USERISH.match(parts[-1]):
        return singular(parts[-1])
    return None


@dataclass
class ProvisionGuard:
    base_url: str
    host_guard: HostGuard
    allowed_objects: set[tuple[str, str]] = field(default_factory=set)
    signed_in: bool = False
    log: list[str] = field(default_factory=list)
    created: list[tuple[str, str]] = field(default_factory=list)  # (model, id), in order
    on_block: Callable[[str], None] | None = None

    def allow(self, model: str, object_id: str) -> None:
        self.allowed_objects.add((singular(model), str(object_id)))

    def decide(self, method: str, url: str, resource_type: str, body: str = "") -> tuple[bool, str]:
        method = method.upper()
        parts = urlsplit(url)
        if parts.scheme in {"data", "blob", "about"}:
            return True, "inline"
        if not same_origin(url, self.base_url):
            if method == "GET" and resource_type in STATIC:
                return True, "boshqa domen: statik resurs"
            return False, "admin sessiyasi: boshqa domen"
        path = parts.path or "/"
        low = path.lower()
        if "logout" in low or "chiqish" in low or "signout" in low:
            return False, "admin sessiyasi: chiqish taqiqlangan"
        if method in {"GET", "HEAD", "OPTIONS"}:
            return True, "o'qish"
        key = object_key(path)
        if key is not None:
            if key in self.allowed_objects:
                return True, f"vosita yaratgan obyekt {key[0]}#{key[1]}"
            return False, f"admin sessiyasi: begona obyekt {key[0]}#{key[1]}"
        if method == "POST" and create_target(path):
            if BULK.search(body):
                return False, "admin sessiyasi: ro'yxatdagi ommaviy amal taqiqlangan"
            return True, "test foydalanuvchi yaratish"
        if not self.signed_in and method == "POST" and any(w in low for w in LOGIN_WORDS):
            return True, "admin paneliga kirish"
        return False, f"admin sessiyasi: {method} {path} taqiqlangan"

    async def handle(self, route: Route, request: Request) -> None:
        blocked = await self.host_guard.check(request.url)
        if blocked is not None:
            allowed, rule = False, f"ssrf: {blocked}"
        else:
            try:
                body = (request.post_data or "") if request.method.upper() == "POST" else ""
            except Exception:  # noqa: BLE001 - binary body: no form fields to look at
                body = ""
            allowed, rule = self.decide(request.method, request.url, request.resource_type, body)
        if not allowed:
            entry = f"{request.method} {urlsplit(request.url).path}: {rule}"
            self.log.append(entry)
            if self.on_block:
                self.on_block(entry)
            await route.abort("blockedbyclient")
            return
        await route.continue_()

    async def on_response(self, response: Response) -> None:
        """Learn ids of what an allowed create request made."""
        request = response.request
        if request.method.upper() != "POST" or not same_origin(response.url, self.base_url):
            return
        target = create_target(urlsplit(request.url).path)
        if target is None:
            return
        location = response.headers.get("location", "")
        key = object_key(urlsplit(location).path) if location else None
        if key is None and "json" in response.headers.get("content-type", ""):
            try:
                data = json.loads(await response.text())
            except Exception:  # noqa: BLE001 - not JSON after all
                data = None
            if isinstance(data, dict) and data.get("id") is not None:
                key = (target, str(data["id"]))
        if key is not None and key not in self.created:
            self.allowed_objects.add(key)
            self.created.append(key)
