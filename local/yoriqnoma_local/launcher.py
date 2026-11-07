"""``yoriqnoma-local`` entry point (TZ FR-L1, ARCHITECTURE §6.1).

1. migrate and start-up checks;
2. web server: waitress on 127.0.0.1 only;
3. Huey worker in a separate process (thread workers, works on Windows);
4. opens the browser; Ctrl+C stops both.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import threading
import webbrowser
from collections.abc import Sequence
from pathlib import Path

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


def start_worker() -> subprocess.Popen[bytes]:
    manage = Path(__file__).resolve().parent.parent / "manage.py"
    workers = os.environ.get("YORIQNOMA_HUEY_WORKERS", "2")
    return subprocess.Popen(
        [sys.executable, str(manage), "run_huey", "-w", workers, "-k", "thread"],
        env=os.environ.copy(),
    )


def serve(port: int) -> None:
    from waitress import serve as waitress_serve

    from yoriqnoma_local.wsgi import application

    waitress_serve(application, host=HOST, port=port, threads=8, _quiet=True)


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="yoriqnoma-local",
        description="AI user yo'riqnoma - lokal dastur (faqat 127.0.0.1).",
    )
    parser.add_argument(
        "--dev", action="store_true", help="DEBUG rejimi (faqat ishlab chiqish uchun)"
    )
    parser.add_argument("--no-browser", action="store_true", help="brauzerni avtomatik ochmaslik")
    parser.add_argument(
        "--no-worker", action="store_true", help="Huey worker'ni ishga tushirmaslik"
    )
    args = parser.parse_args(argv)
    port = _port_from_env()

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "yoriqnoma_local.settings")
    if args.dev:
        os.environ["YORIQNOMA_DEBUG"] = "1"

    import django
    from django.core import management

    django.setup()
    management.call_command("migrate", interactive=False, verbosity=0)
    management.call_command("collectstatic", interactive=False, verbosity=0)

    from settings_app.models import AppSettings
    from yoriqnoma_local.health import all_checks

    cfg = AppSettings.load()
    for check in all_checks(cfg.ollama_host, cfg.ollama_model):
        mark = "OK " if check.ok else "!! "
        print(f"{mark}{check.name}: {check.message}" + (f" — {check.fix}" if check.fix else ""))

    worker = None if args.no_worker else start_worker()
    url = f"http://{HOST}:{port}/"
    if not args.no_browser:
        timer = threading.Timer(1.5, webbrowser.open, args=(url,))
        timer.daemon = True
        timer.start()
    print(f"Yo'riqnoma lokal dasturi: {url}  (to'xtatish: Ctrl+C)")
    try:
        serve(port)
    except KeyboardInterrupt:
        pass
    finally:
        if worker is not None:
            worker.terminate()
            try:
                worker.wait(timeout=10)
            except subprocess.TimeoutExpired:
                worker.kill()
