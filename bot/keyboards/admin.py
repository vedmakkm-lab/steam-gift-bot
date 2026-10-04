"""Общие клавиатуры админ-панели."""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def admin_panel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🎮 Steam-аккаунты", callback_data="adm:acc"),
                InlineKeyboardButton(text="🎟 Промокоды", callback_data="adm:promo"),
            ],
            [
                InlineKeyboardButton(text="📢 Каналы", callback_data="adm:ch"),
                InlineKeyboardButton(text="👥 Пользователи", callback_data="adm:users"),
            ],
            [
                InlineKeyboardButton(text="📊 Статистика", callback_data="adm:stats"),
                InlineKeyboardButton(text="📜 История выдач", callback_data="adm:hist:1"),
            ],
            [
                InlineKeyboardButton(text="💰 Пожертвования", callback_data="adm:don"),
                InlineKeyboardButton(text="📢 Реклама", callback_data="adm:ads"),
            ],
            [
                InlineKeyboardButton(text="⚙️ Настройки", callback_data="adm:set"),
                InlineKeyboardButton(text="🔄 Сброс выдач", callback_data="adm:reset"),
            ],
        ]
    )


def back_row(callback: str, text: str = "⬅️ Назад") -> list[InlineKeyboardButton]:
    return [InlineKeyboardButton(text=text, callback_data=callback)]


def cancel_row() -> list[InlineKeyboardButton]:
    return [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel:admin")]


def cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[cancel_row()])


def confirm_kb(
    ok_cb: str,
    ok_text: str = "✅ Да",
    back_cb: str = "adm:home",
    back_text: str = "❌ Отмена",
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=ok_text, callback_data=ok_cb)],
            [InlineKeyboardButton(text=back_text, callback_data=back_cb)],
        ]
    )
