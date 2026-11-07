"""Parser snippets: prefix chains, guards, forms, React routes, models and E2E tests."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from yoriqnoma_scanner.detect import detect
from yoriqnoma_scanner.fs_guard import SafeFS
from yoriqnoma_scanner.parsers.e2e import E2EParser, data_for_value
from yoriqnoma_scanner.parsers.fastapi_routes import FastAPIParser
from yoriqnoma_scanner.parsers.i18n import flatten
from yoriqnoma_scanner.parsers.jsx_forms import JsxFormsParser
from yoriqnoma_scanner.parsers.pydantic_forms import PydanticFormsParser
from yoriqnoma_scanner.parsers.react_router import ReactRouterParser
from yoriqnoma_scanner.parsers.sqlalchemy_models import SQLAlchemyModelsParser, is_pii_name

_writer: Callable[[Path, dict[str, str]], Path] | None = None


@pytest.fixture(autouse=True)
def _use_writer(write_files: Callable[[Path, dict[str, str]], Path]) -> None:
    global _writer
    _writer = write_files


def _write(root: Path, files: dict[str, str]) -> Path:
    assert _writer is not None
    return _writer(root, files)


FASTAPI_PROJECT = {
    "pyproject.toml": '[project]\nname="x"\ndependencies=["fastapi", "sqlalchemy"]\n',
    "app/deps.py": """
from fastapi import Depends, HTTPException, Request
from typing import Annotated

def get_db():
    yield 1

def get_current_user(request: Request):
    if not request.cookies.get("s"):
        raise HTTPException(status_code=401)
    return 1

def require_admin(user=Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(status_code=403)

def mystery_guard():
    raise HTTPException(status_code=403)

def require_role(role):
    def check(user=Depends(get_current_user)):
        if user.role != role:
            raise HTTPException(status_code=403)
    return check

Manager = Annotated[int, Depends(require_role("manager"))]
""",
    "app/routes.py": """
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from app.deps import get_current_user, get_db, require_admin, mystery_guard, Manager

PATTERN = r"^\\+998\\d{9}$"

class OrderIn(BaseModel):
    phone: str = Field(pattern=PATTERN)
    quantity: int = Field(ge=1, le=99)
    note: str | None = None

router = APIRouter(prefix="/orders")
admin = APIRouter(dependencies=[Depends(require_admin)])
staff = APIRouter()

@router.post("")
def create(body: OrderIn, user=Depends(get_current_user), db=Depends(get_db)):
    return 1

@router.get("/{order_id}")
def view(order_id: int, user=Depends(get_current_user)):
    order = load(order_id)
    if order.owner_id != user.id:
        raise HTTPException(404)

@admin.get("/users")
def users():
    return []

@router.get("/weird", dependencies=[Depends(mystery_guard)])
def weird():
    return 1

@staff.post("/ship/{order_id}")
def ship(order_id: int, user: Manager):
    return 1
""",
    "app/main.py": """
from fastapi import FastAPI
from app import routes

app = FastAPI()
api = APIRouter(prefix="/api")
api.include_router(routes.router)
api.include_router(routes.admin, prefix="/admin")
api.include_router(routes.staff, prefix="/staff")
app.include_router(api)
""",
}


def _routes(tmp_path: Path) -> dict[str, list[str]]:
    _write(tmp_path, FASTAPI_PROJECT)
    fs = SafeFS(tmp_path)
    result = FastAPIParser().parse(detect(fs), fs)
    out = {}
    for r in result.routes:
        out[f"{r.methods[0]} {r.path}"] = [
            f"{g.kind}{':' + ','.join(g.roles) if g.roles else ''}{'!' if g.admin else ''}"
            for g in r.guards
        ]
    return out


def test_fastapi_prefix_chains_and_guards(tmp_path: Path) -> None:
    routes = _routes(tmp_path)

    assert routes["POST /api/orders"] == ["auth"]  # get_db is not a guard
    assert routes["GET /api/orders/:order_id"] == ["auth", "ownership"]
    assert routes["GET /api/admin/users"] == ["role:admin!"]
    assert routes["GET /api/orders/weird"] == ["unknown"]
    assert routes["POST /api/staff/ship/:order_id"] == ["role:manager"]


def test_pydantic_rules(tmp_path: Path) -> None:
    _write(tmp_path, FASTAPI_PROJECT)
    fs = SafeFS(tmp_path)
    models = PydanticFormsParser().parse(detect(fs), fs).request_models

    fields = {f.name: f for f in models["OrderIn"]}
    assert fields["phone"].type == "tel" and fields["phone"].rules == r"regex:^\+998\d{9}$"
    assert fields["quantity"].rules == "min:1|max:99" and fields["quantity"].type == "number"
    assert fields["note"].required is False


def test_sqlalchemy_entities_without_importing(tmp_path: Path) -> None:
    _write(
        tmp_path,
        {
            "pyproject.toml": '[project]\ndependencies=["fastapi","sqlalchemy"]\n',
            "m.py": """
import enum
from sqlalchemy import ForeignKey, Enum
from sqlalchemy.orm import Mapped, mapped_column, DeclarativeBase
class Base(DeclarativeBase): pass
class TicketState(enum.StrEnum):
    open = "open"
    closed = "closed"
class Ticket(Base):
    __tablename__ = "tickets"
    id: Mapped[int] = mapped_column(primary_key=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    contact_phone: Mapped[str] = mapped_column()
    title: Mapped[str] = mapped_column()
    status: Mapped[TicketState] = mapped_column(Enum(TicketState))
""",
        },
    )
    fs = SafeFS(tmp_path)
    [ticket] = SQLAlchemyModelsParser().parse(detect(fs), fs).entities

    assert ticket.name == "ticket" and ticket.owner_field == "author_id"
    assert ticket.statuses == ["open", "closed"] and ticket.status_field == "status"
    assert ticket.pii_fields == ["contact_phone"]


def test_pii_field_names() -> None:
    assert is_pii_name("full_name", "orders")
    assert is_pii_name("name", "users")
    assert not is_pii_name("name", "products")
    assert not is_pii_name("product_name", "orders")


REACT_PROJECT = {
    "web/package.json": '{"dependencies": {"react": "18", "react-router-dom": "6"}}',
    "web/src/locales/uz.json": (
        '{"btn": {"pay": "To\'lash", "ok": "Tasdiqlash"}, "f": {"name": "Ism"}}'
    ),
    "web/src/App.jsx": """
import { Routes, Route, Outlet } from "react-router-dom";
export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="cab" element={<RequireAuth><Outlet /></RequireAuth>}>
        <Route path="items/:id" element={<Item />} />
        <Route path="boss" element={<RequireRole role="manager"><Boss /></RequireRole>} />
      </Route>
      <Route path="admin/*" element={<AdminRoute><AdminHome /></AdminRoute>} />
    </Routes>
  );
}
""",
    "web/src/Item.jsx": """
