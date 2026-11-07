"""Explorer inputs (TZ FR-E1) and the protocols the apps implement (progress, cancel, human)."""

from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, SecretBytes, SecretStr

from yoriqnoma_schemas import Environment


class AccountCredentials(BaseModel):
    model_config = ConfigDict(extra="forbid")
    login: str
    password: SecretStr


class ExploreOptions(BaseModel):
    """Everything a run needs besides the blueprint. Secrets never show in repr or logs."""

    model_config = ConfigDict(extra="forbid")

    base_url: str
    role: str  # target role (TZ FR-RL3)
    environment: Environment = "staging"
    # role -> alias ("A"/"B") -> credentials given by the site owner (FR-RL4)
    accounts: dict[str, dict[str, AccountCredentials]] = Field(default_factory=dict)
    mailbox_kind: Literal["mailpit", "dir"] = "dir"
    mailbox_target: str = ""
    mail_domain: str = "yoriqnoma.test"
    allow_private: bool = False  # True only in the local app (site may be on 127.0.0.1)
    headless: bool = True
    viewport: tuple[int, int] = (1280, 800)
    max_page_height: int = 2400
    locale: str = "uz-UZ"
    timezone: str = "Asia/Tashkent"
    seed: str = "yoriqnoma"
    run_id: str = ""
    pseudonym_key: SecretBytes  # HMAC key for stable fakes; never written anywhere
    step_timeout_ms: int = 8000
    org_domains: list[str] = Field(default_factory=list)  # extra domains of the organization
    ocr: bool = True
    state_graph: bool = True
    patching: bool = True
    max_states: int | None = None  # defaults to policy.max_states
    step_delay_ms: int = 150


class Cancelled(Exception):
    """The run was cancelled by the user."""


class ProgressSink(Protocol):
    def stage(self, name: str, total: int) -> None: ...

    def advance(self, n: int = 1) -> None: ...

    def log(self, level: str, message: str) -> None: ...

    def event(self, kind: str, payload: dict[str, object]) -> None: ...


class CancelToken(Protocol):
    def is_cancelled(self) -> bool: ...


class HumanInput(Protocol):
    async def ask(self, kind: Literal["sms_code", "captcha", "confirm"], message: str) -> str: ...


class NullProgress:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    def stage(self, name: str, total: int) -> None:
        self.messages.append(("stage", f"{name}:{total}"))

    def advance(self, n: int = 1) -> None:
        return None

    def log(self, level: str, message: str) -> None:
        self.messages.append((level, message))

    def event(self, kind: str, payload: dict[str, object]) -> None:
        return None


class NeverCancel:
    def is_cancelled(self) -> bool:
        return False


class NoHuman:
    async def ask(self, kind: Literal["sms_code", "captcha", "confirm"], message: str) -> str:
        raise RuntimeError(f"odam kiritishi kerak ({kind}): {message}")
