"""LLM tasks of the writer (TZ FR-W2, FR-W3): describe flows, statuses, intros, FAQ, reference.

Each task: input -> prompt (versioned Jinja template) -> provider (cached) -> schema ->
checks. A text with a soft problem (a name not on the page) is asked again up to two
times and then kept with ``needs_review``; a text with personal data or an admin mention
is never kept: a template sentence is used instead.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeVar

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from PIL import Image
from pydantic import BaseModel

from yoriqnoma_core.writer.answers import (
    FAQAnswer,
    FlowDescription,
    ReferenceAnswer,
    SectionIntro,
    StatusDescriptions,
)
from yoriqnoma_core.writer.cache import LLMCache, cached_generate
from yoriqnoma_core.writer.providers.base import LLMProvider, LLMRequest, ProviderError
from yoriqnoma_core.writer.validate import check_text

PROMPT_VERSION = "2"
PROMPTS = Path(__file__).parent / "prompts"
A = TypeVar("A", bound=BaseModel)

_env = Environment(
    loader=FileSystemLoader(str(PROMPTS)),
    undefined=StrictUndefined,
    autoescape=False,
    keep_trailing_newline=True,
)


def render_prompt(name: str, **kwargs: Any) -> str:
    return _env.get_template(f"{name}.j2").render(**kwargs)


def texts_of(answer: BaseModel) -> list[str]:
    out: list[str] = []

    def walk(value: Any) -> None:
        if isinstance(value, str):
            out.append(value)
        elif isinstance(value, BaseModel):
            for v in value.__dict__.values():
                walk(v)
        elif isinstance(value, list):
            for v in value:
                walk(v)

    walk(answer)
    return out


@dataclass
class TaskStats:
    calls: int = 0
    cached: int = 0
    retries: int = 0
    needs_review: int = 0
    fallbacks: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    seconds: float = 0.0
    review_fixes: int = 0  # corrections applied by the final review
    errors: list[str] = field(default_factory=list)


class TaskRunner:
    def __init__(
        self,
        provider: LLMProvider,
        cache: LLMCache | None,
        role_label: str,
        ignore: set[str],
        image_dir: Path,
    ) -> None:
        self.provider = provider
        self.cache = cache
        self.role_label = role_label
        self.ignore = ignore
        self.image_dir = image_dir
        self.stats = TaskStats()
        self.system = render_prompt("system", role_label=role_label)
        self.vision = "vision" in provider.capabilities()
        self.before_call: Callable[[str], None] | None = None  # progress / cancel hook

    def llm_image(self, path: Path) -> Path | None:
        """A downscaled copy for the model (faster); the manual uses the full image."""
        if not self.vision or not path.is_file():
            return None
        out = self.image_dir / f"{path.stem}_llm.png"
        if not out.exists():
            self.image_dir.mkdir(parents=True, exist_ok=True)
            with Image.open(path) as opened:
                img: Image.Image = opened.convert("RGB")
            if img.width > 1024:
                img = img.resize((1024, int(img.height * 1024 / img.width)))
            if img.height > 1400:
                img = img.crop((0, 0, img.width, 1400))
            img.save(out)
        return out

    async def ask(
        self,
        task: str,
        prompt: str,
        schema: type[A],
        known: set[str],
        images: Iterable[Path] = (),
        max_tokens: int = 1200,
    ) -> tuple[A | None, bool]:
        """(answer or None, needs_review)."""
        if self.before_call is not None:
            self.before_call(task)
        imgs = [p for p in (self.llm_image(i) for i in images) if p is not None]
        current = prompt
        last: A | None = None
        temperature = 0.0
        for attempt in range(3):
            req = LLMRequest(
                task=task,
                system=self.system,
                prompt=current,
                images=imgs,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            try:
                result = await cached_generate(
                    self.provider, self.cache, req, schema, PROMPT_VERSION
                )
            except ProviderError as exc:
                if "repeat" in str(exc).lower() and attempt < 2:
                    temperature = 0.4  # the model looped: a little randomness breaks the loop
                    self.stats.retries += 1
                    continue
                self.stats.errors.append(f"{task}: {exc}")
                return None, True
            self.stats.calls += 1
            self.stats.cached += int(result.cached)
            self.stats.tokens_in += result.input_tokens
            self.stats.tokens_out += result.output_tokens
            self.stats.seconds += result.latency_s
            soft: list[str] = []
            hard: list[str] = []
            for text in texts_of(result.data):
                s, h = check_text(text, known, self.ignore)
                soft += s
                hard += h
            if not soft and not hard:
                return result.data, False
            last = result.data if not hard else last
            self.stats.retries += 1
            current = (
                prompt
                + "\n\nOldingi javobda muammo bor: "
                + "; ".join(sorted(set(hard + soft))[:5])
                + ". Tuzatib, qaytadan yozing. Faqat ro'yxatdagi nomlarni «...» ichida yozing."
            )
            if attempt == 2:
                break
        if last is not None:
            self.stats.needs_review += 1
            return last, True
        self.stats.fallbacks += 1
        return None, True

    async def describe_flow(self, **kw: Any) -> tuple[FlowDescription | None, bool]:
        images = kw.pop("images", [])
        known = kw.pop("known")
        return await self.ask(
            "describe_flow", render_prompt("describe_flow", **kw), FlowDescription, known, images
        )

    async def describe_statuses(self, **kw: Any) -> tuple[StatusDescriptions | None, bool]:
        known = kw.pop("known")
        images = kw.pop("images", [])
        return await self.ask(
            "describe_statuses",
            render_prompt("describe_statuses", role_label=self.role_label, **kw),
            StatusDescriptions,
            known,
            images,
        )

    async def section_intro(self, **kw: Any) -> tuple[SectionIntro | None, bool]:
        known = kw.pop("known")
        return await self.ask(
            "section_intro",
            render_prompt("section_intro", **kw),
            SectionIntro,
            known,
            max_tokens=400,
        )

    async def faq(self, **kw: Any) -> tuple[FAQAnswer | None, bool]:
        known = kw.pop("known")
        return await self.ask(
            "faq",
            render_prompt("faq", role_label=self.role_label, **kw),
            FAQAnswer,
            known,
            max_tokens=1500,
        )

    async def reference(self, **kw: Any) -> tuple[ReferenceAnswer | None, bool]:
        known = kw.pop("known")
        return await self.ask(
            "reference",
            render_prompt("reference", role_label=self.role_label, **kw),
            ReferenceAnswer,
            known,
            max_tokens=2000,
        )
