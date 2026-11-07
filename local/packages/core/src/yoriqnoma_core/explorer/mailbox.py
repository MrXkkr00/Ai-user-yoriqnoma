"""Mailboxes for email verification (TZ FR-E5): Mailpit REST API or a folder of .eml files."""

from __future__ import annotations

import asyncio
import email
import email.policy
import re
import time
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path
from typing import Protocol

import httpx

CODE_RE = re.compile(r"(?<!\d)(\d{6})(?!\d)")
LINK_RE = re.compile(r"https?://[^\s<>\"']+")


@dataclass
class MailMessage:
    to: str
    subject: str
    text: str

    @property
    def code(self) -> str | None:
        match = CODE_RE.search(self.text)
        return match.group(1) if match else None

    @property
    def link(self) -> str | None:
        match = LINK_RE.search(self.text)
        return match.group(0) if match else None


class MailTimeout(TimeoutError):
    pass


class Mailbox(Protocol):
    async def wait_for(self, to: str, timeout_s: int = 60) -> MailMessage: ...


def _body(msg: EmailMessage) -> str:
    part = msg.get_body(preferencelist=("plain", "html"))
    if part is None:
        return ""
    content = part.get_content()
    return content if isinstance(content, str) else str(content)


class DirMailbox:
    """Reads ``*.eml`` files a site writes to a folder (demo_shop without Mailpit)."""

    def __init__(self, folder: Path | str) -> None:
        self.folder = Path(folder)
        self._seen: set[str] = set()

    async def wait_for(self, to: str, timeout_s: int = 60) -> MailMessage:
        deadline = time.monotonic() + timeout_s
        target = to.lower()
        while time.monotonic() < deadline:
            if self.folder.is_dir():
                for path in sorted(self.folder.glob("*.eml"), key=lambda p: p.stat().st_mtime):
                    if path.name in self._seen:
                        continue
                    msg = email.message_from_bytes(path.read_bytes(), policy=email.policy.default)
                    assert isinstance(msg, EmailMessage)
                    if target in str(msg.get("To", "")).lower():
                        self._seen.add(path.name)
                        return MailMessage(target, str(msg.get("Subject", "")), _body(msg))
            await asyncio.sleep(0.5)
        raise MailTimeout(f"{timeout_s} soniyada {to} uchun xat kelmadi ({self.folder})")


class MailpitMailbox:
    """Mailpit REST API: search by recipient, read the newest message."""

    def __init__(self, api_url: str) -> None:
        self.api_url = api_url.rstrip("/")
        self._seen: set[str] = set()

    async def wait_for(self, to: str, timeout_s: int = 60) -> MailMessage:
        deadline = time.monotonic() + timeout_s
        async with httpx.AsyncClient(timeout=10) as client:
            while time.monotonic() < deadline:
                resp = await client.get(
                    f"{self.api_url}/api/v1/search", params={"query": f'to:"{to}"'}
                )
                if resp.status_code == 200:
                    for item in resp.json().get("messages", []):
                        mid = str(item.get("ID"))
                        if mid in self._seen:
                            continue
                        self._seen.add(mid)
                        detail = await client.get(f"{self.api_url}/api/v1/message/{mid}")
                        data = detail.json()
                        return MailMessage(
                            to, str(data.get("Subject", "")), str(data.get("Text", ""))
                        )
                await asyncio.sleep(1)
        raise MailTimeout(f"{timeout_s} soniyada {to} uchun xat kelmadi (Mailpit)")


def make_mailbox(kind: str, target: str) -> Mailbox:
    if kind == "mailpit":
        return MailpitMailbox(target)
    return DirMailbox(target)
