"""FastAPI app: /api plus the built React app (SPA fallback). ``uv run demo-shop``."""

from __future__ import annotations

import argparse
import os
from collections.abc import Sequence
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from demo_shop import config
from demo_shop.api import api_router
from demo_shop.db import Base, engine, new_session, reset_engine
from demo_shop.seed import seed

NO_BUILD = (
    "<!doctype html><meta charset=utf-8><title>Demo Shop</title>"
    "<p>web/dist topilmadi: <code>cd web && npm install && npm run build</code></p>"
)


def init_db(reset: bool = False) -> None:
    path = config.db_path()
    if reset:
        reset_engine()
        path.unlink(missing_ok=True)
        for folder in (config.mail_dir(), config.uploads_dir()):
            for item in folder.iterdir():
                item.unlink()
    fresh = not path.exists()
    Base.metadata.create_all(engine())
    if fresh:
        with new_session() as db:
            seed(db)


def create_app() -> FastAPI:
    app = FastAPI(title="Demo Shop", docs_url=None, redoc_url=None, openapi_url=None)
    app.include_router(api_router)
    assets = config.WEB_DIST / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False, response_model=None)
    def spa(full_path: str) -> FileResponse | HTMLResponse:
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Topilmadi")
        candidate = (config.WEB_DIST / full_path).resolve()
        if full_path and candidate.is_file() and candidate.is_relative_to(config.WEB_DIST):
            return FileResponse(candidate)
        index = config.WEB_DIST / "index.html"
        if index.is_file():
            return FileResponse(index)
        return HTMLResponse(NO_BUILD)

    return app


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="demo-shop", description="Demo Shop test site")
    parser.add_argument("--port", type=int, default=8800)
    parser.add_argument("--reset", action="store_true", help="delete and re-seed the database")
    parser.add_argument("--var-dir", type=Path, default=None)
    # 0.0.0.0 only inside the server's e2e test container (docker compose --profile test)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args(argv)
    if args.var_dir:
        os.environ["DEMO_SHOP_VAR"] = str(args.var_dir)
    init_db(reset=args.reset)

    import uvicorn

    print(f"Demo Shop: http://{args.host}:{args.port}/  (pochta: {config.mail_dir()})")
    uvicorn.run(create_app(), host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
