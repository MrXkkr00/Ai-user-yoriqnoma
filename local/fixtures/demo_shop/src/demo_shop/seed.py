"""Seed data. Other people's data here is what the tool must replace with fakes (FR-E10)."""

from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont
from sqlalchemy.orm import Session

from demo_shop.config import uploads_dir
from demo_shop.models import Order, OrderEvent, OrderStatus, Product, Review, Role, User
from demo_shop.security import hash_password

# Test accounts the site owner would hand over (they imitate staff accounts).
STAFF_ACCOUNTS = {
    "admin": ("admin@demo.local", "Admin12345", "Bosh administrator"),
    "manager": ("manager@demo.local", "Manager12345", "Sardor Menejerov"),
    "courier": ("courier@demo.local", "Courier12345", "Kamol Kuryerov"),
}

# Real-looking customers: the tool must never show them as they are.
OTHER_CUSTOMER = ("Dilnoza Karimova", "dilnoza.karimova@mail.uz", "+998977654321")
REVIEWERS = [
    ("Jasur Toshmatov", "jasur.toshmatov@mail.uz", "+998935551122"),
    ("Malika Yusupova", "malika.yusupova@mail.uz", "+998977003344"),
]

PRODUCTS = [
    ("Choynak", "Elektr choynak, 1,7 litr", 289_000),
    ("Piyola to'plami", "6 ta chinni piyola", 145_000),
    ("Dazmol", "Bug'li dazmol, 2200 Vt", 399_000),
    ("Changyutgich", "Simsiz changyutgich", 1_250_000),
    ("Blender", "Stakanli blender, 600 Vt", 520_000),
    ("Qozon", "Cho'yan qozon, 8 litr", 610_000),
    ("Gilam", "Paxta gilam, 2x3 m", 1_900_000),
    ("Lampa", "Stol lampasi, LED", 175_000),
    ("Sochiq", "Paxta sochiq to'plami", 98_000),
    ("Termos", "Po'lat termos, 1 litr", 160_000),
]


def _slip_image(order_id: int, name: str, phone: str) -> str:
    """A delivery slip PNG with a name and phone inside the image (OCR test)."""
    img = Image.new("RGB", (640, 300), "white")
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default(size=30)
    small = ImageFont.load_default(size=26)
    draw.rectangle((8, 8, 631, 291), outline="black", width=3)
    draw.text((30, 30), "YETKAZISH VARAQASI", fill="black", font=font)
    draw.text((30, 100), f"Qabul qiluvchi: {name}", fill="black", font=small)
    draw.text((30, 150), f"Telefon: {phone}", fill="black", font=small)
    draw.text((30, 200), "Manzil: Toshkent, Chilonzor 5-12", fill="black", font=small)
    filename = f"slip_{order_id}.png"
    img.save(uploads_dir() / filename)
    return filename


def seed(db: Session) -> None:
    for role, (email, password, name) in STAFF_ACCOUNTS.items():
        db.add(
            User(
                email=email,
                password_hash=hash_password(password),
                full_name=name,
                phone="+998712000000" if role == "admin" else "+998900000001",
                role=Role(role),
                email_verified=True,
            )
        )
    for name, desc, price in PRODUCTS:
        db.add(Product(name=name, description=desc, price=price))
    db.commit()

    other = User(
        email=OTHER_CUSTOMER[1],
        password_hash=hash_password("Dilnoza-private-1"),
        full_name=OTHER_CUSTOMER[0],
        phone=OTHER_CUSTOMER[2],
        email_verified=True,
    )
    reviewers = [
        User(
            email=email,
            password_hash=hash_password("Reviewer-private-1"),
            full_name=name,
            phone=phone,
            email_verified=True,
        )
        for name, email, phone in REVIEWERS
    ]
    db.add_all([other, *reviewers])
    db.commit()

    db.add(
        Review(
            product_id=1,
            author_id=reviewers[0].id,
            rating=5,
            text="Juda tez qaynaydi. Jasur, Yunusobod. Tel: +998 93 555 11 22",
        )
    )
    db.add(
        Review(
            product_id=1,
            author_id=reviewers[1].id,
            rating=4,
            text="Yaxshi choynak, lekin biroz shovqinli.",
        )
    )
    db.add(
        Review(
            product_id=2,
            author_id=reviewers[1].id,
            rating=5,
            text="Piyolalar chiroyli, sovg'aga oldim.",
        )
    )

    courier = db.query(User).filter(User.role == Role.courier).one()
    statuses = [OrderStatus.paid, OrderStatus.paid, OrderStatus.shipped]
    for i, status in enumerate(statuses):
        order = Order(
            user_id=other.id,
            product_id=i + 1,
            quantity=1 + i,
            customer_name=other.full_name,
            phone=other.phone,
            address="Toshkent, Chilonzor 5-12",
            status=status,
            courier_id=courier.id if status == OrderStatus.shipped else None,
        )
        db.add(order)
        db.commit()
        db.add(OrderEvent(order_id=order.id, status=OrderStatus.new))
        db.add(OrderEvent(order_id=order.id, status=status))
        if status == OrderStatus.shipped:  # the newest one: both manager and courier see it
            order.attachment = _slip_image(order.id, other.full_name, "+998 97 765 43 21")
        db.commit()
