"""Writer (FakeProvider) and renderer on a small synthetic run folder."""

from __future__ import annotations

import asyncio
import json
import shutil
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pytest
from markupsafe import escape
from PIL import Image, ImageDraw
from pydantic import HttpUrl

from yoriqnoma_core.explorer.datagen import DataGen
from yoriqnoma_core.render import build
from yoriqnoma_core.text_uz import normalize_uz
from yoriqnoma_core.writer import write_manual
from yoriqnoma_core.writer.assemble import element_marker
from yoriqnoma_core.writer.cache import LLMCache, cached_generate
from yoriqnoma_core.writer.changes import compare, write_changelog
from yoriqnoma_core.writer.providers import FakeProvider, LLMRequest
from yoriqnoma_core.writer.templates_uz import step_sentence
from yoriqnoma_core.writer.validate import check_text, known_set, name_matches
from yoriqnoma_schemas import (
    BBox,
    Blueprint,
    CaptureRun,
    Element,
    Flow,
    FlowResult,
    Policy,
    RoleInfo,
    State,
    Step,
    Target,
    load_json,
    save_json,
)
from yoriqnoma_schemas.manual import Manual

NOW = datetime(2026, 11, 8, tzinfo=UTC)


def _image(path: Path, text: str) -> None:
    img = Image.new("RGB", (1280, 800), "white")
    draw = ImageDraw.Draw(img)
    draw.rectangle((400, 300, 700, 340), outline="black")
    draw.text((410, 310), text, fill="black")
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)


def make_run(tmp: Path, guest_only: bool = False) -> Path:
    roles = [
        RoleInfo(id="guest", label="Mehmon", kind="guest", reason="r", source="s"),
        RoleInfo(
            id="customer", label="Mijoz", kind="role", reason="r", source="s", self_signup=True
        ),
    ]
    steps = [
        Step(action="goto", path="/register"),
        Step(action="fill", target=Target(label="Email"), data="fake:email"),
        Step(action="click", target=Target(role="button", name="Yuboriş")),
    ]
    flows = [
        Flow(
            id="guest.page.home",
            title="Bosh sahifa",
            stage="core",
            role="guest",
            source="s",
            steps=[Step(action="goto", path="/")],
        )
    ]
    if not guest_only:
        flows.append(
            Flow(
                id="customer.register",
                title="Ro'yxatdan o'tish",
                stage="start",
                role="customer",
                action="register",
                source="s",
                steps=steps,
            )
        )
    bp = Blueprint(
        project="t",
        base_url=HttpUrl("http://127.0.0.1:8800/"),
        source="code",
        generated_at=NOW,
        generator="test",
        policy=Policy(target_role="customer"),
        roles=roles,
        flows=flows,
        nav=[{"label": "Ro'yxat", "path": "/register"}],
    )
    run = tmp / "run"
    save_json(run / "blueprint.json", bp)
    els = [
        Element(
            marker=1,
            role="textbox",
            name="Email",
            bbox=BBox(x=400, y=300, w=300, h=40),
            selector=Target(label="Email"),
            kind="input",
        ),
        Element(
            marker=2,
            role="button",
            name="Yuboriş",
            bbox=BBox(x=400, y=400, w=120, h=40),
            selector=Target(role="button", name="Yuboriş"),
            kind="button",
        ),
    ]
    states = []
    for sid, idx in (("s001", 1), ("s002", 2), ("s003", 3), ("s004", 1)):
        _image(run / "capture" / "images" / f"{sid}_clean.png", sid)
        _image(run / "capture" / "images" / f"{sid}_som.png", sid)
        states.append(
            State(
                id=sid,
                hash=sid,
                url="http://127.0.0.1:8800/register",
                title="t",
                flow_id="guest.page.home" if sid == "s004" else "customer.register",
                step_index=idx,
                account="A",
                images={"clean": f"images/{sid}_clean.png", "som": f"images/{sid}_som.png"},
                elements=els,
            )
        )
    results = [FlowResult(flow_id="guest.page.home", status="verified", state_ids=["s004"])]
    if not guest_only:
        results.append(
            FlowResult(
                flow_id="customer.register", status="verified", state_ids=["s001", "s002", "s003"]
            )
        )
    else:
        states = [s for s in states if s.id == "s004"]
    cap = CaptureRun(
        run_id="r",
        blueprint_hash="h",
        role="customer",
        role_label="Mijoz",
        base_url=HttpUrl("http://127.0.0.1:8800/"),
        environment="staging",
        started_at=NOW,
        flows=results,
        states=states,
    )
    save_json(run / "capture" / "capture.json", cap)
    return run


