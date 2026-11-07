"""Public catalog and product reviews."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from demo_shop.deps import Customer, Db
from demo_shop.models import Product, Review, User
from demo_shop.schemas import ReviewIn

router = APIRouter()


def product_out(p: Product) -> dict[str, Any]:
    return {"id": p.id, "name": p.name, "description": p.description, "price": p.price}


@router.get("")
def list_products(db: Db) -> list[dict[str, Any]]:
    return [product_out(p) for p in db.scalars(select(Product).order_by(Product.id))]


@router.get("/{product_id}")
def get_product(product_id: int, db: Db) -> dict[str, Any]:
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Topilmadi")
    return product_out(product)


@router.get("/{product_id}/reviews")
def list_reviews(product_id: int, db: Db) -> list[dict[str, Any]]:
    rows = db.execute(
        select(Review, User)
        .join(User, User.id == Review.author_id)
        .where(Review.product_id == product_id)
        .order_by(Review.id)
    )
    return [
        {"id": r.id, "author_name": u.full_name, "rating": r.rating, "text": r.text}
        for r, u in rows
    ]


@router.post("/{product_id}/reviews", status_code=201)
def create_review(product_id: int, body: ReviewIn, user: Customer, db: Db) -> dict[str, Any]:
    if db.get(Product, product_id) is None:
        raise HTTPException(status_code=404, detail="Topilmadi")
    review = Review(product_id=product_id, author_id=user.id, rating=body.rating, text=body.text)
    db.add(review)
    db.commit()
    return {
        "id": review.id,
        "author_name": user.full_name,
        "rating": review.rating,
        "text": review.text,
    }
