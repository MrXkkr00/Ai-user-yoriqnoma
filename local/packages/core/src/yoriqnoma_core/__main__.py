"""Debug CLI: ``python -m yoriqnoma_core run --blueprint B --base-url URL --role R --out DIR``.

The provider is ``fake`` (no model) or ``ollama`` (local model, default gemma4:26b).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import secrets
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

from pydantic import SecretBytes, SecretStr

from yoriqnoma_core.pipeline import (
    AccountCredentials,
    ConsoleProgressSink,
    ExploreOptions,
    NeverCancel,
    TerminalHumanInput,
    run_explore,
    run_render,
    run_write,
)
from yoriqnoma_core.writer.providers import FakeProvider, OllamaProvider
from yoriqnoma_core.writer.providers.base import LLMProvider
from yoriqnoma_schemas import Blueprint, load_json


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m yoriqnoma_core")
    sub = parser.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="explore -> write -> render")
    run.add_argument("--blueprint", type=Path, required=True)
    run.add_argument("--base-url", required=True)
    run.add_argument("--role", required=True)
    run.add_argument("--out", type=Path, required=True)
    run.add_argument("--provider", choices=["fake", "ollama"], default="fake")
    run.add_argument("--model", default="gemma4:26b")
    run.add_argument("--ollama-host", default="http://127.0.0.1:11434")
    run.add_argument("--accounts", type=Path, help="JSON: {role: {A: {login, password}}}")
    run.add_argument("--mailbox", default="", help="folder of .eml files, or Mailpit URL")
    run.add_argument("--formats", default="html,pdf,docx")
    run.add_argument("--allow-private", action="store_true", help="site on 127.0.0.1 (local)")
    run.add_argument("--headed", action="store_true")
    args = parser.parse_args(argv)

    bp = load_json(args.blueprint, Blueprint)
    accounts: dict[str, dict[str, AccountCredentials]] = {}
    if args.accounts:
        raw = json.loads(args.accounts.read_text(encoding="utf-8"))
        for role, aliases in raw.items():
            accounts[role] = {
                alias: AccountCredentials(login=v["login"], password=SecretStr(v["password"]))
                for alias, v in aliases.items()
            }
    mailbox_kind: Literal["mailpit", "dir"] = (
        "mailpit" if args.mailbox.startswith("http") else "dir"
    )
    opts = ExploreOptions(
        base_url=args.base_url,
        role=args.role,
        accounts=accounts,
        mailbox_kind=mailbox_kind,
        mailbox_target=args.mailbox,
        allow_private=args.allow_private,
        headless=not args.headed,
        pseudonym_key=SecretBytes(secrets.token_bytes(32)),
        run_id=args.out.name,
    )
    provider: LLMProvider = (
        FakeProvider()
        if args.provider == "fake"
        else OllamaProvider(host=args.ollama_host, model=args.model)
    )
    progress = ConsoleProgressSink()
    cancel = NeverCancel()
    capture = asyncio.run(run_explore(bp, args.out, opts, TerminalHumanInput(), progress, cancel))
    print(f"capture: {len(capture.states)} holat, {len(capture.flows)} flow")
    manual = asyncio.run(
        run_write(
            args.out, provider, progress, cancel, cache_dir=args.out.parent / ".cache" / "llm"
        )
    )
    print(
        f"manual: {sum(len(s.articles) for s in manual.sections)} maqola, "
        f"qamrov {manual.coverage.percent.get('total', 0)}%"
    )
    result = run_render(args.out, set(args.formats.split(",")))
    for kind, path in result.files.items():
        print(f"{kind}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
