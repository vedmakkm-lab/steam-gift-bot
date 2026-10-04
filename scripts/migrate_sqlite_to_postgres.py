"""Разовая миграция данных из локального SQLite (bot.db) в PostgreSQL (Neon).

Запуск: DATABASE_URL=postgresql+asyncpg://... python scripts/migrate_sqlite_to_postgres.py
Копирует users, steam_accounts, issue_history, promos, promo_uses, channels,
payments, ads, bot_settings и выставляет sequence'ы.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from bot.database.models import (
    Ad,
    Base,
    BotSetting,
    Channel,
    IssueHistory,
    Payment,
    Promo,
    PromoUse,
    SteamAccount,
    User,
)  # noqa: E402

ORDER = [User, SteamAccount, IssueHistory, Promo, PromoUse, Channel, Payment, Ad, BotSetting]
SEQ_TABLES = {
    "users": User,
    "steam_accounts": SteamAccount,
    "issue_history": IssueHistory,
    "promos": Promo,
    "promo_uses": PromoUse,
    "channels": Channel,
    "payments": Payment,
    "ads": Ad,
}


def _good_account(acc: SteamAccount) -> bool:
    """Отсекаем мусорные записи (например, от старой загрузки файла целиком)."""
    if "\n" in (acc.login or "") or "\n" in (acc.password or ""):
        return False
    if len(acc.login or "") > 250 or len(acc.password or "") > 250:
        return False
    if (acc.login or "").strip().lower() in {"логин", "пароль", "игры"}:
        return False
    return True


def _clip(value: str | None, limit: int) -> str | None:
    if value is not None and len(value) > limit:
        return value[:limit]
    return value


async def main() -> None:
    pg_url = os.environ["DATABASE_URL"]
    sqlite_url = "sqlite+aiosqlite:///./bot.db"

    src_engine = create_async_engine(sqlite_url)
    dst_engine = create_async_engine(pg_url)

    src_sm = async_sessionmaker(src_engine, expire_on_commit=False)
    dst_sm = async_sessionmaker(dst_engine, expire_on_commit=False)

    async with dst_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with src_sm() as s, dst_sm() as d:
        moved_account_ids: set[int] = set()
        for model in ORDER:
            rows = (await s.execute(select(model))).scalars().all()
            moved = 0
            skipped = 0
            for row in rows:
                if isinstance(row, SteamAccount) and not _good_account(row):
                    skipped += 1
                    print(
                        f"  ⏭ пропуск мусорного аккаунта #{row.id}: "
                        f"login={ (row.login or '')[:40]!r}"
                    )
                    continue
                if isinstance(row, IssueHistory):
                    row.account_login = _clip(row.account_login, 255)
                    row.username = _clip(row.username, 255)
                    if row.account_id is not None and row.account_id not in moved_account_ids:
                        # Аккаунт удалён/мусорный — как и при обычном удалении,
                        # оставляем историю со снапшотом логина без ссылки.
                        row.account_id = None
                if isinstance(row, SteamAccount):
                    moved_account_ids.add(row.id)
                await d.merge(row)
                moved += 1
            print(f"{model.__tablename__}: перенесено {moved}, пропущено {skipped}")
        await d.commit()

    async with dst_engine.begin() as conn:
        for table, model in SEQ_TABLES.items():
            await conn.execute(
                text(
                    f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                    f"COALESCE((SELECT MAX(id) FROM {table}), 1))"
                )
            )
    print("Sequences обновлены.")

    await src_engine.dispose()
    await dst_engine.dispose()
    print("МИГРАЦИЯ ЗАВЕРШЕНА")


if __name__ == "__main__":
    asyncio.run(main())