import { useState } from "react";
import { t } from "./i18n";
export function Item() {
  const [open, setOpen] = useState(false);
  async function pay() { await api.post(`/api/items/${id}/pay`); }
  async function save(e) { await api.put("/api/items/1", {}); }
  return (
    <div>
      <button onClick={() => setOpen(true)}>{t("btn.pay")}</button>
      {open && (<div role="dialog"><button onClick={pay}>{t("btn.ok")}</button></div>)}
      <form onSubmit={save}>
        <label htmlFor="n">{t("f.name")}</label>
        <input id="n" name="full_name" required minLength={3} />
        <button type="submit">Saqlash</button>
      </form>
    </div>
  );
}
""",
}


def test_react_routes_nested_guards(tmp_path: Path) -> None:
    _write(tmp_path, REACT_PROJECT)
    fs = SafeFS(tmp_path)
    result = ReactRouterParser({}).parse(detect(fs), fs)
    pages = {r.path: (r.component, [g.kind for g in r.guards]) for r in result.routes}

    assert pages["/"] == ("Home", [])
    assert pages["/cab/items/:id"] == ("Item", ["auth"])
    assert pages["/cab/boss"] == ("Boss", ["auth", "role"])
    assert "/admin/*" not in pages  # catch-all
    assert "/cab" not in pages  # pure guard wrapper


def test_jsx_modal_opener_and_form_labels(tmp_path: Path) -> None:
    _write(tmp_path, REACT_PROJECT)
    fs = SafeFS(tmp_path)
    i18n = flatten({"btn": {"pay": "To'lash", "ok": "Tasdiqlash"}, "f": {"name": "Ism"}})
    item = JsxFormsParser(i18n).parse(detect(fs), fs).components["Item"]

    pay = next(a for a in item.actions if a.api_path.endswith("/pay"))
    assert (pay.trigger, pay.opener, pay.in_modal) == ("Tasdiqlash", "To'lash", True)
    [form] = item.forms
    assert form.api == "PUT /api/items/1"
    assert [(f.name, f.label, f.required, f.rules) for f in form.fields] == [
        ("full_name", "Ism", True, "min:3")
    ]


def test_e2e_values_become_generated_markers(tmp_path: Path) -> None:
    _write(
        tmp_path,
        {
            "web/package.json": '{"devDependencies": {"@playwright/test": "1"}}',
            "e2e/a.spec.ts": """
import { test, expect } from "@playwright/test";
test("kirish", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill("real.person@mail.uz");
  await page.getByRole("button", { name: "Kirish" }).click();
  await expect(page).toHaveURL(/dashboard/);
});
test("admin", async ({ page }) => { await page.goto("/admin/users"); });
""",
        },
    )
    fs = SafeFS(tmp_path)
    result = E2EParser().parse(detect(fs), fs)

    [flow] = result.flows
    assert [s.action for s in flow.steps] == ["goto", "fill", "click", "expect_url"]
    assert flow.steps[1].data == "fake:email"
    assert "real.person" not in flow.model_dump_json()
    assert any("admin" in n for n in result.notes)


def test_data_for_value() -> None:
    assert data_for_value("Telefon", "+998901112233") == "fake:phone_uz"
    assert data_for_value("To'liq ism", "Ali Valiyev") == "fake:full_name"
    assert data_for_value("Parol", "x") == "fake:password"
    assert data_for_value("Miqdor", "2") == "literal:2"
