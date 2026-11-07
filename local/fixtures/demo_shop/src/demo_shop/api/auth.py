"""Registration, email verification, login and password reset."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from sqlalchemy import select

from demo_shop.deps import COOKIE, CurrentUser, Db
from demo_shop.mail import send_mail
from demo_shop.models import Role, SessionToken, User
from demo_shop.schemas import ForgotIn, LoginIn, RegisterIn, VerifyIn
from demo_shop.security import check_password, hash_password, new_code, new_token

router = APIRouter()


def user_out(user: User) -> dict[str, Any]:
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "phone": user.phone,
        "role": user.role.value,
        "language": user.language,
        "notify_email": user.notify_email,
    }


@router.post("/register", status_code=201)
def register(body: RegisterIn, request: Request, db: Db) -> dict[str, str]:
    email = body.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=409, detail="Bu email bilan hisob mavjud")
    code = new_code()
    user = User(
        email=email,
        password_hash=hash_password(body.password),
        full_name=body.full_name,
        phone=body.phone,
        role=Role.customer,
        verify_code=code,
    )
    db.add(user)
    db.commit()
    link = f"{request.base_url}verify-email?email={email}&code={code}"
    send_mail(
        email,
        "Demo Shop: emailni tasdiqlang",
        f"Salom, {body.full_name}!\n\nTasdiqlash kodi: {code}\nYoki havolani oching: {link}\n",
    )
    return {"status": "verify_email"}


@router.post("/verify-email")
def verify_email(body: VerifyIn, db: Db) -> dict[str, str]:
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if user is None or user.verify_code != body.code:
        raise HTTPException(status_code=400, detail="Kod noto'g'ri")
    user.email_verified = True
    user.verify_code = ""
    db.commit()
    return {"status": "verified"}


@router.post("/login")
def login(body: LoginIn, response: Response, db: Db) -> dict[str, Any]:
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if user is None or not check_password(body.password, user.password_hash):
        raise HTTPException(status_code=400, detail="Email yoki parol noto'g'ri")
    if not user.email_verified:
        raise HTTPException(status_code=403, detail="Email tasdiqlanmagan")
    token = new_token()
    db.add(SessionToken(token=token, user_id=user.id))
    db.commit()
    response.set_cookie(COOKIE, token, httponly=True, samesite="lax")
    return user_out(user)


@router.post("/logout")
def logout(request: Request, response: Response, db: Db) -> dict[str, str]:
    token = request.cookies.get(COOKIE)
    if token:
        session = db.get(SessionToken, token)
        if session:
            db.delete(session)
            db.commit()
    response.delete_cookie(COOKIE)
    return {"status": "ok"}


@router.post("/forgot-password")
def forgot_password(body: ForgotIn, db: Db) -> dict[str, str]:
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if user is not None:
        send_mail(user.email, "Demo Shop: parolni tiklash", f"Tiklash kodi: {new_code()}\n")
    return {"status": "sent"}


@router.get("/me")
def me(user: CurrentUser) -> dict[str, Any]:
    return user_out(user)
