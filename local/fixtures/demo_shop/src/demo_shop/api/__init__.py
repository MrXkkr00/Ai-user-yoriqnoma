"""All API routers under /api."""

from __future__ import annotations

from fastapi import APIRouter

from demo_shop.api import admin, auth, catalog, courier, orders, staff
from demo_shop.api.account import account_router, messages_router, profile_router, settings_router

api_router = APIRouter(prefix="/api")
api_router.include_router(auth.router, prefix="/auth")
api_router.include_router(catalog.router, prefix="/products")
api_router.include_router(orders.router, prefix="/orders")
api_router.include_router(profile_router, prefix="/profile")
api_router.include_router(settings_router, prefix="/settings")
api_router.include_router(messages_router, prefix="/messages")
api_router.include_router(account_router, prefix="/account")
api_router.include_router(staff.router, prefix="/staff")
api_router.include_router(courier.router, prefix="/courier")
api_router.include_router(admin.router, prefix="/admin")


@api_router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
