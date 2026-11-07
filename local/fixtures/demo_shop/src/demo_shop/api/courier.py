"""Courier pages: orders assigned to this courier, mark them delivered."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from demo_shop.api.orders import log_event, order_out
from demo_shop.deps import CurrentUser, Db, require_role
from demo_shop.models import Order, OrderStatus, Product

router = APIRouter(dependencies=[Depends(require_role("courier"))])


def assigned(db: Db, courier_id: int, order_id: int) -> Order:
    order = db.get(Order, order_id)
    if order is None or order.courier_id != courier_id:
        raise HTTPException(status_code=404, detail="Buyurtma topilmadi")
    return order


@router.get("/orders")
def courier_orders(user: CurrentUser, db: Db) -> list[dict[str, Any]]:
    orders = db.scalars(select(Order).where(Order.courier_id == user.id).order_by(Order.id.desc()))
    return [order_out(o, db.get(Product, o.product_id)) for o in orders]


@router.get("/orders/{order_id}")
def courier_order(order_id: int, user: CurrentUser, db: Db) -> dict[str, Any]:
    order = assigned(db, user.id, order_id)
    return order_out(order, db.get(Product, order.product_id))


@router.post("/orders/{order_id}/deliver")
def deliver_order(order_id: int, user: CurrentUser, db: Db) -> dict[str, Any]:
    order = assigned(db, user.id, order_id)
    if order.status != OrderStatus.shipped:
        raise HTTPException(status_code=409, detail="Faqat jo'natilgan buyurtmani yetkazish mumkin")
    order.status = OrderStatus.delivered
    log_event(db, order)
    return order_out(order, db.get(Product, order.product_id))
