"""Полная очистка Steam-аккаунтов с предварительным бэкапом.

1. Сохраняет все аккаунты в backups/accounts_<дата>.txt (формат массовой загрузки).
2. Удаляет все записи steam_accounts (история выдач остаётся, ссылки обнуляются).
3. Возвращает пользователям права: free_claim_used=false, extra_claims_used=0.

Запуск: DATABASE_URL=... python scripts/wipe_accounts.py
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from bot.database.models import SteamAccount, User  # noqa: E402


async def main() -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    sm = async_sessionmaker(engine, expire_on_commit=False)

    backup_dir = Path(__file__).resolve().parent.parent / "backups"
    backup_dir.mkdir(exist_ok=True)
    backup_file = backup_dir / f"accounts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"

    async with sm() as s:
        accounts = (await s.execute(select(SteamAccount).order_by(SteamAccount.id))).scalars().all()

        with open(backup_file, "w", encoding="utf-8") as f:
            for a in accounts:
                games = ", ".join(a.games_list)
                line = f"{a.login}:{a.password}"
                if games:
                    line += f" | {games}"
                f.write(line + "\n")
        print(f"Бэкап: {backup_file} ({len(accounts)} аккаунтов)")

        res = await s.execute(text("DELETE FROM steam_accounts"))
        print("Удалено аккаунтов:", res.rowcount)

        users = (await s.execute(select(User))).scalars().all()
        for u in users:
            u.free_claim_used = False
            u.extra_claims_used = 0
        await s.commit()
        print(f"Права возвращены {len(users)} пользователям (free + promo остатки).")

        total = (await s.execute(text("SELECT COUNT(*) FROM steam_accounts"))).scalar_one()
        hist = (await s.execute(text("SELECT COUNT(*) FROM issue_history"))).scalar_one()
        print(f"steam_accounts теперь: {total} | issue_history сохранена: {hist}")

    await engine.dispose()


asyncio.run(main())
