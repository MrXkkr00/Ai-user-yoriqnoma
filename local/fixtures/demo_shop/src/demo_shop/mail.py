"""Outgoing mail: SMTP to Mailpit when MAILPIT_SMTP is set, otherwise var/mail/*.eml."""

from __future__ import annotations

import smtplib
import time
from email.message import EmailMessage

from demo_shop.config import mail_dir, smtp_target

SENDER = "noreply@demo-shop.uz"


def send_mail(to: str, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["From"] = SENDER
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    target = smtp_target()
    if target:
        with smtplib.SMTP(*target, timeout=10) as smtp:
            smtp.send_message(msg)
        return
    stamp = f"{time.time_ns()}"
    safe_to = "".join(ch if ch.isalnum() or ch in "@.+-_" else "_" for ch in to)
    (mail_dir() / f"{stamp}_{safe_to}.eml").write_bytes(bytes(msg))
