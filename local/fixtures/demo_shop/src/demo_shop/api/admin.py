"""Admin area: users, roles, refunds and site settings. Must never reach a manual."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from demo_shop.api.auth import user_out
from demo_shop.api.orders import log_event, order_out
from demo_shop.deps import Db, require_admin
from demo_shop.models import Order, OrderStatus, Product, Role, SiteSetting, User
from demo_shop.schemas import RoleChangeIn, SettingIn

router = APIRouter(dependencies=[Depends(require_admin)])


@router.get("/users")
def admin_users(db: Db) -> list[dict[str, Any]]:
    return [user_out(u) for u in db.scalars(select(User).order_by(User.id))]


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
