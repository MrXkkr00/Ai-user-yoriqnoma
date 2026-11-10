"""Shared types of admin provisioning (local modes 2 and 3).

The site owner gives an admin login. The tool uses it ONLY to create test users of the
chosen role and to remove them (and what they created) when the job ends. The admin
session is a separate browser context: nothing in it is captured, nothing from it goes
into the blueprint, capture or manual (CLAUDE.md rule 1), and its writes are limited by
``ProvisionGuard`` to creating users and changing what the tool itself created.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal, Protocol

from playwright.async_api import Page
from pydantic import SecretStr

from yoriqnoma_core.explorer.datagen import Identity
from yoriqnoma_core.text_uz import normalize_uz

ADMIN_LIKE = re.compile(
    r"\b(admin\w*|administrator|superadmin|super ?user|root|owner|ega|boshqaruvchi|"
    r"админ\w*|суперадмин)\b",
    re.I,
)


class ProvisionError(Exception):
    """Admin provisioning cannot go on; the reason is shown to the user."""


@dataclass
class AdminCredentials:
    login: str
    password: SecretStr
    admin_url: str = ""  # path or URL of the admin panel ("/admin/"); empty: look for it

    def __repr__(self) -> str:  # never the password
        return f"AdminCredentials(login={self.login!r}, admin_url={self.admin_url!r})"


@dataclass
class RoleCandidate:
    id: str
    label: str
    kind: Literal["role", "excluded"]
    reason: str
    source: str
    field: str = ""  # form field that sets it ("role", "groups")
    value: str = ""  # option value in that field


@dataclass
class CreatedUser:
    role: str
    alias: str
    login: str
    email: str
    remote_id: str  # id in the site's admin ("17")
    model: str = "user"  # admin model segment ("user", "users")
    cleaned: bool = False
    error: str = ""


@dataclass
class CleanupReport:
    users_removed: int = 0
    objects_removed: int = 0
    left: list[str] = field(default_factory=list)  # what could not be removed, with reason

    @property
    def clean(self) -> bool:
        return not self.left


def role_id(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", normalize_uz(text).replace("'", "")).strip("_")
    return slug[:40] or "role"


def classify_role(label: str, value: str, source: str, field_name: str) -> RoleCandidate:
    """Admin-like or unclear -> excluded (default-deny, TZ FR-RL2)."""
    rid = role_id(value or label)
    if ADMIN_LIKE.search(label) or ADMIN_LIKE.search(value):
        kind: Literal["role", "excluded"] = "excluded"
        reason = "adminga o'xshash rol: yo'riqnoma yozilmaydi"
    elif not rid or rid in {"none", "null", "role"} or not label.strip():
        kind, reason = "excluded", "noaniq rol (default-deny)"
    else:
        kind, reason = "role", "admin panelidagi rol"
    return RoleCandidate(
        id=rid,
        label=label.strip() or rid,
        kind=kind,
        reason=reason,
        source=source,
        field=field_name,
        value=value,
    )


class AdminAdapter(Protocol):
    """One way of driving an admin panel (Django admin, a plain form panel, the agent)."""

    name: str

    async def detect(self, page: Page) -> bool: ...

    async def login(self, page: Page, creds: AdminCredentials) -> None: ...

    async def roles(self, page: Page) -> list[RoleCandidate]: ...

    async def create_user(
        self, page: Page, role: RoleCandidate, identity: Identity, alias: str
    ) -> CreatedUser: ...

    async def delete_object(self, page: Page, entity: str, object_id: str) -> bool: ...

    async def delete_user(self, page: Page, user: CreatedUser) -> None: ...


class Ledger:
    """What the tool created on the site (``provision.json``; no passwords, ever).

    Written after every change, so a cleanup can be repeated after a crash.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self.users: list[CreatedUser] = []
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            self.users = [CreatedUser(**u) for u in data.get("users", [])]

    def add(self, user: CreatedUser) -> None:
        self.users.append(user)
        self.save()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {"users": [asdict(u) for u in self.users]}
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    def pending(self) -> list[CreatedUser]:
        return [u for u in self.users if not u.cleaned]
