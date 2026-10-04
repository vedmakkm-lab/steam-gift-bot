"""Временная проверка: схема ORM == схема миграции 0001."""
import asyncio
import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import create_async_engine

from bot.database.models import Base

TABLES = [
    "users", "steam_accounts", "issue_history", "promos", "promo_uses",
    "channels", "payments", "ads", "bot_settings",
]


async def create_orm_schema(dirpath: str) -> str:
    engine = create_async_engine(f"sqlite+aiosqlite:///{dirpath}/orm.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()
    return os.path.join(dirpath, "orm.db")


def columns(db: sqlite3.Connection, table: str) -> list:
    return sorted(r[1] for r in db.execute(f"PRAGMA table_info({table})"))


def main() -> None:
    orm_db = asyncio.run(create_orm_schema(tempfile.mkdtemp()))
    mig_db = sys.argv[1]
    con_orm = sqlite3.connect(orm_db)
    con_mig = sqlite3.connect(mig_db)
    ok = True
    for table in TABLES:
        c1, c2 = columns(con_orm, table), columns(con_mig, table)
        if c1 != c2:
            ok = False
            print(f"MISMATCH {table}:\n  ORM: {c1}\n  MIG: {c2}")
    print("SCHEMA_MATCH_OK" if ok else "SCHEMA_MISMATCH")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
