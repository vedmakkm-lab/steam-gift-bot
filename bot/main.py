"""Точка входа бота: инициализация, middlewares, polling.

Запуск: python main.py  (из корня проекта, с заполненным .env)
"""
from __future__ import annotations

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, Update

from bot.config import get_settings
from bot.database.engine import build_engine, build_sessionmaker
from bot.database.models import Base
from bot.handlers import setup_routers
from bot.middlewares.db import DbSessionMiddleware
from bot.middlewares.throttling import ThrottlingMiddleware
from bot.middlewares.user import UserMiddleware
from bot.utils.logging import setup_logging


async def create_tables_if_sqlite(engine) -> None:
    """Для SQLite (локальный запуск) создаём таблицы автоматически.
    Для PostgreSQL используйте миграции: alembic upgrade head."""
    if engine.dialect.name == "sqlite":
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)


async def _run_health_server(port: int) -> None:
    """Мини-HTTP-сервер для health-check (порт из HEALTH_PORT).

    Нужен платформам типа Hugging Face Spaces: контейнер должен слушать порт.
    """
    from aiohttp import web

    async def health(_request) -> "web.Response":
        return web.Response(text="ok")

    app = web.Application()
    app.router.add_get("/", health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logging.info("Health-сервер слушает порт %s", port)
    await asyncio.Event().wait()  # держим сервер до остановки процесса


async def run_webhook(bot: Bot, dp: Dispatcher, settings) -> None:
    """Webhook-режим: Telegram сам присылает обновления на наш HTTP-сервер.

    Используется на хостингах (Render и т.п.), где сервис обязан слушать
    HTTP-порт. GET / и /healthz отвечают 'ok' — для пинга от засыпания.
    """
    from aiohttp import web

    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Главное меню"),
            BotCommand(command="cancel", description="Отменить действие"),
        ]
    )
    if settings.webhook_register:
        await bot.set_webhook(
            url=settings.webhook_url,
            secret_token=settings.webhook_secret or None,
            allowed_updates=dp.resolve_used_update_types(),
            drop_pending_updates=True,
        )
        logging.info("Webhook зарегистрирован: %s", settings.webhook_url)
    else:
        logging.warning("WEBHOOK_REGISTER=false — set_webhook пропущен (тестовый режим)")

    async def on_webhook(request: web.Request) -> web.Response:
        if settings.webhook_secret:
            header = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
            if header != settings.webhook_secret:
                return web.Response(status=403, text="forbidden")
        try:
            data = await request.json()
        except Exception:  # noqa: BLE001
            return web.Response(status=400, text="bad json")
        update = Update.model_validate(data, context={"bot": bot})
        await dp.feed_update(bot, update)
        return web.Response(text="ok")

    async def health(_request: web.Request) -> web.Response:
        return web.Response(text="ok")

    app = web.Application()
    app.router.add_get("/", health)
    app.router.add_get("/healthz", health)
    app.router.add_post(settings.webhook_path, on_webhook)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", settings.port)
    await site.start()
    logging.info(
        "Webhook-сервер слушает 0.0.0.0:%s%s", settings.port, settings.webhook_path
    )
    await asyncio.Event().wait()


async def main() -> None:
    setup_logging()
    settings = get_settings()

    if not settings.bot_token:
        print("❌ BOT_TOKEN не задан. Скопируйте .env.example в .env и укажите токен бота.")
        sys.exit(1)

    logging.info("Запуск бота…")

    engine = build_engine(settings.database_url)
    await create_tables_if_sqlite(engine)
    sessionmaker = build_sessionmaker(engine)

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    # Порядок middlewares: антифлуд -> сессия БД -> пользователь
    dp.message.middleware(ThrottlingMiddleware())
    dp.callback_query.middleware(ThrottlingMiddleware())
    dp.message.middleware(DbSessionMiddleware(sessionmaker))
    dp.callback_query.middleware(DbSessionMiddleware(sessionmaker))
    dp.message.middleware(UserMiddleware())
    dp.callback_query.middleware(UserMiddleware())

    setup_routers(dp)

    try:
        if settings.webhook_url:
            await run_webhook(bot, dp, settings)
        else:
            if settings.health_port:
                asyncio.create_task(_run_health_server(settings.health_port))
            await bot.set_my_commands(
                [
                    BotCommand(command="start", description="Главное меню"),
                    BotCommand(command="cancel", description="Отменить действие"),
                ]
            )
            await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()
        await engine.dispose()
        logging.info("Бот остановлен.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
