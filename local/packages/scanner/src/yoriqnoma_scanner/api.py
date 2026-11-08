"""``scan(project_dir, base_url, stack="auto") -> ScanResult`` (TZ FR-S1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from yoriqnoma_scanner.build import build_blueprint
from yoriqnoma_scanner.detect import ProjectInfo, detect
from yoriqnoma_scanner.fs_guard import SafeFS, Skipped
from yoriqnoma_scanner.parsers.base import Parser, ParseResult
from yoriqnoma_scanner.parsers.django_routes import DjangoParser
from yoriqnoma_scanner.parsers.e2e import E2EParser
from yoriqnoma_scanner.parsers.fastapi_routes import FastAPIParser
from yoriqnoma_scanner.parsers.flask_routes import FlaskParser
from yoriqnoma_scanner.parsers.i18n import I18nParser
from yoriqnoma_scanner.parsers.jsx_forms import JsxFormsParser
from yoriqnoma_scanner.parsers.pydantic_forms import PydanticFormsParser
from yoriqnoma_scanner.parsers.react_router import ReactRouterParser
from yoriqnoma_scanner.parsers.sqlalchemy_models import SQLAlchemyModelsParser
from yoriqnoma_scanner.report import render_report
from yoriqnoma_schemas import Blueprint

SUPPORTED = {"fastapi", "react", "django", "flask"}


class UnsupportedStack(ValueError):
    pass


@dataclass
class ScanResult:
    blueprint: Blueprint
    report_md: str
    skipped: list[Skipped]
    stats: dict[str, int] = field(default_factory=dict)
    stacks: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def scan(
    project_dir: Path | str,
    base_url: str,
    stack: str = "auto",
    project: str | None = None,
    language: str = "uz",
) -> ScanResult:
    """Read the project through SafeFS only and build its blueprint.

    ``base_url`` comes only from this argument, never from the project's config files.
    """
    fs = SafeFS(Path(project_dir))
    info: ProjectInfo = detect(fs)
    if stack != "auto":
        info.stacks |= set(stack.split(","))
    if not SUPPORTED & info.stacks:
        raise UnsupportedStack(
            "Qo'llab-quvvatlanadigan stek topilmadi (FastAPI, Django, Flask, React). "
            f"Topilgani: {', '.join(sorted(info.stacks)) or 'hech narsa'}"
        )
    parsed = ParseResult()
    i18n = I18nParser(language)
    if i18n.applies(info):
        parsed.merge(i18n.parse(info, fs))
    parsers: list[Parser] = [
        FastAPIParser(),
        DjangoParser(language),
        FlaskParser(language),
        PydanticFormsParser(),
        SQLAlchemyModelsParser(),
        ReactRouterParser(parsed.i18n),
        JsxFormsParser(parsed.i18n),
    ]
    for parser in parsers:
        if parser.applies(info):
            parsed.merge(parser.parse(info, fs))
    e2e = E2EParser().parse(info, fs) if E2EParser().applies(info) else ParseResult()
    parsed.notes += e2e.notes
    name = project or fs.root.name
    out = build_blueprint(parsed, e2e.flows, base_url, name)
    bp = out.blueprint
    report = render_report(bp, sorted(info.stacks), fs.skipped, out.notes, out.unknown_routes)
    stats = {
        "roles": len(bp.roles),
        "selectable_roles": len(bp.selectable_roles()),
        "pages": sum(1 for p in bp.pages if p.kind == "page"),
        "api_routes": sum(1 for p in bp.pages if p.kind == "api"),
        "excluded": len(bp.excluded),
        "forms": len(bp.forms),
        "entities": len(bp.entities),
        "flows": len(bp.flows),
        "skipped": len(fs.skipped),
    }
    return ScanResult(bp, report, list(fs.skipped), stats, sorted(info.stacks), out.notes)
