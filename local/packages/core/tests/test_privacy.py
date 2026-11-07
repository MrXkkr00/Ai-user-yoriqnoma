"""Test data generator, stable fakes (HMAC) and the replacement decisions (FR-E4, FR-E10)."""

from __future__ import annotations

import re
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from yoriqnoma_core.explorer.bundle import make_bundle, verify_bundle
from yoriqnoma_core.explorer.datagen import DataGen
from yoriqnoma_core.explorer.pseudonymize import PrivacyLedger
from yoriqnoma_schemas import Entity

KEY = b"0123456789abcdef0123456789abcdef"


def gen(run_id: str = "run-1") -> DataGen:
    return DataGen("seed", run_id, KEY)


def test_identity_is_deterministic_and_valid() -> None:
    a = gen().identity("customer", "A", "yoriqnoma.test")
    b = gen().identity("customer", "A", "yoriqnoma.test")

    assert a == b
    assert re.fullmatch(r"\+998\d{9}", a.phone)
    assert len(a.password) >= 8 and a.email.endswith("@yoriqnoma.test")
    assert gen().identity("customer", "B", "yoriqnoma.test").email != a.email


def test_values_follow_rules() -> None:
    g = gen()
    assert len(g.value("text", "min:30|max:40")) in range(30, 41)
    assert g.value("number", "min:3|max:3") == "3"


def test_substitute_is_stable_and_run_scoped() -> None:
    real = "Dilnoza Karimova"
    one = gen().substitute("name", real)

    assert one == gen().substitute("name", "  dilnoza   karimova ")
    assert one != real
    assert gen("run-2").substitute("name", real) != one


def test_substitute_is_stable_across_processes() -> None:
    code = (
        "from yoriqnoma_core.explorer.datagen import DataGen;"
        f"print(DataGen('seed', 'run-1', {KEY!r}).substitute('phone', '+998 97 765 43 21'))"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)

    assert out.stdout.strip() == gen().substitute("phone", "+998 97 765 43 21")
    assert out.stdout.strip().startswith("+998 ")  # layout of the real value is kept


def test_one_record_one_fake_person() -> None:
    g = gen()
    name = g.substitute("name", "Dilnoza Karimova", record_key="+998977654321")
    phone = g.substitute("phone", "+998977654321", record_key="+998977654321")
    person = g.fake_person("+998977654321")

    assert name == person.full_name
    assert phone.endswith(person.phone[-7:])


def test_key_never_in_repr() -> None:
    assert KEY.decode() not in repr(gen())
    with pytest.raises(ValueError):
        DataGen("s", "r", b"short")


def ledger() -> PrivacyLedger:
    return PrivacyLedger(
        datagen=gen(),
        base_url="http://127.0.0.1:8800/",
        entities={
            "order": Entity(
                name="order",
                source="s",
                owner_field="user_id",
                pii_fields=["customer_name", "phone", "address"],
                created_by=["customer"],
            ),
            "review": Entity(
                name="review", source="s", owner_field="author_id", created_by=["customer"]
            ),
            "product": Entity(name="product", source="s"),
        },
        self_signup_roles={"customer"},
        own_ids={"order": {"7"}},
    )


def test_json_foreign_records_are_replaced_and_own_kept() -> None:
    led = ledger()
    data = [
        {
            "id": 1,
            "customer_name": "Dilnoza Karimova",
            "phone": "+998977654321",
            "address": "Toshkent, Chilonzor 5-12",
            "status": "paid",
        },
        {"id": 7, "customer_name": "Aziz Test", "phone": "+998901112233", "status": "new"},
    ]

    out = led.transform_json(data, "/api/staff/orders")

    assert out[0]["customer_name"] != "Dilnoza Karimova" and out[0]["status"] == "paid"
    assert "977654321" not in str(out)
    assert out[1]["customer_name"] == "Aziz Test"
    assert "Aziz Test" in led.test_values
    again = led.transform_json(data, "/api/staff/orders/1")
    assert again[0]["customer_name"] == out[0]["customer_name"]


def test_json_user_content_text_is_replaced() -> None:
    led = ledger()
    data = [
        {
            "id": 1,
            "author_name": "Jasur Toshmatov",
            "rating": 5,
            "text": "Juda yaxshi. Tel: +998 93 555 11 22",
        }
    ]

    out = led.transform_json(data, "/api/products/1/reviews")

    assert "Jasur" not in str(out) and "555" not in str(out)
    assert out[0]["rating"] == 5


def test_json_published_records_are_kept() -> None:
    led = ledger()
    data = [{"id": 1, "name": "Choynak", "price": 1}]

    assert led.transform_json(data, "/api/products") == data


def _node(
    i: int, text: str, zone: str, block: int = -1, structural: str | None = None
) -> dict[str, object]:
    return {
        "i": i,
        "text": text,
        "zone": zone,
        "block": block,
        "structural": structural,
        "interactive": False,
    }


def test_dom_decisions_by_zone() -> None:
    led = ledger()
    scan = {
        "nodes": [
            _node(0, "Email: info@demo-shop.uz", "org"),
            _node(1, "Tel: +998 71 200-00-00", "org"),
            _node(2, "Muallif: Komron Çegaboyev", "editorial"),
            _node(3, "Dilnoza Karimova", "other", block=1, structural="name"),
            _node(4, "+998 97 765 43 21", "other", block=1),
            _node(5, "Jasur Toshmatov", "user_content", block=2, structural="name"),
            _node(6, "Juda tez qaynaydi, Yunusobodda yashayman.", "user_content", block=2),
        ],
        "inputs": [],
        "images": [],
    }

    decision = led.decide_dom(scan)
    changed = {d["i"]: d["text"] for d in decision.nodes}

    assert set(changed) == {3, 4, 5, 6}
    assert "info@demo-shop.uz" in led.public_values and "+998 71 200-00-00" in led.public_values
    assert "Komron" not in str(changed)
    assert all("Dilnoza" not in t and "765" not in t and "Jasur" not in t for t in changed.values())
    assert decision.counts["org:kept"] == 2 and decision.counts["editorial:kept"] == 1


def test_bundle_has_only_allowed_files_and_rejects_zip_slip(tmp_path: Path) -> None:
    run = tmp_path / "run"
    (run / "capture" / "images").mkdir(parents=True)
    (run / "capture" / "capture.json").write_text("{}", encoding="utf-8")
    (run / "capture" / "images" / "s001_clean.png").write_bytes(b"png")
    (run / "capture" / "images" / "notes.txt").write_text("x", encoding="utf-8")
    (run / "capture" / "progress.json").write_text("{}", encoding="utf-8")
    (run / "blueprint.json").write_text("{}", encoding="utf-8")

    bundle = make_bundle(run)
    files = verify_bundle(bundle)

    assert set(files) == {"blueprint.json", "capture/capture.json", "capture/images/s001_clean.png"}
    evil = tmp_path / "evil.zip"
    with zipfile.ZipFile(evil, "w") as zf:
        zf.writestr("../../escape.json", "{}")
    with pytest.raises(ValueError, match="xavfli"):
        verify_bundle(evil)
