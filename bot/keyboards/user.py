"""Клавиатуры пользователя."""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.database.models import Ad, Channel


def main_menu_kb(ad: Ad | None = None) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="🎮 Получить аккаунт", callback_data="menu:get")],
        [InlineKeyboardButton(text="💰 Пожертвовать", callback_data="menu:donate")],
        [InlineKeyboardButton(text="🎟 Ввести промокод", callback_data="menu:promo")],
    ]
    if ad and ad.button_text and ad.url:
        rows.append([InlineKeyboardButton(text=ad.button_text, url=ad.url)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def back_kb(callback: str = "menu:home", text: str = "⬅️ В меню") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=text, callback_data=callback)]]
    )


def channels_kb(channels: list[Channel]) -> InlineKeyboardMarkup:
    rows = []
    for channel in channels:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"📢 {channel.title} — Подписаться",
                    url=channel.url,
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="✅ Проверить подписку", callback_data="sub:check")])
    rows.append([InlineKeyboardButton(text="⬅️ В меню", callback_data="menu:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def donate_kb(presets: list[int]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"⭐ {amount} Stars", callback_data=f"don:buy:{amount}")]
        for amount in presets
    ]
    rows.append([InlineKeyboardButton(text="⬅️ В меню", callback_data="menu:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def promo_input_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="promo:cancel")]]
    )
