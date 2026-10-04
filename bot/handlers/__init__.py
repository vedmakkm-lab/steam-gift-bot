"""Регистрация всех роутеров бота."""
from aiogram import Dispatcher

from bot.handlers import errors, user
from bot.handlers.admin import admin_router


def setup_routers(dp: Dispatcher) -> None:
    # Админ-роутер первым: /admin у администраторов перехватывается им,
    # а у обычных пользователей срабатывает «доступ запрещён» из user-роутера.
    dp.include_router(admin_router)
    dp.include_router(user.router)
    dp.include_router(errors.router)
