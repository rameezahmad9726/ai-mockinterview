"""
SQLAlchemy engine and session factory for the HR automation layer.

Defaults to a local SQLite file at `backend/interveux.db`. Swap to Postgres by
setting DATABASE_URL (e.g. `postgresql+psycopg://user:pass@host:5432/interveux`).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from dotenv import load_dotenv

_backend_dir = Path(__file__).resolve().parent
load_dotenv(_backend_dir / ".env", override=False)

DEFAULT_SQLITE_PATH = _backend_dir / "interveux.db"
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"sqlite:///{DEFAULT_SQLITE_PATH.as_posix()}",
)

# SQLite needs a special connect arg to work across threads (FastAPI uses threads).
_is_sqlite = DATABASE_URL.startswith("sqlite")
_connect_args = {"check_same_thread": False} if _is_sqlite else {}

engine = create_engine(
    DATABASE_URL,
    connect_args=_connect_args,
    pool_pre_ping=True,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a scoped DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all tables. Safe to call repeatedly; idempotent."""
    # Import models here so SQLAlchemy registers them before create_all().
    import models  # noqa: F401 (registers mappers)

    Base.metadata.create_all(bind=engine)
