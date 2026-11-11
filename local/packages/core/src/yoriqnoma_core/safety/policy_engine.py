"""PolicyEngine (ARCHITECTURE §4.3; TZ SEC-4, SEC-5). Default-deny.

* ``allows_path``: not in ``deny_paths``.
* ``allows_request``: same-origin requests outside ``deny_paths``; other domains only
  for static GET resources; changing an object (PUT/PATCH/DELETE, or POST to
  ``/<collection>/<id>/<verb>``) only when the id is one of the test accounts' own objects.
* ``allows_click``: the explorer's own clicks never hit destructive, payment or logout
  words, unless a flow step on an own object on staging allows it.
* ``passive`` (TZ SEC-9, server on an unverified domain): only reading requests go out.
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from yoriqnoma_core.safety.sso import trusted_decision
from yoriqnoma_core.safety.url_guard import same_origin
from yoriqnoma_core.text_uz import contains_word
from yoriqnoma_schemas import Policy

STATIC_TYPES = {"stylesheet", "script", "font", "image", "media"}
ID_SEGMENT = re.compile(r"^(\d+|[0-9a-fA-F]{8}-[0-9a-fA-F-]{27,}|[0-9a-fA-F]{24})$")


@dataclass
class RequestContext:
    own_ids: set[str] = field(default_factory=set)
    collections: set[str] = field(default_factory=set)  # entity collection names (reviews)
    probe: bool = False  # SEC-6 privilege probe: GET to denied paths allowed, nothing captured


@dataclass
class ClickContext:
    own_object: bool = False
    flow_step: bool = False  # the click is a blueprint step (not free exploration)


def path_of(url: str) -> str:
    return urlsplit(url).path or "/"


class PolicyEngine:
    def __init__(
        self,
        policy: Policy,
        base_url: str,
        *,
        passive: bool = False,
        trusted_hosts: tuple[str, ...] = (),
    ) -> None:
        self.policy = policy
        self.base_url = base_url
        self.passive = passive
        self.trusted_hosts = trusted_hosts  # named sign-in domains (SSO), see safety/sso.py

    def allows_path(self, path: str) -> bool:
        clean = path.split("?")[0].rstrip("/") or "/"
        for pattern in self.policy.deny_paths:
            if fnmatch.fnmatch(clean, pattern) or fnmatch.fnmatch(clean + "/", pattern):
                return False
        return True

    def allows_request(
        self, method: str, url: str, resource_type: str, ctx: RequestContext
    ) -> tuple[bool, str]:
        method = method.upper()
        scheme = urlsplit(url).scheme
        if scheme in {"data", "blob", "about"}:
            return True, "inline"
        if not same_origin(url, self.base_url):
            sso = trusted_decision(method, url, resource_type, self.trusted_hosts)
            if sso is not None:
                if sso[0] and self.passive and method not in {"GET", "HEAD", "OPTIONS"}:
                    return False, "passiv rejim: domen tasdiqlanmagan, faqat o'qish"
                return sso
            if method == "GET" and resource_type in STATIC_TYPES:
                return True, "boshqa domen: statik resurs"
            return False, f"boshqa domen: {resource_type} {method} taqiqlangan"
        path = path_of(url)
        if not self.allows_path(path):
            if ctx.probe and method == "GET":
                return True, "imtiyoz tekshiruvi (probe)"
            return False, "deny_paths"
        if method in {"GET", "HEAD", "OPTIONS"}:
            return True, "o'qish"
        if self.passive:
            return False, "passiv rejim: domen tasdiqlanmagan, faqat o'qish"
        segments = [s for s in path.split("/") if s]
        for i, seg in enumerate(segments):
            if not ID_SEGMENT.match(seg):
                continue
            rest = segments[i + 1 :]
            if method == "POST" and rest and rest[0] in ctx.collections:
                continue  # creating inside a sub-collection (/products/1/reviews)
            if seg not in ctx.own_ids:
                return False, f"o'zimizniki bo'lmagan obyektni o'zgartirish ({seg})"
        return True, "ruxsat"

    def allows_click(self, name: str, ctx: ClickContext) -> tuple[bool, str]:
        for word in self.policy.deny_action_words:
            if contains_word(name, word):
                if ctx.flow_step and ctx.own_object and self.policy.environment == "staging":
                    if self.policy.destructive == "own_objects_only":
                        return True, "o'z obyekti, staging"
                return False, f"taqiqlangan so'z: «{word}»"
        return True, "ruxsat"
