"""Пагинация списков в inline-клавиатурах."""
from __future__ import annotations

import math
from typing import Sequence

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.utils.telegram import esc


def paginate(items: Sequence, page: int, per_page: int) -> tuple[Sequence, int, int]:
    """Возвращает (элементы страницы, текущая страница, всего страниц)."""
    total_pages = max(1, math.ceil(len(items) / per_page)) if items else 1
    page = min(max(1, page), total_pages)
    start = (page - 1) * per_page
    return items[start : start + per_page], page, total_pages


def nav_kb(
    prefix: str,
    page: int,
    total_pages: int,
    back_cb: str | None = None,
    back_text: str = "⬅️ Назад",
) -> InlineKeyboardMarkup:
    """Клавиатура навигации. Callback'и имеют вид '{prefix}:{page}'."""
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    if page > 1:
        row.append(InlineKeyboardButton(text="◀️", callback_data=f"{prefix}:{page - 1}"))
    row.append(InlineKeyboardButton(text=f"📄 {page}/{total_pages}", callback_data="noop"))
    if page < total_pages:
        row.append(InlineKeyboardButton(text="▶️", callback_data=f"{prefix}:{page + 1}"))
    rows.append(row)
    if back_cb:
        rows.append([InlineKeyboardButton(text=back_text, callback_data=back_cb)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def short(value: str, limit: int = 24) -> str:
    """Короткое представление значения для кнопки."""
    clean = esc(value)
    return clean if len(clean) <= limit else clean[: limit - 1] + "…"
