"""Export JSON Schemas: ``python -m yoriqnoma_schemas.export [--out DIR]``.

Writes ``blueprint.schema.json``, ``capture.schema.json`` and ``manual.schema.json``.
Without ``--out`` the files go to ``docs/schemas`` of the repository that contains the
current directory.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel

from yoriqnoma_schemas.blueprint import Blueprint
from yoriqnoma_schemas.capture import CaptureRun
from yoriqnoma_schemas.manual import Manual

MODELS: dict[str, type[BaseModel]] = {
    "blueprint": Blueprint,
    "capture": CaptureRun,
    "manual": Manual,
}


def default_out_dir(start: Path | None = None) -> Path:
    here = (start or Path.cwd()).resolve()
    for folder in (here, *here.parents):
        if (folder / "docs").is_dir() and (folder / "local").is_dir():
            return folder / "docs" / "schemas"
    raise SystemExit("docs/ papkasi topilmadi: --out bilan papkani ko'rsating")


def export(out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, model in MODELS.items():
        schema = model.model_json_schema()
        path = out_dir / f"{name}.schema.json"
        path.write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        written.append(path)
    return written


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m yoriqnoma_schemas.export")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)
    for path in export(args.out or default_out_dir()):
        print(path)


if __name__ == "__main__":
    main()
