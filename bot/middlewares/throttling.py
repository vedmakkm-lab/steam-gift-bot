"""Простой антифлуд: не чаще одного действия в 0.4 сек на пользователя."""
from __future__ import annotations

import logging
import time
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)

_INTERVAL = 0.4


class ThrottlingMiddleware:
    def __init__(self) -> None:
        self._last: dict[int, float] = {}

    async def __call__(
        self,
        handler: Callable[[Any, dict[str, Any]], Awaitable[Any]],
        event: Any,
        data: dict[str, Any],
    ) -> Any:
        tg_user = getattr(event, "from_user", None)
        if tg_user is None or tg_user.is_bot:
            return await handler(event, data)

        now = time.monotonic()
        last = self._last.get(tg_user.id)
        self._last[tg_user.id] = now
        # периодически чистим словарь, чтобы он не рос бесконечно
        if len(self._last) > 10000:
            cutoff = now - 60
            self._last = {uid: ts for uid, ts in self._last.items() if ts > cutoff}

        if last is not None and now - last < _INTERVAL:
            answer = getattr(event, "answer", None)
            if answer is not None and event.__class__.__name__ == "CallbackQuery":
                try:
                    await event.answer("⏳ Не так быстро", show_alert=False)
                except Exception:  # noqa: BLE001
                    pass
            return None
        return await handler(event, data)
