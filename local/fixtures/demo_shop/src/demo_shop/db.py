"""demo_shop's own SQLite database (it is the studied site, not our tool)."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from demo_shop.config import db_path


class Base(DeclarativeBase):
    pass


_engine: Engine | None = None
_factory: sessionmaker[Session] | None = None


def engine() -> Engine:
    global _engine, _factory
    if _engine is None:
        _engine = create_engine(f"sqlite:///{db_path()}", connect_args={"check_same_thread": False})
        _factory = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def reset_engine() -> None:
    global _engine, _factory
    if _engine is not None:
        _engine.dispose()
    _engine, _factory = None, None


def get_db() -> Iterator[Session]:
    engine()
    assert _factory is not None
    db = _factory()
    try:
        yield db
    finally:
        db.close()


def new_session() -> Session:
    engine()
    assert _factory is not None
    return _factory()
