"""Middleware: регистрация/обновление пользователя при каждом сообщении и нажатии."""
from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from bot.services import users as users_svc

logger = logging.getLogger(__name__)


class UserMiddleware:
    async def __call__(
        self,
        handler: Callable[[Any, dict[str, Any]], Awaitable[Any]],
        event: Any,
        data: dict[str, Any],
    ) -> Any:
        tg_user = getattr(event, "from_user", None)
        session = data.get("session")
        if tg_user is None or session is None or tg_user.is_bot:
            return await handler(event, data)

        db_user = await users_svc.get_or_create_user(
            session, tg_user.id, tg_user.username
        )
        await session.commit()
        data["user"] = db_user
        return await handler(event, data)
