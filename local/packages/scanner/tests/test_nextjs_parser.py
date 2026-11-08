"""Next.js snippets: app and pages routers, middleware, layouts, API handlers, Prisma (T29)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from yoriqnoma_scanner.api import scan
from yoriqnoma_scanner.parsers.nextjs import segment_path

Writer = Callable[[Path, dict[str, str]], Path]

NEXT_PROJECT = {
    "package.json": (
        '{"dependencies": {"next": "14.2.3", "react": "18.3.1", "next-auth": "4.24.7",'
        ' "@prisma/client": "5.14.0"}}'
    ),
    "prisma/schema.prisma": """
enum Role {
  CUSTOMER
  MANAGER
  ADMIN
}

enum OrderStatus {
  NEW
  PAID
  SHIPPED
}

model User {
  id     Int     @id @default(autoincrement())
  email  String  @unique
  phone  String?
  role   Role    @default(CUSTOMER)
  orders Order[]
}

model Order {
  id      Int         @id @default(autoincrement())
  userId  Int
  user    User        @relation(fields: [userId], references: [id])
  address String
  status  OrderStatus @default(NEW)
}
""",
    "middleware.ts": """
export { default } from "next-auth/middleware";
export const config = { matcher: ["/dashboard/:path*", "/admin/:path*"] };
""",
    "app/page.tsx": "export default function HomePage() { return <h1>Bosh sahifa</h1>; }\n",
    "app/(auth)/register/page.tsx": """'use client';
export default function RegisterPage() {
  async function onSubmit(e) {
    e.preventDefault();
    await fetch('/api/register', { method: 'POST', body: '' });
  }
  return (
    <form onSubmit={onSubmit}>
      <label htmlFor="email">Email</label>
      <input id="email" name="email" type="email" required />
      <label htmlFor="password">Parol</label>
      <input id="password" name="password" type="password" minLength={8} required />
      <button type="submit">Ro'yxatdan o'tish</button>
    </form>
  );
}
""",
    "app/dashboard/orders/page.tsx": """'use client';
import { useEffect, useState } from 'react';
export default function OrdersPage() {
  const [orders, setOrders] = useState([]);
  useEffect(() => { fetch('/api/orders').then((r) => r.json()).then(setOrders); }, []);
  async function create(e) {
    e.preventDefault();
    await fetch('/api/orders', { method: 'POST' });
  }
  return (
    <form onSubmit={create}>
      <label htmlFor="address">Manzil</label>
      <input id="address" name="address" required />
      <button type="submit">Buyurtma berish</button>
    </form>
  );
}
""",
    "app/dashboard/staff/layout.tsx": """
import { getServerSession } from 'next-auth';
import { redirect } from 'next/navigation';
export default async function StaffLayout({ children }) {
  const session = await getServerSession();
  if (session?.user.role !== 'MANAGER') redirect('/');
  return children;
}
""",
    "app/dashboard/staff/page.tsx": """'use client';
export default function StaffOrdersPage() {
  async function ship(id) {
    await fetch(`/api/orders/${id}/ship`, { method: 'POST' });
  }
  return <ul><li><button onClick={() => ship(1)}>Jo'natish</button></li></ul>;
}
""",
    "app/admin/page.tsx": "export default function AdminPage() { return <h1>Admin</h1>; }\n",
    "app/_lib/db.ts": "export const prisma = {};\n",
    "app/api/register/route.ts": """
import { prisma } from '../../_lib/db';
export async function POST(req: Request) {
  const data = await req.json();
  const user = await prisma.user.create({ data: { email: data.email } });
  return Response.json(user);
}
""",
    "app/api/orders/route.ts": """
import { getServerSession } from 'next-auth';
import { prisma } from '../../_lib/db';
export async function GET() {
  const session = await getServerSession();
  if (!session) return Response.json({}, { status: 401 });
  return Response.json(await prisma.order.findMany({ where: { userId: session.user.id } }));
}
export async function POST(req: Request) {
  const session = await getServerSession();
  if (!session) return Response.json({}, { status: 401 });
  const order = await prisma.order.create({
    data: { userId: session.user.id, address: '', status: 'NEW' },
  });
  return Response.json(order);
}
""",
    "pages/api/orders/[id]/ship.ts": """
import { getServerSession } from 'next-auth';
export default async function handler(req, res) {
  const session = await getServerSession(req, res);
  if (session?.user.role !== 'MANAGER') return res.status(403).end();
  if (req.method === 'POST') {
    const order = await prisma.order.findUnique({ where: { id: Number(req.query.id) } });
    if (order.status !== 'NEW') return res.status(409).end();
    await prisma.order.update({ where: { id: order.id }, data: { status: 'SHIPPED' } });
    return res.json({ ok: true });
  }
}
""",
}


def test_segment_paths() -> None:
    assert segment_path(["(shop)", "orders", "[id]"]) == "/orders/:id"
    assert segment_path(["docs", "[...slug]"]) == "/docs/:slug"
    assert segment_path(["@modal", "photo", "[[...rest]]"]) == "/photo/:rest"
    assert segment_path(["_lib"]) is None


def test_next_routes_guards_handlers_and_prisma(tmp_path: Path, write_files: Writer) -> None:
    result = scan(write_files(tmp_path, NEXT_PROJECT), "http://127.0.0.1:3000")
    bp = result.blueprint
    kinds = {r.id: r.kind for r in bp.roles}
    pages = {p.path: (p.access, p.roles) for p in bp.pages if p.kind == "page"}
    api = {(p.path, m): p for p in bp.pages if p.kind == "api" for m in p.methods}
    excluded = {p.path for p in bp.excluded}

    assert "next" in result.stacks
    assert kinds == {"guest": "guest", "CUSTOMER": "role", "MANAGER": "role", "ADMIN": "excluded"}
    customer = bp.role("CUSTOMER")
    assert customer is not None and customer.self_signup and customer.label == "Mijoz"
    assert pages["/"][0] == "guest" and pages["/register"][0] == "guest"
    assert pages["/dashboard/orders"] == ("roles", ["CUSTOMER", "MANAGER"])
    assert pages["/dashboard/staff"] == ("roles", ["MANAGER"])  # layout role check
    assert "/admin" in excluded
    assert api[("/api/orders", "POST")].roles == ["CUSTOMER", "MANAGER"]
    assert api[("/api/orders/:id/ship", "POST")].roles == ["MANAGER"]
    order = bp.entity("order")
    assert order is not None and order.owner_field == "userId"
    reach = {s.value: s.reachable_by for s in order.statuses}
    assert reach == {"NEW": ["CUSTOMER", "MANAGER"], "PAID": [], "SHIPPED": ["MANAGER"]}

    flows = {f.id: f for f in bp.flows}
    labels = [
        s.target.label for s in flows["CUSTOMER.register"].steps if s.target and s.target.label
    ]
    assert labels == ["Email", "Parol"]
    assert flows["CUSTOMER.order.create"].steps[0].path == "/dashboard/orders"
    ship = flows["MANAGER.order.ship"]
    assert ship.needs_status == ["NEW"] and ship.sets_status == "SHIPPED"
