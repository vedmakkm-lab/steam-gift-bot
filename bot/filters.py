"""Фильтры доступа."""
from aiogram.filters import BaseFilter
from aiogram.types import TelegramObject

from bot.config import get_settings


class IsAdmin(BaseFilter):
    """Доступ только для Telegram ID из ADMIN_IDS."""

    async def __call__(self, event: TelegramObject) -> bool:
        user = getattr(event, "from_user", None)
        return bool(user) and user.id in get_settings().admin_id_list
