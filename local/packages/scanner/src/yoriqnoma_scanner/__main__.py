"""Debug entry: ``python -m yoriqnoma_scanner PATH --base-url URL [--out FILE] [--report FILE]``."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from yoriqnoma_scanner.api import UnsupportedStack, scan
from yoriqnoma_schemas import save_json


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m yoriqnoma_scanner")
    parser.add_argument("path", type=Path)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--out", type=Path, help="blueprint.json yo'li")
    parser.add_argument("--report", type=Path, help="scan_report.md yo'li")
    parser.add_argument("--stack", default="auto")
    args = parser.parse_args(argv)
    try:
        result = scan(args.path, args.base_url, stack=args.stack)
    except (UnsupportedStack, NotADirectoryError) as exc:
        print(f"Xato: {exc}", file=sys.stderr)
        return 2
    print(f"Stek: {', '.join(result.stacks)}")
    for key, value in result.stats.items():
        print(f"  {key}: {value}")
    for role in result.blueprint.roles:
        print(f"  rol {role.id:12} {role.kind:9} {role.reason}")
    if args.out:
        save_json(args.out, result.blueprint)
        print(f"blueprint: {args.out}")
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(result.report_md, encoding="utf-8")
        print(f"hisobot: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
