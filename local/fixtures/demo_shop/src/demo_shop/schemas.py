"""Request bodies. Validation rules: password >= 8, phone +998XXXXXXXXX, quantity 1-99."""

from __future__ import annotations

from pydantic import BaseModel, Field

PHONE = r"^\+998\d{9}$"
EMAIL = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class RegisterIn(BaseModel):
    full_name: str = Field(min_length=3, max_length=80)
    email: str = Field(pattern=EMAIL, max_length=120)
    phone: str = Field(pattern=PHONE)
    password: str = Field(min_length=8, max_length=64)


class VerifyIn(BaseModel):
    email: str = Field(pattern=EMAIL)
    code: str = Field(pattern=r"^\d{6}$")


class LoginIn(BaseModel):
    email: str = Field(pattern=EMAIL)
    password: str = Field(min_length=1)


class ForgotIn(BaseModel):
    email: str = Field(pattern=EMAIL)


class OrderIn(BaseModel):
    product_id: int
    quantity: int = Field(ge=1, le=99)
    address: str = Field(min_length=5, max_length=200)
    phone: str = Field(pattern=PHONE)


class ReviewIn(BaseModel):
    rating: int = Field(ge=1, le=5)
    text: str = Field(min_length=3, max_length=1000)


class MessageIn(BaseModel):
    to_email: str = Field(pattern=EMAIL)
    text: str = Field(min_length=1, max_length=2000)


class ProfileIn(BaseModel):
    full_name: str = Field(min_length=3, max_length=80)
    phone: str = Field(pattern=PHONE)


class PasswordIn(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=8, max_length=64)


class NotificationsIn(BaseModel):
    notify_email: bool


class LanguageIn(BaseModel):
    language: str = Field(pattern=r"^(uz|ru)$")


class DeleteAccountIn(BaseModel):
    password: str = Field(min_length=1)


class SettingIn(BaseModel):
    key: str
    value: str


class RoleChangeIn(BaseModel):
    role: str
