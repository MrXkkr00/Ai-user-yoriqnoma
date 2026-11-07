"""Explorer policy (ARCHITECTURE §3.2). Default-deny everywhere (TZ SEC-1)."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator

from yoriqnoma_schemas.common import Environment, RoleId, StrictModel

DEFAULT_DENY_PATHS: list[str] = [
    "/admin",
    "/admin/*",
    "/api/admin",
    "/api/admin/*",
    "/ops/*",
    "/superadmin*",
    "/wp-admin*",
    "/administrator*",
]

# Words of buttons and links the explorer never clicks on its own (state graph), unless
# a flow step on an own object allows it. Logging out is denied too: it would end the
# session. Uzbek in both Latin alphabets is matched after normalize_uz.
DEFAULT_DENY_ACTION_WORDS: list[str] = [
    "o'chirish",
    "bekor qilish",
    "to'lash",
    "to'lov",
    "sotib olish",
    "chiqish",
    "удалить",
    "отменить",
    "оплатить",
    "купить",
    "выйти",
    "delete",
    "remove",
    "cancel",
    "pay",
    "purchase",
    "buy",
    "refund",
    "logout",
    "log out",
    "sign out",
]


class Policy(StrictModel):
    target_role: RoleId  # the role the manual is written for (TZ FR-RL3)
    helper_roles: list[RoleId] = Field(default_factory=list)  # prepare objects only (SEC-5)
    deny_paths: list[str] = Field(default_factory=lambda: list(DEFAULT_DENY_PATHS))
    deny_action_words: list[str] = Field(default_factory=lambda: list(DEFAULT_DENY_ACTION_WORDS))
    default: Literal["deny"] = "deny"
    environment: Environment = "staging"
    destructive: Literal["own_objects_only", "never"] = "own_objects_only"
    payments: Literal["sandbox_only", "never"] = "sandbox_only"
    test_accounts: int = 2
    max_states: int = 400
    max_depth: int = 3
    requests_per_second: float = 2.0

    @field_validator("deny_paths")
    @classmethod
    def _globs(cls, value: list[str]) -> list[str]:
        for pattern in value:
            if not pattern or not (pattern.startswith("/") or pattern.startswith("*")):
                raise ValueError(
                    f"deny_paths entry must be a path glob starting with / or *: {pattern!r}"
                )
            if any(ch.isspace() for ch in pattern):
                raise ValueError(f"deny_paths entry must not contain spaces: {pattern!r}")
        return value
