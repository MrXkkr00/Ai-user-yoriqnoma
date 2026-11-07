"""The customer's own orders. Every query is filtered by the owner (user_id)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy import select

from demo_shop.deps import Customer, Db
from demo_shop.models import Order, OrderEvent, OrderStatus, Product, User
from demo_shop.schemas import OrderIn

router = APIRouter()


def order_out(order: Order, product: Product | None) -> dict[str, Any]:
    return {
        "id": order.id,
        "product_id": order.product_id,
        "product_name": product.name if product else "",
        "quantity": order.quantity,
        "total": (product.price if product else 0) * order.quantity,
        "customer_name": order.customer_name,
        "phone": order.phone,
        "address": order.address,
        "status": order.status.value,
        "attachment_url": f"/api/staff/orders/{order.id}/attachment" if order.attachment else "",
        "created_at": order.created_at.isoformat(),
    }


def own_order(db: Db, user: User, order_id: int) -> Order:
    order = db.get(Order, order_id)
    if order is None or order.user_id != user.id:
        raise HTTPException(status_code=404, detail="Buyurtma topilmadi")
    return order


def log_event(db: Db, order: Order) -> None:
    db.add(OrderEvent(order_id=order.id, status=order.status))
    db.commit()


@router.get("")
def list_orders(user: Customer, db: Db) -> list[dict[str, Any]]:
    orders = db.scalars(select(Order).where(Order.user_id == user.id).order_by(Order.id.desc()))
    return [order_out(o, db.get(Product, o.product_id)) for o in orders]


@router.post("", status_code=201)
def create_order(body: OrderIn, user: Customer, db: Db) -> dict[str, Any]:
    product = db.get(Product, body.product_id)
    if product is None:
        raise HTTPException(status_code=400, detail="Mahsulot topilmadi")
    order = Order(
        user_id=user.id,
        product_id=product.id,
        quantity=body.quantity,
        customer_name=user.full_name,
        phone=body.phone,
        address=body.address,
    )
    order.status = OrderStatus.new
    db.add(order)
    db.commit()
    log_event(db, order)
    return order_out(order, product)


@router.get("/{order_id}")
def get_order(order_id: int, user: Customer, db: Db) -> dict[str, Any]:
    order = own_order(db, user, order_id)
    return order_out(order, db.get(Product, order.product_id))


@router.get("/{order_id}/history")
def order_history(order_id: int, user: Customer, db: Db) -> list[dict[str, str]]:
    own_order(db, user, order_id)
    events = db.scalars(
        select(OrderEvent).where(OrderEvent.order_id == order_id).order_by(OrderEvent.id)
    )
    return [{"status": e.status.value, "at": e.at.isoformat()} for e in events]


@router.post("/{order_id}/pay")
def pay_order(order_id: int, user: Customer, db: Db) -> dict[str, Any]:
    order = own_order(db, user, order_id)
    if order.status != OrderStatus.new:
        raise HTTPException(status_code=409, detail="Faqat yangi buyurtmani to'lash mumkin")
    order.status = OrderStatus.paid  # sandbox payment: no real money
    log_event(db, order)
    return order_out(order, db.get(Product, order.product_id))


@router.post("/{order_id}/cancel")
def cancel_order(order_id: int, user: Customer, db: Db) -> dict[str, Any]:
    order = own_order(db, user, order_id)
    if order.status != OrderStatus.new:
        raise HTTPException(status_code=409, detail="Faqat yangi buyurtmani bekor qilish mumkin")
    order.status = OrderStatus.cancelled
    log_event(db, order)
    return order_out(order, db.get(Product, order.product_id))


@router.get("/{order_id}/invoice")
def download_invoice(order_id: int, user: Customer, db: Db) -> PlainTextResponse:
    order = own_order(db, user, order_id)
    product = db.get(Product, order.product_id)
    total = (product.price if product else 0) * order.quantity
    text = (
        f"Demo Shop chek\nBuyurtma #{order.id}\nSumma: {total} so'm\nStatus: {order.status.value}\n"
    )
    return PlainTextResponse(
        text, headers={"Content-Disposition": f'attachment; filename="chek-{order.id}.txt"'}
    )
