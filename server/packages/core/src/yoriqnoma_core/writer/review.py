"""Final review (TZ FR-SV6, T21): a strong model reads the whole manual and fixes it.

Only for providers that offer ``final_review`` (Claude: Opus). The model sees the manual's
LLM-written texts (purposes and notes; step sentences come from templates and stay) and one
picture per section, and answers with corrections. A correction is applied only when the
article exists and the new text passes the writer's checks (names on the page, no
personal data, no admin), so a review can only make the manual cleaner.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import Field

from yoriqnoma_core.writer.answers import _Answer
from yoriqnoma_core.writer.tasks import TaskRunner, render_prompt
from yoriqnoma_core.writer.validate import check_text
from yoriqnoma_schemas import Manual


class Correction(_Answer):
    flow_id: str
    field: Literal["purpose", "note"]
    index: int = Field(default=0, description="eslatma tartib raqami (0 dan), purpose uchun 0")
    text: str = Field(description="tuzatilgan to'liq matn")
    reason: str = ""


class ReviewAnswer(_Answer):
    corrections: list[Correction] = Field(default_factory=list)


def manual_digest(manual: Manual) -> str:
    """The manual as compact JSON: what the reviewer needs, nothing else."""
    sections = []
    for s in manual.sections:
        sections.append(
            {
                "section": s.title,
                "articles": [
                    {
                        "flow_id": a.flow_id,
                        "title": a.title,
                        "purpose": a.purpose,
                        "steps": [st.text for st in a.steps],
                        "notes": a.notes,
                    }
                    for a in s.articles
                ],
            }
        )
    return json.dumps(sections, ensure_ascii=False, indent=1)


def review_images(manual: Manual, capture_dir: Path, limit: int = 8) -> list[Path]:
    """One picture per section with articles (the first step that has one)."""
    out: list[Path] = []
    for s in manual.sections:
        image = next((st.image for a in s.articles for st in a.steps if st.image), None)
        if image and (capture_dir / image).is_file():
            out.append(capture_dir / image)
        if len(out) >= limit:
            break
    return out


async def final_review(
    manual: Manual, tasks: TaskRunner, capture_dir: Path, known: set[str]
) -> int:
    """Apply the reviewer's corrections in place; return how many were applied."""
    articles = {a.flow_id: a for s in manual.sections for a in s.articles}
    if not articles:
        return 0
    prompt = render_prompt(
        "final_review", role_label=tasks.role_label, digest=manual_digest(manual)
    )
    answer, _review = await tasks.ask(
        "final_review",
        prompt,
        ReviewAnswer,
        known,
        review_images(manual, capture_dir),
        max_tokens=4000,
    )
    if answer is None:
        return 0
    applied = 0
    for fix in answer.corrections:
        article = articles.get(fix.flow_id)
        text = fix.text.strip()
        if article is None or not text:
            continue
        soft, hard = check_text(text, known, tasks.ignore)
        if soft or hard:
            continue
        if fix.field == "purpose":
            article.purpose = text
        elif 0 <= fix.index < len(article.notes):
            article.notes[fix.index] = text
        else:
            continue
        applied += 1
    return applied
