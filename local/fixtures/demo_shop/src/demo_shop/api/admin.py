"""Admin area: users, roles, refunds and site settings. Must never reach a manual.

Creating and deleting users here is what the local app's admin provisioning uses
(modes 2 and 3): it makes test users of a role and removes them with their data.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select, update

from demo_shop.api.auth import user_out
from demo_shop.api.orders import log_event, order_out
from demo_shop.deps import Db, require_admin
from demo_shop.models import (
    Message,
    Order,
    OrderEvent,
    OrderStatus,
    Product,
    Review,
    Role,
    SessionToken,
    SiteSetting,
    User,
)
from demo_shop.schemas import AdminUserIn, RoleChangeIn, SettingIn
from demo_shop.security import hash_password

router = APIRouter(dependencies=[Depends(require_admin)])


@router.get("/users")
def admin_users(db: Db) -> list[dict[str, Any]]:
    return [user_out(u) for u in db.scalars(select(User).order_by(User.id))]


@router.post("/users", status_code=201)
def admin_create_user(body: AdminUserIn, db: Db) -> dict[str, Any]:
    if db.scalar(select(User).where(User.email == body.email.lower())) is not None:
        raise HTTPException(status_code=409, detail="Bu email band")
    user = User(
        email=body.email.lower(),
        full_name=body.full_name,
        phone=body.phone,
        password_hash=hash_password(body.password),
        role=Role(body.role),
        email_verified=True,
    )
    db.add(user)
    db.commit()
    return user_out(user)


@router.delete("/users/{user_id}")
def admin_delete_user(user_id: int, db: Db) -> dict[str, str]:
    """The user and everything that is theirs (orders, reviews, messages, sessions)."""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Topilmadi")
    if user.role == Role.admin:
        raise HTTPException(status_code=409, detail="Administratorni o'chirib bo'lmaydi")
    orders = select(Order.id).where(Order.user_id == user_id)
    db.execute(delete(OrderEvent).where(OrderEvent.order_id.in_(orders)))
    db.execute(delete(Order).where(Order.user_id == user_id))
    db.execute(update(Order).where(Order.courier_id == user_id).values(courier_id=None))
    db.execute(delete(Review).where(Review.author_id == user_id))
    db.execute(
        delete(Message).where((Message.sender_id == user_id) | (Message.recipient_id == user_id))
    )
    db.execute(delete(SessionToken).where(SessionToken.user_id == user_id))
    db.delete(user)
    db.commit()
    return {"status": "deleted"}


@router.put("/users/{user_id}/role")
def admin_set_role(user_id: int, body: RoleChangeIn, db: Db) -> dict[str, Any]:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Topilmadi")
    user.role = Role(body.role)
    db.commit()
    return user_out(user)


@router.get("/roles")
def admin_roles() -> list[str]:
    return [r.value for r in Role]


@router.post("/orders/{order_id}/refund")
def admin_refund(order_id: int, db: Db) -> dict[str, Any]:
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Topilmadi")
    if order.status != OrderStatus.paid:
        raise HTTPException(status_code=409, detail="Faqat to'langan buyurtma qaytariladi")
    order.status = OrderStatus.refunded
    log_event(db, order)
    return order_out(order, db.get(Product, order.product_id))


@router.put("/settings")
def admin_settings(body: SettingIn, db: Db) -> dict[str, str]:
    db.merge(SiteSetting(key=body.key, value=body.value))
    db.commit()
    return {"status": "ok"}
