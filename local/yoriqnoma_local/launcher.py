"""``yoriqnoma-local`` entry point.

For now it applies migrations and starts Django's development server on 127.0.0.1.
T18 replaces runserver with waitress and starts the Huey consumer next to it.
"""

from __future__ import annotations

import argparse
import os
import threading
import webbrowser
from collections.abc import Sequence

# Never 0.0.0.0: the local app reads local folders and must not be reachable from
# the network (CLAUDE.md rule 9). Only the port is configurable.
HOST = "127.0.0.1"
DEFAULT_PORT = 8765


def _port_from_env() -> int:
    raw = os.environ.get("YORIQNOMA_LOCAL_PORT", str(DEFAULT_PORT))
    try:
        port = int(raw)
    except ValueError:
        port = 0
    if not 1 <= port <= 65535:
        raise SystemExit(
            f"YORIQNOMA_LOCAL_PORT noto'g'ri: {raw!r}. 1 dan 65535 gacha son bo'lishi kerak."
        )
    return port


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="yoriqnoma-local",
        description="AI user yo'riqnoma - lokal dastur (faqat 127.0.0.1).",
    )
    parser.add_argument(
        "--dev", action="store_true", help="DEBUG rejimi (faqat ishlab chiqish uchun)"
    )
    parser.add_argument("--no-browser", action="store_true", help="brauzerni avtomatik ochmaslik")
    args = parser.parse_args(argv)
    port = _port_from_env()

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "yoriqnoma_local.settings")
    if args.dev:
        os.environ["YORIQNOMA_DEBUG"] = "1"

    import django
    from django.core import management

    django.setup()
    management.call_command("migrate", interactive=False, verbosity=0)

    url = f"http://{HOST}:{port}/"
    if not args.no_browser:
        timer = threading.Timer(1.5, webbrowser.open, args=(url,))
        timer.daemon = True
        timer.start()
    print(f"Yo'riqnoma lokal dasturi: {url}  (to'xtatish: Ctrl+C)")
    # --insecure lets runserver serve static files when DEBUG is off.
    management.execute_from_command_line(
        ["yoriqnoma-local", "runserver", f"{HOST}:{port}", "--noreload", "--insecure"]
    )
