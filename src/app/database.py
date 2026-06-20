"""SQLAlchemy engine / session / declarative base."""
from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session

from app.config import settings


class Base(DeclarativeBase):
    pass


def _make_engine(url: str):
    # SQLite (used in tests) needs a special connect arg for multithreaded access.
    if url.startswith("sqlite"):
        return create_engine(
            url, connect_args={"check_same_thread": False}, future=True
        )
    return create_engine(url, pool_pre_ping=True, future=True)


engine = _make_engine(settings.sqlalchemy_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency that yields a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
