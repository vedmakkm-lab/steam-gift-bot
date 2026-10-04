"""Диагностика: каналы в Neon + тест getChatMember через Telegram API."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, text  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402

from bot.config import get_settings  # noqa: E402


async def main() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    async with engine.begin() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT id, title, chat_id, username, url, is_active FROM channels ORDER BY id"
                )
            )
        ).all()
        print("=== channels in Neon ===")
        for r in rows:
            print(dict(r._mapping))
        cnt = (await conn.execute(text("SELECT COUNT(*) FROM steam_accounts"))).scalar()
        print("steam_accounts:", cnt)
    await engine.dispose()

    # живой тест getChatMember для каждого канала (как делает бот)
    import aiohttp

    tok = settings.bot_token
    async with aiohttp.ClientSession() as s:
        for r in rows:
            chat_id, username, url = r.chat_id, r.username, r.url
            target = chat_id if chat_id else (f"@{username}" if username else None)
            print(f"--- channel #{r.id} {r.title!r} target={target!r} active={r.is_active}")
            if target is None:
                print("    !! нет chat_id и username — target unusable")
                continue
            # бот сам в канале?
            async with s.get(
                f"https://api.telegram.org/bot{tok}/getChatMember",
                params={"chat_id": target, "user_id": tok.split(":")[0]},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                d = await resp.json()
                print("    bot member check:", d.get("ok"), d.get("result", {}).get("status"), d.get("description", ""))
            # админ (создатель) подписан?
            async with s.get(
                f"https://api.telegram.org/bot{tok}/getChatMember",
                params={"chat_id": target, "user_id": settings.admin_id_list[0]},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                d = await resp.json()
                print("    admin member check:", d.get("ok"), d.get("result", {}).get("status"), d.get("description", ""))


asyncio.run(main())
