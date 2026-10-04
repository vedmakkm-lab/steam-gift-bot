"""Сборка админ-роутера. Фильтр IsAdmin применяется ко всем хендлерам."""
from aiogram import Router

from bot.filters import IsAdmin
from . import (
    accounts,
    ads,
    channels,
    donations,
    panel,
    promos,
    settings,
    stats,
    users,
)


def build_admin_router() -> Router:
    root = Router(name="admin")
    root.message.filter(IsAdmin())
    root.callback_query.filter(IsAdmin())
    root.include_routers(
        panel.router,
        accounts.router,
        promos.router,
        channels.router,
        users.router,
        stats.router,
        donations.router,
        ads.router,
        settings.router,
    )
    return root


admin_router = build_admin_router()
