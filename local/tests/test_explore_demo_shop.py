"""QM-2 and the privacy part of QM-3 on a live demo_shop (slow: starts a browser)."""

from __future__ import annotations

import asyncio
import zipfile
from pathlib import Path

import pytest
from demo_shop.seed import OTHER_CUSTOMER, REVIEWERS
from pydantic import SecretBytes, SecretStr

from yoriqnoma_core.explorer.bundle import make_bundle
from yoriqnoma_core.explorer.options import (
    AccountCredentials,
    Cancelled,
    ExploreOptions,
    NeverCancel,
    NoHuman,
    NullProgress,
)
from yoriqnoma_core.explorer.privilege import PrivilegedAccountError
from yoriqnoma_core.explorer.runner import RunAborted, run_explorer
from yoriqnoma_scanner.api import scan
from yoriqnoma_schemas import Blueprint, CaptureRun, save_json

DEMO_SHOP = Path(__file__).resolve().parent.parent / "fixtures" / "demo_shop"
SEED_VALUES = [
    OTHER_CUSTOMER[0],
    OTHER_CUSTOMER[1],
    OTHER_CUSTOMER[2],
    "765 43 21",
    "977654321",
    "Chilonzor 5-12",
    *(v for r in REVIEWERS for v in r),
    "Jasur",
    "555 11 22",
]
pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def blueprint(demo_shop_url: str) -> Blueprint:
    return scan(DEMO_SHOP, demo_shop_url, project="demo_shop").blueprint


def options(url: str, var: Path, role: str, run_id: str, **extra: object) -> ExploreOptions:
    return ExploreOptions(
        base_url=url,
        role=role,
        accounts={
            "manager": {
                "A": AccountCredentials(
                    login="manager@demo.local", password=SecretStr("Manager12345")
                )
            },
            "courier": {
                "A": AccountCredentials(
                    login="courier@demo.local", password=SecretStr("Courier12345")
                )
            },
        },
        mailbox_kind="dir",
        mailbox_target=str(var / "mail"),
        allow_private=True,
        pseudonym_key=SecretBytes(b"test-key-0123456789abcdef-0123456"),
        run_id=run_id,
        **extra,  # type: ignore[arg-type]
    )


def explore(
    bp: Blueprint, run_dir: Path, opts: ExploreOptions, cancel: object = None
) -> CaptureRun:
    save_json(run_dir / "blueprint.json", bp)
    return asyncio.run(
        run_explorer(bp, run_dir, opts, NoHuman(), NullProgress(), cancel or NeverCancel())  # type: ignore[arg-type]
    )


@pytest.fixture(scope="module")
def runs(
    blueprint: Blueprint,
    demo_shop_url: str,
    demo_shop_var: Path,
    tmp_path_factory: pytest.TempPathFactory,
) -> dict[str, tuple[Path, CaptureRun]]:
    out: dict[str, tuple[Path, CaptureRun]] = {}
    for role in ("manager", "courier", "customer"):  # manager first: it sees the seed orders
        run_dir = tmp_path_factory.mktemp(f"run_{role}")
        opts = options(demo_shop_url, demo_shop_var, role, f"test-{role}")
        out[role] = (run_dir, explore(blueprint, run_dir, opts))
    return out


@pytest.mark.parametrize("role", ["customer", "manager", "courier"])
def test_qm2_flows_verified_and_no_admin(
    runs: dict[str, tuple[Path, CaptureRun]], role: str
) -> None:
    _, cap = runs[role]
    own = [f for f in cap.flows if not f.helper]
    verified = [f for f in own if f.status == "verified"]

    assert len(verified) / len(own) >= 0.9, [(f.flow_id, f.reason) for f in own]
    assert cap.privilege_ok is True
    assert not [s for s in cap.states if "/admin" in s.url]
    assert not [b for b in cap.firewall_log if "/admin" in b.url]


@pytest.mark.parametrize("role", ["customer", "manager", "courier"])
def test_qm3_no_real_data_of_other_people(
    runs: dict[str, tuple[Path, CaptureRun]], role: str
) -> None:
    run_dir, cap = runs[role]
    texts = [(run_dir / "capture" / "capture.json").read_text(encoding="utf-8")]
    bundle = make_bundle(run_dir)
    with zipfile.ZipFile(bundle) as zf:
        texts += [zf.read(n).decode("utf-8") for n in zf.namelist() if n.endswith(".json")]

    for text in texts:
        for value in SEED_VALUES:
            assert value not in text, f"{value!r} leaked in {role}"
    assert {"info@demo-shop.uz", "+998 71 200-00-00"} <= set(cap.public_values)


def test_reviews_are_replaced_for_the_customer(runs: dict[str, tuple[Path, CaptureRun]]) -> None:
    _, cap = runs["customer"]
    product_states = [s for s in cap.states if s.url.endswith("/catalog/1")]

    assert product_states
    assert any(s.substituted > 0 for s in product_states)


def test_manager_sees_slip_blurred_by_ocr(runs: dict[str, tuple[Path, CaptureRun]]) -> None:
    _, cap = runs["manager"]
    reasons = [h.reason for s in cap.states for h in s.hidden]

    assert any("OCR" in r for r in reasons), reasons
    assert any(s.trigger and not s.flow_id for s in cap.states)  # foreign record detail


def test_patched_statuses_for_unreachable_ones(runs: dict[str, tuple[Path, CaptureRun]]) -> None:
    _, cap = runs["customer"]
    patched = {s.entity_status for s in cap.states if s.patched}

    assert {"shipped", "delivered", "refunded"} <= patched


def test_helper_objects_and_own_objects(runs: dict[str, tuple[Path, CaptureRun]]) -> None:
    _, cap = runs["courier"]
    helpers = {f.flow_id for f in cap.flows if f.helper}

    assert {"customer.order.create", "customer.order.pay", "manager.order.ship"} <= helpers
    assert cap.own_objects["order"]


class CancelAfter:
    def __init__(self, n: int) -> None:
        self.calls = 0
        self.n = n

    def is_cancelled(self) -> bool:
        self.calls += 1
        return self.calls > self.n


def test_resume_after_cancel(
    blueprint: Blueprint, demo_shop_url: str, demo_shop_var: Path, tmp_path: Path
) -> None:
    opts = options(
        demo_shop_url, demo_shop_var, "manager", "test-resume", state_graph=False, patching=False
    )
    with pytest.raises(Cancelled):
        explore(blueprint, tmp_path, opts, CancelAfter(25))
    progress = (tmp_path / "capture" / "progress.json").read_text(encoding="utf-8")
    done_before = progress.count('"status": "verified"')
    assert done_before >= 1

    cap = explore(blueprint, tmp_path, opts)

    assert all(f.status == "verified" for f in cap.flows if not f.helper)
    assert len({s.id for s in cap.states}) == len(cap.states)


def test_admin_account_stops_the_run(
    blueprint: Blueprint, demo_shop_url: str, demo_shop_var: Path, tmp_path: Path
) -> None:
    opts = options(
        demo_shop_url, demo_shop_var, "manager", "test-admin", state_graph=False, patching=False
    )
    opts.accounts["manager"]["A"] = AccountCredentials(
        login="admin@demo.local", password=SecretStr("Admin12345")
    )

    with pytest.raises((RunAborted, PrivilegedAccountError), match="Imtiyoz|admin|rolida"):
        explore(blueprint, tmp_path, opts)
