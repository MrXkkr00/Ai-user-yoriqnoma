"""Manager pages: every order, ship paid orders. Managers never edit users or settings."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select

from demo_shop.api.orders import log_event, order_out
from demo_shop.config import uploads_dir
from demo_shop.deps import Db, require_role
from demo_shop.models import Order, OrderStatus, Product, Role, User

router = APIRouter(dependencies=[Depends(require_role("manager"))])


@router.get("/orders")
def staff_orders(db: Db) -> list[dict[str, Any]]:
    orders = db.scalars(select(Order).order_by(Order.id.desc()))
    return [order_out(o, db.get(Product, o.product_id)) for o in orders]


@router.get("/orders/{order_id}")
def staff_order(order_id: int, db: Db) -> dict[str, Any]:
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Buyurtma topilmadi")
    return order_out(order, db.get(Product, order.product_id))


@router.get("/orders/{order_id}/attachment")
def staff_order_attachment(order_id: int, db: Db) -> FileResponse:
    order = db.get(Order, order_id)
    if order is None or not order.attachment:
        raise HTTPException(status_code=404, detail="Ilova yo'q")
    return FileResponse(uploads_dir() / order.attachment, media_type="image/png")


@router.post("/orders/{order_id}/ship")
def ship_order(order_id: int, db: Db) -> dict[str, Any]:
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Buyurtma topilmadi")
    if order.status != OrderStatus.paid:
        raise HTTPException(status_code=409, detail="Faqat to'langan buyurtmani jo'natish mumkin")
    courier = db.scalar(select(User).where(User.role == Role.courier).order_by(User.id))
    order.courier_id = courier.id if courier else None
    order.status = OrderStatus.shipped
    log_event(db, order)
    return order_out(order, db.get(Product, order.product_id))
