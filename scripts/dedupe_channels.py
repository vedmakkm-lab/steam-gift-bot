"""Разовая чистка: удалить дубли каналов (тот же chat_id), оставить первый."""
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402


async def main() -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    async with engine.begin() as conn:
        rows = (
            await conn.execute(text("SELECT id, chat_id, username FROM channels ORDER BY id"))
        ).all()
        print("before:", [tuple(r) for r in rows])
        seen: set = set()
        removed = 0
        for r in rows:
            key = r.chat_id or (r.username or "").lower()
            if key in seen:
                await conn.execute(text("DELETE FROM channels WHERE id = :i"), {"i": r.id})
                removed += 1
            else:
                seen.add(key)
        print("removed duplicates:", removed)
        rows = (
            await conn.execute(text("SELECT id, title, chat_id, is_active FROM channels ORDER BY id"))
        ).all()
        print("after:", [tuple(r) for r in rows])
    await engine.dispose()


asyncio.run(main())
