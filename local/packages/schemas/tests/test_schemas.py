from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from yoriqnoma_schemas import (
    Blueprint,
    CaptureRun,
    Flow,
    Manual,
    Policy,
    RoleInfo,
    RouteInfo,
    Step,
    Target,
    load_json,
    save_json,
)
from yoriqnoma_schemas.export import export

REPO = Path(__file__).resolve().parents[4]
EXAMPLES = REPO / "docs" / "schemas" / "examples"
NOW = datetime(2026, 11, 8, tzinfo=UTC)


def flow(fid: str, requires: list[str] | None = None, role: str = "customer") -> Flow:
    return Flow(
        id=fid,
        title=fid,
        stage="core",
        role=role,
        requires=requires or [],
        source="test",
        steps=[Step(action="goto", path="/")],
    )


def blueprint(flows: list[Flow], **extra: Any) -> Blueprint:
    return Blueprint(
        project="t",
        base_url="http://127.0.0.1:8800/",  # type: ignore[arg-type]
        source="code",
        generated_at=NOW,
        generator="test",
        policy=Policy(target_role="customer"),
        roles=[
            RoleInfo(id="guest", label="Mehmon", kind="guest", reason="r", source="s"),
            RoleInfo(id="customer", label="Mijoz", kind="role", reason="r", source="s"),
            RoleInfo(id="admin", label="Admin", kind="excluded", reason="r", source="s"),
        ],
        flows=flows,
        **extra,
    )


# --- examples -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "model"),
    [("blueprint", Blueprint), ("capture", CaptureRun), ("manual", Manual)],
)
def test_examples_validate(name: str, model: type[BaseModel]) -> None:
    path = EXAMPLES / f"{name}.example.json"
    if not path.exists():
        pytest.skip("docs/ is not part of this checkout")
    assert isinstance(load_json(path, model), model)


def test_example_blueprint_has_demo_shop_roles() -> None:
    path = EXAMPLES / "blueprint.example.json"
    if not path.exists():
        pytest.skip("docs/ is not part of this checkout")
    bp = load_json(path, Blueprint)
    kinds = {r.id: r.kind for r in bp.roles}
    assert kinds == {
        "guest": "guest",
        "customer": "role",
        "manager": "role",
        "courier": "role",
        "admin": "excluded",
    }
    assert [r.id for r in bp.selectable_roles()] == ["customer", "manager", "courier"]


# --- validators -----------------------------------------------------------------------


def test_extra_fields_are_rejected() -> None:
    with pytest.raises(ValidationError, match="Extra inputs"):
        Target.model_validate({"role": "button", "colour": "red"})


def test_target_needs_one_field() -> None:
    with pytest.raises(ValidationError, match="at least one"):
        Target()


def test_unknown_requires_is_rejected() -> None:
    with pytest.raises(ValidationError, match="requires unknown flows"):
        blueprint([flow("a", ["missing"])])


def test_cycle_is_reported_with_its_path() -> None:
    with pytest.raises(ValidationError, match="a -> b -> c -> a"):
        blueprint([flow("a", ["b"]), flow("b", ["c"]), flow("c", ["a"])])


def test_self_cycle() -> None:
    with pytest.raises(ValidationError, match="a -> a"):
        blueprint([flow("a", ["a"])])


def test_flow_cannot_use_excluded_role() -> None:
    with pytest.raises(ValidationError, match="excluded role"):
        blueprint([flow("a", role="admin")])


def test_pages_cannot_hold_excluded_routes() -> None:
    bad = RouteInfo(path="/admin", kind="page", access="excluded", reason="r", source="s")
    with pytest.raises(ValidationError, match="must not contain excluded"):
        blueprint([], pages=[bad])


def test_route_roles_must_be_usable() -> None:
    bad = RouteInfo(path="/x", kind="page", access="roles", roles=["admin"], reason="r", source="s")
    with pytest.raises(ValidationError, match="excluded role"):
        blueprint([], pages=[bad])


def test_excluded_list_holds_only_excluded() -> None:
    ok = RouteInfo(path="/x", kind="page", access="guest", reason="r", source="s")
    with pytest.raises(ValidationError, match="non-excluded"):
        blueprint([], excluded=[ok])


def test_deny_paths_must_be_globs() -> None:
    with pytest.raises(ValidationError, match="path glob"):
        Policy(target_role="customer", deny_paths=["admin"])


def test_steps_need_their_fields() -> None:
    with pytest.raises(ValidationError, match="needs a target"):
        Step(action="click")
    with pytest.raises(ValidationError, match="needs a path"):
        Step(action="goto")
    with pytest.raises(ValidationError, match="needs data"):
        Step(action="fill", target=Target(label="Ism"))


# --- helpers --------------------------------------------------------------------------


def test_topo_order_respects_requires_and_keeps_order() -> None:
    bp = blueprint([flow("pay", ["create"]), flow("create", ["register"]), flow("register")])

    assert [f.id for f in bp.topo_order()] == ["register", "create", "pay"]


def test_topo_order_is_stable_for_independent_flows() -> None:
    bp = blueprint([flow("b"), flow("a"), flow("c", ["a"])])

    assert [f.id for f in bp.topo_order()] == ["b", "a", "c"]


def test_requirement_closure() -> None:
    bp = blueprint([flow("register"), flow("create", ["register"]), flow("other")])

    assert [f.id for f in bp.requirement_closure(["create"])] == ["register", "create"]


def test_content_hash_ignores_generation_time() -> None:
    a = blueprint([flow("a")])
    b = a.model_copy(update={"generated_at": datetime(2030, 1, 1, tzinfo=UTC)})
    c = blueprint([flow("a"), flow("b")])

    assert a.content_hash() == b.content_hash()
    assert a.content_hash() != c.content_hash()


def test_round_trip(tmp_path: Path) -> None:
    bp = blueprint([flow("register"), flow("create", ["register"])])

    path = save_json(tmp_path / "sub" / "blueprint.json", bp)

    assert load_json(path, Blueprint) == bp
    text = path.read_text(encoding="utf-8")
    assert "Mijoz" in text and "\\u" not in text


def test_export_writes_three_schemas(tmp_path: Path) -> None:
    paths = export(tmp_path)

    assert sorted(p.name for p in paths) == [
        "blueprint.schema.json",
        "capture.schema.json",
        "manual.schema.json",
    ]
    schema = json.loads((tmp_path / "blueprint.schema.json").read_text(encoding="utf-8"))
    assert "roles" in schema["properties"]
