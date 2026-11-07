"""Auth dependencies: who is logged in and which role they have."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from demo_shop.db import get_db
from demo_shop.models import Role, SessionToken, User

COOKIE = "demo_session"

Db = Annotated[Session, Depends(get_db)]


def get_current_user(request: Request, db: Db) -> User:
    token = request.cookies.get(COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Tizimga kiring")
    session = db.get(SessionToken, token)
    user = db.get(User, session.user_id) if session else None
    if user is None:
        raise HTTPException(status_code=401, detail="Tizimga kiring")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_role(role: str) -> Callable[[User], User]:
    def checker(user: CurrentUser) -> User:
        if user.role != role:
            raise HTTPException(status_code=403, detail="Ruxsat yo'q")
        return user

    return checker


def require_admin(user: CurrentUser) -> User:
    if user.role != Role.admin:
        raise HTTPException(status_code=403, detail="Ruxsat yo'q")
    return user


Customer = Annotated[User, Depends(require_role("customer"))]
Manager = Annotated[User, Depends(require_role("manager"))]
Courier = Annotated[User, Depends(require_role("courier"))]
Admin = Annotated[User, Depends(require_admin)]
