"""Assemble manual.json (TZ FR-W4, FR-W5): 9 sections, verified flows only.

Every section is always present; a section without flows gets a template sentence
(no LLM call) and its reason in coverage. Failed flows go to the "Tekshirilmagan" annex.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from urllib.parse import urlsplit

from yoriqnoma_core.explorer.session import path_template
from yoriqnoma_core.text_uz import normalize_uz
from yoriqnoma_core.writer import templates_uz as tpl
from yoriqnoma_core.writer.coverage import compute
from yoriqnoma_core.writer.tasks import TaskRunner
from yoriqnoma_core.writer.validate import known_set
from yoriqnoma_schemas import (
    QA,
    Article,
    Blueprint,
    CaptureRun,
    Flow,
    FlowResult,
    Manual,
    RefEntry,
    Section,
    Stage,
    State,
    StatusRow,
    Step,
    StepText,
)

SECTIONS: list[tuple[str, str]] = [
    ("start", "1. Boshlash"),
    ("core", "2. Asosiy ishlar"),
    ("manage", "3. O'z ma'lumotlarini boshqarish"),
    ("social", "4. Boshqa foydalanuvchilar bilan"),
    ("payment", "5. To'lovlar"),
    ("settings", "6. Sozlamalar va xavfsizlik"),
    ("exit", "7. Hisobni o'chirish"),
    ("reference", "8. Imkoniyatlar ma'lumotnomasi (A–Z)"),
    ("faq", "9. Xatolar va savollar (FAQ)"),
]
NAV_ROLES = {"link"}
H1 = re.compile(r'heading "((?:[^"\\]|\\.)*)"\s*\[level=1\]')
RECORD_TAIL = re.compile(r"\s*#\d+.*$")
CONTACT = re.compile(r"@|\d[\d\s()+-]{6,}")  # an e-mail or a phone number is not a menu item


def page_heading(state: State | None) -> str | None:
    """The page's own <h1> from the aria snapshot, without a record number («Buyurtma #4 Yangi»)."""
    if state is None:
        return None
    match = H1.search(state.aria)
    if match is None:
        return None
    text = RECORD_TAIL.sub("", match.group(1).replace('\\"', '"')).strip()
    return text or None


def useful_rules(rules: str | None) -> str:
    """Rules worth telling a person: drop trivial ones (min:0, min:1) and long email regexes."""
    keep = []
    for rule in (rules or "").split("|"):
        key, _, value = rule.partition(":")
        if not key or (key == "min" and value in {"0", "1"}):
            continue
        if key == "regex" and "@" in value:
            continue
        keep.append(rule)
    return "|".join(keep)


def element_marker(state: State | None, step: Step) -> int | None:
    if state is None or step.target is None:
        return None
    t = step.target
    wanted = [normalize_uz(x) for x in (t.label, t.name) if x]
    if not wanted:
        return None
    for el in state.elements:
        name = normalize_uz(el.name)
        if name in wanted and (t.role is None or el.role == t.role or t.label):
            return el.marker
    for el in state.elements:
        name = normalize_uz(el.name)
        if any(w and (w in name or name in w) for w in wanted if len(w) >= 3):
            return el.marker
    return None


