"""Фабрики async-движка и фабрики сессий SQLAlchemy."""
from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)

logger = logging.getLogger(__name__)


def _tune_sqlite(engine: AsyncEngine) -> None:
    @event.listens_for(engine.sync_engine, "connect")
    def _set_pragma(dbapi_conn, _record):  # noqa: ANN001
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()


def build_engine(database_url: str) -> AsyncEngine:
    if database_url.startswith("sqlite"):
        # Относительный путь — от корня проекта; создаём папку при необходимости.
        path_part = database_url.split("///", 1)[-1]
        if path_part and not path_part.startswith(("/", "C:", "D:")):
            parent = Path(path_part).parent
            if str(parent) not in ("", "."):
                parent.mkdir(parents=True, exist_ok=True)
        engine = create_async_engine(database_url, connect_args={"timeout": 30})
        _tune_sqlite(engine)
    else:
        engine = create_async_engine(
            database_url,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
        )
    logger.info("База данных: %s", database_url.split("://")[0])
    return engine


def build_sessionmaker(engine: AsyncEngine) -> async_sessionmaker:
    return async_sessionmaker(engine, expire_on_commit=False)