def test_manual_has_nine_sections_and_renders(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    manual, stats = asyncio.run(write_manual(run, FakeProvider()))

    assert [s.stage for s in manual.sections][:9] == [
        "start",
        "core",
        "manage",
        "social",
        "payment",
        "settings",
        "exit",
        "reference",
        "faq",
    ]
    start = manual.sections[0]
    assert "«Mijoz» roli uchun" in start.intro and "ro'yxatdan" in start.intro
    article = start.articles[0]
    assert article.steps[1].text == "«Email» maydoniga email manzilingizni kiriting ①."
    assert article.steps[2].markers == [2] and "«Yuboriş»" in article.steps[2].text
    assert stats.calls > 0 and manual.coverage.percent

    result = build(run, {"html", "docx"})
    html = result.files["html"].read_text(encoding="utf-8")
    assert all(str(escape(s.title)) in html for s in manual.sections)
    assert (result.out_dir / "html" / "assets" / "search_index.json").is_file()
    with zipfile.ZipFile(result.files["docx"]) as zf:
        document = zf.read("word/document.xml").decode("utf-8")
    assert document.count('w:val="Heading1"') == len(manual.sections) + 1  # + Mundarija


def test_guest_only_site_still_has_nine_sections(tmp_path: Path) -> None:
    run = make_run(tmp_path, guest_only=True)
    manual, _ = asyncio.run(write_manual(run, FakeProvider()))
    empty = [s for s in manual.sections if s.empty_reason]

    assert len([s for s in manual.sections if s.stage != "unverified"]) == 9
    assert {s.stage for s in empty} >= {"start", "manage", "social", "payment", "exit"}
    assert all("topilmadi" in s.intro for s in empty)
    reasons = [i.reason for i in manual.coverage.items if i.kind == "section" and not i.covered]
    assert reasons and all(reasons)


def test_validate_names_in_both_alphabets() -> None:
    known = known_set(["Yuboriş", "Özbekça", "Ro'yxatdan o'tish"])

    assert name_matches("Yuborish", known)
    assert name_matches("O'zbekcha", known)
    soft, hard = check_text("«Yuborish» tugmasini bosing, keyin «Mavjud emas».", known, [])
    assert soft == ["«Mavjud emas» nomi sahifada topilmadi"] and hard == []
    _, hard = check_text("Admin panelga kiring: ali@mail.uz", known, [])
    assert len(hard) == 2


def test_step_templates() -> None:
    fill = Step(
        action="fill", target=Target(label="Parol"), data="fake:password", rules="min:8|max:64"
    )
    phone = Step(action="fill", target=Target(label="Telefon raqami"), data="fake:phone_uz")
    confirm = Step(action="click", target=Target(role="button", name="Ha"), confirm=True)

    assert (
        step_sentence(fill, 3, None)
        == "«Parol» maydoniga parolingizni (kamida 8 ta belgi) kiriting ③."
    )
    assert "+998901234567" in (step_sentence(phone, None, None) or "")
    assert step_sentence(confirm, 1, None) == "Tasdiqlash oynasida «Ha» tugmasini bosing ①."
    assert step_sentence(Step(action="expect_url", path="/x"), None, None) is None


def test_marker_lookup_tolerates_alphabets() -> None:
    state = State(
        id="s",
        hash="h",
        url="u",
        title="t",
        account="A",
        images={"clean": "a", "som": "b"},
        elements=[
            Element(
                marker=4,
                role="button",
                name="Yuboriş",
                bbox=BBox(x=0, y=0, w=1, h=1),
                selector=Target(css="b"),
                kind="button",
            )
        ],
    )
    step = Step(action="click", target=Target(role="button", name="Yuboriş"))

    assert element_marker(state, step) == 4
    assert normalize_uz("Yuboriş") == "yuborish"


def test_cache_hit_skips_the_provider(tmp_path: Path) -> None:
    provider = FakeProvider()
    cache = LLMCache(tmp_path)
    req = LLMRequest(task="faq", system="s", prompt="p")
    from yoriqnoma_core.writer.answers import FAQAnswer

    first = asyncio.run(cached_generate(provider, cache, req, FAQAnswer, "1"))
    second = asyncio.run(cached_generate(provider, cache, req, FAQAnswer, "1"))

    assert not first.cached and second.cached
    assert len(provider.calls) == 1
    asyncio.run(cached_generate(provider, cache, req, FAQAnswer, "2"))
    assert len(provider.calls) == 2  # new prompt version -> new call


@pytest.mark.slow
def test_pdf_and_js_search_normalization(tmp_path: Path) -> None:
    from playwright.sync_api import sync_playwright

    run = make_run(tmp_path)
    asyncio.run(write_manual(run, FakeProvider()))
    result = build(run, {"html", "pdf"})
    assert result.files["pdf"].stat().st_size > 1000
    samples = ["Öçiriş", "O‘CHIRISH", "oʻchirish", "Yuboriş", "Tölaş", "  Ğalaba  ", "Şahar"]
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        page.goto(result.files["html"].resolve().as_uri())
        got = [page.evaluate("s => window.normalizeUz(s)", s) for s in samples]
        browser.close()
    assert got == [normalize_uz(s) for s in samples]


@pytest.mark.llm
def test_ollama_answers_in_schema() -> None:
    from yoriqnoma_core.writer.answers import FlowDescription
    from yoriqnoma_core.writer.providers import OllamaProvider

    provider = OllamaProvider()
    provider.check()
    req = LLMRequest(
        task="describe_flow",
        system="O'zbek tilida yozing.",
        prompt="Vazifa: «Ro'yxatdan o'tish». purpose va notes yozing.",
    )
    result = asyncio.run(provider.generate(req, FlowDescription))

    assert result.data.purpose


def test_manual_example_still_valid() -> None:
    path = (
        Path(__file__).resolve().parents[4]
        / "docs"
        / "schemas"
        / "examples"
        / "manual.example.json"
    )
    if path.exists():
        Manual.model_validate_json(path.read_text(encoding="utf-8"))


# --- T30: tours, GIF, changelog, stable fakes -----------------------------------

T30_KEY = b"k" * 32


def _with_css(run: Path) -> None:
    capture_path = run / "capture" / "capture.json"
    cap = load_json(capture_path, CaptureRun)
    for state in cap.states:
        state.elements = [
            e.model_copy(update={"css": "#email" if e.marker == 1 else "form > button"})
            for e in state.elements
        ]
        state.url = "http://127.0.0.1:8800/register/42"  # a record of the test account
    save_json(capture_path, cap)


def test_tour_and_gif_exports(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    _with_css(run)
    asyncio.run(write_manual(run, FakeProvider()))

    result = build(run, {"html", "tour", "gif"})

    tours = json.loads(result.files["tour"].read_text(encoding="utf-8"))
    steps = tours["customer.register"]["steps"]
    assert steps[1]["path"] == "/register/:id" and steps[1]["element"] == "#email"
    assert steps[2]["element"] == "form > button"
    assert "«Yuboriş»" in steps[2]["popover"]["description"]
    assert "②" not in steps[2]["popover"]["description"]  # image markers are not in tours
    loader = (result.out_dir / "tour" / "tour.js").read_text(encoding="utf-8")
    assert "YoriqnomaTour" in loader and "customer.register" in loader
    steps_flow = "customer.register"
    gif = result.out_dir / "gif" / f"{steps_flow}.gif"
    manual = load_json(run / "manual.json", Manual)
    article = next(a for s in manual.sections for a in s.articles if a.flow_id == steps_flow)
    with Image.open(gif) as img:
        frames = int(getattr(img, "n_frames", 1))
        assert frames == sum(1 for st in article.steps if st.image) and img.width == 960
    assert "pdf" not in result.files  # only what was asked


def test_changelog_against_previous_run(tmp_path: Path) -> None:
    old = make_run(tmp_path / "a")
    asyncio.run(write_manual(old, FakeProvider()))
    same = tmp_path / "b" / "run"
    shutil.copytree(old, same)
    assert compare(old, same).empty

    new = tmp_path / "c" / "run"
    shutil.copytree(old, new)
    cap = load_json(new / "capture" / "capture.json", CaptureRun)
    extra = Element(
        marker=3,
        role="link",
        name="Parolni unutdingizmi?",
        bbox=cap.states[0].elements[0].bbox,
        selector=Target(role="link", name="Parolni unutdingizmi?"),
        kind="link",
    )
    first: State = cap.states[0]
    cap.states[0] = first.model_copy(update={"elements": [*first.elements, extra]})
    cap.flows.append(FlowResult(flow_id="guest.page.about", status="verified", state_ids=[]))
    save_json(new / "capture" / "capture.json", cap)

    changes = compare(old, new)
    assert changes.changed_screens == ["customer.register"]
    assert changes.added_flows == ["guest.page.about"]
    assert changes.unchanged == 1
    path = write_changelog(old, new)
    assert path is not None
    text = path.read_text(encoding="utf-8")
    assert "Ekrani o'zgargan vazifalar" in text and "Yangi vazifalar" in text
    assert "Ro'yxatdan o'tish" in text


def test_fakes_stay_the_same_within_a_scope() -> None:
    first = DataGen("s", "run-1", T30_KEY)
    update = DataGen("s", "run-2", T30_KEY, scope="run-1")
    other = DataGen("s", "run-3", T30_KEY)

    real = "Dilnoza Karimova"
    assert first.substitute("name", real) == update.substitute("name", real)
    assert first.substitute("name", real) != other.substitute("name", real)
    assert (
        update.identity("customer", "A", "x.test").email
        != first.identity("customer", "A", "x.test").email
    )  # each run still signs up its own fresh test accounts


# --- T21: final review (Claude: Opus) -----------------------------------------------


def test_final_review_applies_only_clean_corrections(tmp_path: Path) -> None:
    from typing import Any

    from yoriqnoma_core.writer.providers import LLMResult
    from yoriqnoma_core.writer.review import Correction, ReviewAnswer

    class ReviewingFake(FakeProvider):
        def capabilities(self) -> set[str]:
            return {"vision", "json_schema", "final_review"}

        def model_for(self, task: str) -> str:
            return "reviewer" if task == "final_review" else self.model

        async def generate(self, req: LLMRequest, schema: Any) -> Any:
            if req.task != "final_review":
                return await super().generate(req, schema)
            fixes = [
                Correction(
                    flow_id="customer.register",
                    field="purpose",
                    text="Saytda yangi hisob ochish uchun.",
                ),
                Correction(flow_id="customer.register", field="note", index=9, text="Ortiqcha."),
                Correction(flow_id="nope", field="purpose", text="Yo'q maqola."),
            ]
            return LLMResult(data=ReviewAnswer(corrections=fixes), model="reviewer")

    run = make_run(tmp_path)
    manual, stats = asyncio.run(write_manual(run, ReviewingFake()))

    register = next(
        a for s in manual.sections for a in s.articles if a.flow_id == "customer.register"
    )
    assert register.purpose == "Saytda yangi hisob ochish uchun."
    assert stats.review_fixes == 1  # the bad note index and the unknown flow are skipped
    assert manual.models[-1] == "reviewer"
    saved = load_json(run / "manual.json", Manual)
    assert saved.sections[0].articles[0].purpose == register.purpose