class ManualBuilder:
    def __init__(
        self,
        bp: Blueprint,
        capture: CaptureRun,
        tasks: TaskRunner,
        capture_dir: Path,
        source_mode: str = "local",
    ) -> None:
        self.bp = bp
        self.capture = capture
        self.tasks = tasks
        self.capture_dir = capture_dir
        self.source_mode = source_mode
        self.role = capture.role
        info = bp.role(self.role)
        self.role_label = info.label if info else self.role
        self.self_signup = bool(info and info.self_signup)
        self.states = {s.id: s for s in capture.states}
        self.nav = {n.get("path", ""): n.get("label", "") for n in bp.nav}
        self.notes: list[str] = []
        self.titles: dict[str, str] = {}
        for state in capture.states:
            if state.patched or state.account == "B":
                continue
            path = path_template(urlsplit(state.url).path)
            if ":" not in path and path not in self.titles:
                heading = page_heading(state)
                if heading:
                    self.titles[path] = heading

    # --- helpers ------------------------------------------------------------------

    def _known(self, states: list[State]) -> set[str]:
        names: list[str] = []
        for s in states:
            names += [el.name for el in s.elements]
        names += list(self.nav.values()) + list(self.bp.i18n.values())
        names += [st.label or st.value for e in self.bp.entities for st in e.statuses]
        names += [self.role_label, self.bp.project]
        return known_set(names)

    def _image(self, state: State | None, kind: str = "clean") -> str | None:
        return state.images.get(kind) if state else None  # type: ignore[call-overload]

    def page_title(self, path: str, state: State | None) -> str:
        """A readable page name: the menu label, else the page's <h1>, else the path.

        A page of one record (``/orders/:id``) is named after its list page, because its own
        heading carries the record's data («Choynak», «Buyurtma #4»).
        """
        label = self.nav.get(path)
        if label:
            return label
        if ":" in path:
            parent = path.rsplit("/", 1)[0] or "/"
            parent_label = self.nav.get(parent) or self.titles.get(parent)
            if parent_label:
                return f"{parent_label} — tafsilot"
        heading = page_heading(state)
        if heading:
            return heading
        if state is not None and state.title and state.title != self.bp.project:
            return state.title
        return path

    def _state_for_step(self, states: list[State], index: int) -> State | None:
        exact = [s for s in states if s.step_index == index]
        if exact:
            return exact[0]
        before = [s for s in states if s.step_index is not None and s.step_index <= index]
        return before[-1] if before else (states[0] if states else None)

    def step_texts(self, flow: Flow, states: list[State]) -> list[StepText]:
        out: list[StepText] = []
        used_images: set[str] = set()
        for i, step in enumerate(flow.steps):
            state = self._state_for_step(states, i if step.action != "goto" else i + 1)
            marker = element_marker(state, step) if step.action != "goto" else None
            label = None
            if step.action == "goto":
                goto_path = step.path or ""
                label = self.nav.get(goto_path) or (
                    None
                    if "{own:" in goto_path or ":" in goto_path
                    else self.titles.get(path_template(goto_path))
                )
            text = tpl.step_sentence(step, marker, label)
            if text is None:
                continue
            image = self._image(state)
            if image and (marker or image not in used_images):
                used_images.add(image)
            else:
                image = None
            out.append(
                StepText(
                    n=len(out) + 1,
                    text=text,
                    image=image,
                    markers=[marker] if marker else [],
                    state_id=state.id if state else None,
                )
            )
        final = next((s for s in states if s.step_index == len(flow.steps)), None)
        if final is not None and len(flow.steps) > 1 and self._image(final) not in used_images:
            out.append(
                StepText(
                    n=len(out) + 1,
                    text="Natija rasmda ko'rsatilgan.",
                    image=self._image(final),
                    state_id=final.id,
                )
            )
        if not out and states:
            out.append(
                StepText(
                    n=1,
                    text="Sahifa rasmda ko'rsatilgan.",
                    image=self._image(states[-1]),
                    state_id=states[-1].id,
                )
            )
        return out

    # --- articles -----------------------------------------------------------------

    async def article(self, flow: Flow, result: FlowResult) -> Article:
        states = [self.states[s] for s in result.state_ids if s in self.states]
        steps = self.step_texts(flow, states)
        main = next((s for s in states if s.elements), states[0] if states else None)
        elements = [
            {"marker": el.marker, "role": el.role, "name": el.name}
            for el in (main.elements if main else [])[:40]
        ]
        rules = sorted(
            {
                f"«{s.target.label or s.target.name}»: {useful_rules(s.rules)}"
                for s in flow.steps
                if s.target is not None and useful_rules(s.rules)
            }
        )
        som = self.capture_dir / main.images["som"] if main else None
        answer, review = await self.tasks.describe_flow(
            title=flow.title,
            project=self.bp.project,
            url=urlsplit(main.url).path if main else "",
            steps=[st.text for st in steps],
            elements=elements,
            rules=rules,
            images=[som] if som else [],
            known=self._known(states),
        )
        purpose = answer.purpose if answer else f"Bu bo'limda «{flow.title}» vazifasi ko'rsatilgan."
        notes = list(answer.notes) if answer else []
        if result.stopped_at_confirm:
            notes.append(tpl.STOPPED_NOTE)
        return Article(
            flow_id=flow.id,
            title=flow.title,
            purpose=purpose,
            steps=steps,
            notes=notes,
            needs_review=review,
        )

    async def status_rows(self, entity_name: str) -> list[StatusRow]:
        entity = self.bp.entity(entity_name)
        if entity is None or not entity.statuses:
            return []
        seen = {
            s.entity_status: s
            for s in self.capture.states
            if s.entity == entity_name and s.entity_status
        }
        statuses = [
            {"value": st.value, "label": st.label or st.value, "own": self.role in st.reachable_by}
            for st in entity.statuses
        ]
        images = [self.capture_dir / s.images["som"] for s in seen.values()][:3]
        noun = entity_name
        answer, _ = await self.tasks.describe_statuses(
            entity_label=noun,
            statuses=statuses,
            images=images,
            known=self._known(list(seen.values())),
        )
        answer_rows = answer.rows if answer else []
        by_label = {normalize_uz(r.status.strip("«»")): r for r in answer_rows}
        same_order = len(answer_rows) == len(entity.statuses)
        rows: list[StatusRow] = []
        for index, st in enumerate(entity.statuses):
            label = st.label or st.value
            row = by_label.get(normalize_uz(label)) or by_label.get(normalize_uz(st.value))
            if row is None and same_order:
                row = answer_rows[index]
            state = seen.get(st.value)
            rows.append(
                StatusRow(
                    status=label,
                    meaning=row.meaning if row else f"Obyekt «{label}» holatida.",
                    what_you_can_do=row.what_you_can_do if row else "—",
                    patched_image=bool(state and state.patched),
                    image=self._image(state),
                )
            )
        return rows

    # --- the whole manual ---------------------------------------------------------

    async def build(self, models: list[str]) -> Manual:
        results = {r.flow_id: r for r in self.capture.flows if not r.helper}
        flows = [f for f in self.bp.topo_order() if f.id in results]
        verified = [f for f in flows if results[f.id].status == "verified"]
        failed = [f for f in flows if results[f.id].status != "verified"]
        sections: list[Section] = []
        status_done: set[str] = set()
        for stage_name, title in SECTIONS[:7]:
            stage = cast(Stage, stage_name)
            articles: list[Article] = []
            for flow in [f for f in verified if f.stage == stage]:
                article = await self.article(flow, results[flow.id])
                if flow.entity and flow.action == "view" and flow.entity not in status_done:
                    article.statuses = await self.status_rows(flow.entity)
                    status_done.add(flow.entity)
                articles.append(article)
            if stage == "manage":
                for entity in self.bp.entities:
                    has_states = any(
                        s.entity == entity.name and s.entity_status for s in self.capture.states
                    )
                    if entity.statuses and entity.name not in status_done and has_states:
                        rows = await self.status_rows(entity.name)
                        articles.append(
                            Article(
                                flow_id=f"{entity.name}.statuses",
                                title=f"«{entity.name}» statuslari",
                                purpose="Obyekt qaysi holatda ekanini bilish.",
                                statuses=rows,
                            )
                        )
                        status_done.add(entity.name)
            intro, empty = await self._intro(stage, title, articles)
            sections.append(
                Section(
                    id=stage,
                    stage=stage,
                    title=title,
                    intro=intro,
                    articles=articles,
                    empty_reason=empty,
                )
            )
        reference, common = await self._reference()
        reference_intro = "Rolingiz ko'radigan sahifalar va ulardagi asosiy elementlar."
        if common:
            reference_intro += (
                " Har sahifada bor menyu va tugmalar: " + ", ".join(f"«{n}»" for n in common) + "."
            )
        sections.append(
            Section(
                id="reference",
                stage="reference",
                title=SECTIONS[7][1],
                intro=reference_intro,
                articles=[],
            )
        )
        faq = await self._faq(failed, results)
        sections.append(
            Section(
                id="faq",
                stage="faq",
                title=SECTIONS[8][1],
                intro="Ko'p uchraydigan xatolar va savollarga javoblar.",
                articles=[],
            )
        )
        if failed:
            sections.append(
                Section(
                    id="unverified",
                    stage="unverified",
                    title="Ilova: Tekshirilmagan vazifalar",
                    intro=tpl.UNVERIFIED_INTRO,
                    articles=[
                        Article(
                            flow_id=f.id,
                            title=f.title,
                            purpose=results[f.id].reason or "sabab yozilmagan",
                        )
                        for f in failed
                    ],
                )
            )
        manual = Manual(
            project=self.bp.project,
            language=self.bp.language,
            role=self.role,
            role_label=self.role_label,
            role_granted_by=(
                "Bu rolni saytda ro'yxatdan o'tib o'zingiz olasiz."
                if self.self_signup
                else "Bu rolni sayt administratori beradi."
            ),
            generated_at=datetime.now(UTC),
            source_mode=self.source_mode,  # type: ignore[arg-type]
            models=models,
            sections=sections,
            reference=reference,
            faq=faq,
        )
        manual.coverage = compute(self.bp, self.capture, manual)
        return manual

    async def _intro(
        self, stage: str, title: str, articles: list[Article]
    ) -> tuple[str, str | None]:
        if not articles:
            return tpl.EMPTY_SECTION, "bu rol uchun bunday flow topilmadi"
        prefix = tpl.role_intro(self.role_label, self.self_signup) + " " if stage == "start" else ""
        answer, _ = await self.tasks.section_intro(
            title=title, articles=[a.title for a in articles], known=self._known([])
        )
        text = (
            answer.intro if answer else f"Bu bo'limda: {', '.join(a.title for a in articles[:4])}."
        )
        return prefix + text, None

    async def _reference(self) -> tuple[list[RefEntry], list[str]]:
        """(entries, names on every page). The menu that repeats on each page is listed once."""
        pages: dict[str, State] = {}
        for state in self.capture.states:
            if state.patched or state.account == "B":
                continue
            tpl_path = path_template(urlsplit(state.url).path)
            pages.setdefault(tpl_path, state)
        counts: dict[str, int] = {}
        for state in pages.values():
            for name in {el.name for el in state.elements if el.name}:
                counts[name] = counts.get(name, 0) + 1
        threshold = max(3, (len(pages) + 1) // 2)
        common = sorted(
            (
                n
                for n, c in counts.items()
                if c >= threshold and len(pages) >= 4 and not CONTACT.search(n)
            ),
            key=lambda n: -counts[n],
        )[:12]
        entries = [
            RefEntry(
                page_title=self.page_title(path, s),
                path=path,
                purpose="—",
                elements=[el.name for el in s.elements if el.name and el.name not in common][:12],
            )
            for path, s in sorted(pages.items())
        ]
        answer, _ = await self.tasks.reference(
            pages=[
                {"path": e.path, "title": e.page_title, "elements": e.elements} for e in entries
            ],
            known=self._known(list(pages.values())),
        )
        purposes = {p.path: p.purpose for p in (answer.pages if answer else [])}
        for entry in entries:
            entry.purpose = purposes.get(entry.path, "—")
        return sorted(entries, key=lambda e: normalize_uz(e.page_title)), common

    async def _faq(self, failed: list[Flow], results: dict[str, FlowResult]) -> list[QA]:
        forms = []
        for form in self.bp.forms:
            rules = [
                f"«{f.label or f.name}»: {useful_rules(f.rules)}"
                for f in form.fields
                if useful_rules(f.rules)
            ]
            if rules:
                forms.append({"title": form.submit.name or form.id, "rules": rules})
        problems = [f"{f.title}: {results[f.id].reason}" for f in failed][:5]
        answer, _ = await self.tasks.faq(
            forms=forms[:12], problems=problems, known=self._known(list(self.states.values())[:30])
        )
        return [QA(q=i.q, a=i.a) for i in (answer.items if answer else [])]
