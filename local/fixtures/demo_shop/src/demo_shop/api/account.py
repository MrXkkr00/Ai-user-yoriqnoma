"""Profile, settings, messages and account deletion."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Response
from sqlalchemy import or_, select

from demo_shop.api.auth import user_out
from demo_shop.deps import COOKIE, CurrentUser, Customer, Db
from demo_shop.models import Message, User
from demo_shop.schemas import (
    DeleteAccountIn,
    LanguageIn,
    MessageIn,
    NotificationsIn,
    PasswordIn,
    ProfileIn,
)
from demo_shop.security import check_password, hash_password

profile_router = APIRouter()
settings_router = APIRouter()
messages_router = APIRouter()
account_router = APIRouter()


@profile_router.get("")
def get_profile(user: CurrentUser) -> dict[str, Any]:
    return user_out(user)


@profile_router.put("")
def update_profile(body: ProfileIn, user: CurrentUser, db: Db) -> dict[str, Any]:
    user.full_name = body.full_name
    user.phone = body.phone
    db.commit()
    return user_out(user)


@settings_router.put("/password")
def change_password(body: PasswordIn, user: CurrentUser, db: Db) -> dict[str, str]:
    if not check_password(body.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Joriy parol noto'g'ri")
    user.password_hash = hash_password(body.new_password)
    db.commit()
    return {"status": "ok"}


@settings_router.put("/notifications")
def update_notifications(body: NotificationsIn, user: CurrentUser, db: Db) -> dict[str, str]:
    user.notify_email = body.notify_email
    db.commit()
    return {"status": "ok"}


@settings_router.put("/language")
def update_language(body: LanguageIn, user: CurrentUser, db: Db) -> dict[str, str]:
    user.language = body.language
    db.commit()
    return {"status": "ok"}


@messages_router.get("")
def list_messages(user: Customer, db: Db) -> list[dict[str, Any]]:
    rows = db.scalars(
        select(Message)
        .where(or_(Message.sender_id == user.id, Message.recipient_id == user.id))
        .order_by(Message.id)
    )
    out: list[dict[str, Any]] = []
    for m in rows:
        other_id = m.recipient_id if m.sender_id == user.id else m.sender_id
        other = db.get(User, other_id)
        out.append(
            {
                "id": m.id,
                "outgoing": m.sender_id == user.id,
                "other_name": other.full_name if other else "",
                "other_email": other.email if other else "",
                "text": m.text,
            }
        )
    return out


@messages_router.post("", status_code=201)
def send_message(body: MessageIn, user: Customer, db: Db) -> dict[str, Any]:
    recipient = db.scalar(select(User).where(User.email == body.to_email.lower()))
    if recipient is None:
        raise HTTPException(status_code=400, detail="Qabul qiluvchi topilmadi")
    message = Message(sender_id=user.id, recipient_id=recipient.id, text=body.text)
    db.add(message)
    db.commit()
    return {"id": message.id}


@account_router.post("/delete")
def delete_account(
    body: DeleteAccountIn, user: Customer, response: Response, db: Db
) -> dict[str, str]:
    if not check_password(body.password, user.password_hash):
        raise HTTPException(status_code=400, detail="Parol noto'g'ri")
    db.delete(user)
    db.commit()
    response.delete_cookie(COOKIE)
    return {"status": "deleted"}
