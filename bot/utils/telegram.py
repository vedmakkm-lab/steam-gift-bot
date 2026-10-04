"""Мелкие помощники для работы с Telegram API."""
from __future__ import annotations

import html
import logging

from aiogram.exceptions import TelegramAPIError, TelegramBadRequest

logger = logging.getLogger(__name__)


def esc(value: object) -> str:
    """Экранирование для HTML parse mode."""
    return html.escape(str(value), quote=False)


async def safe_edit(message, text: str, reply_markup=None) -> None:
    """edit_text без падений на 'message is not modified' и прочих мелочах API."""
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e).lower():
            logger.warning("edit_text не удался: %s", e)
    except TelegramAPIError as e:
        logger.warning("edit_text не удался (API): %s", e)


def parse_int(value: str) -> int | None:
    try:
        return int(value.strip())
    except (ValueError, AttributeError):
        return None
