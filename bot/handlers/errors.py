"""Глобальный обработчик ошибок: логируем и мягко сообщаем пользователю."""
from __future__ import annotations

import logging

from aiogram import Router
from aiogram.types import CallbackQuery, ErrorEvent, Message

router = Router(name="errors")
logger = logging.getLogger(__name__)


@router.errors()
async def on_error(event: ErrorEvent) -> bool:
    logger.exception("Необработанная ошибка: %s", event.exception)

    update = event.update
    message: Message | None = getattr(update, "message", None) or getattr(update, "edited_message", None)
    callback: CallbackQuery | None = getattr(update, "callback_query", None)

    if callback is not None:
        try:
            await callback.answer("⚠️ Произошла ошибка. Попробуйте позже.", show_alert=True)
        except Exception:  # noqa: BLE001
            pass
    elif message is not None:
        try:
            await message.answer("⚠️ Произошла ошибка. Попробуйте позже.")
        except Exception:  # noqa: BLE001
            pass
    return True
