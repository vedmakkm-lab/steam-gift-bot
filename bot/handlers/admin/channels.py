"""Админ: управление каналами обязательной подписки."""
from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.keyboards.admin import cancel_kb
from bot.services import channels as channels_svc
from bot.states import ChSG
from bot.utils.telegram import esc, parse_int, safe_edit

router = Router(name="admin:channels")
logger = logging.getLogger(__name__)

CANCEL = cancel_kb()


def channel_card(channel) -> str:
    status = "✅ активен" if channel.is_active else "⛔ отключён"
    username = f"@{esc(channel.username)}" if channel.username else "—"
    chat_id = str(channel.chat_id) if channel.chat_id else "—"
    return (
        f"📢 <b>{esc(channel.title)}</b>\n\n"
        f"🆔 ID: <code>{chat_id}</code>\n"
        f"👤 Username: {username}\n"
        f"🔗 Ссылка: {esc(channel.url)}\n"
        f"Статус: {status}"
    )


def item_kb(channel_id: int, is_active: bool) -> InlineKeyboardMarkup:
    toggle_text = "🚫 Отключить" if is_active else "✅ Включить"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=toggle_text, callback_data=f"adm:ch:tg:{channel_id}")],
            [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"adm:ch:rm:{channel_id}")],
            [InlineKeyboardButton(text="⬅️ К списку", callback_data="adm:ch:list")],
        ]
    )


@router.callback_query(F.data == "adm:ch")
async def cb_menu(callback: CallbackQuery, session) -> None:
    await callback.answer()
    if not callback.message:
        return
    channels = await channels_svc.get_all_channels(session)
    active = sum(1 for c in channels if c.is_active)
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить канал", callback_data="adm:ch:new")],
            [InlineKeyboardButton(text="📋 Список каналов", callback_data="adm:ch:list")],
            [InlineKeyboardButton(text="🔄 Проверить настройки", callback_data="adm:ch:check")],
            [InlineKeyboardButton(text="⬅️ В админ-панель", callback_data="adm:home")],
        ]
    )
    await safe_edit(
        callback.message,
        f"📢 <b>Каналы</b>\n\nВсего: {len(channels)} | Активных: {active}\n\n"
        "Пользователь должен быть подписан на все активные каналы, "
        "чтобы получить аккаунт.",
        kb,
    )


# ---------- Добавление ----------

@router.callback_query(F.data == "adm:ch:new")
async def cb_new(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(ChSG.chat)
    if callback.message:
        await safe_edit(
            callback.message,
            "📢 <b>Добавление канала</b>\n\n"
            "1️⃣ Отправьте @username канала или его числовой ID (например, -1001234567890).\n\n"
            "⚠️ Бот должен быть <b>администратором</b> канала, иначе проверка подписки работать не будет.",
            CANCEL,
        )


@router.message(ChSG.chat, F.text)
async def ch_chat(message: Message, state: FSMContext, bot: Bot) -> None:
    raw = message.text.strip()
    try:
        chat = await bot.get_chat(raw)
    except Exception:  # noqa: BLE001 — Telegram API ошибки
        await message.answer(
            "❌ Не удалось найти канал. Проверьте @username/ID и то, что бот добавлен в канал.\n"
            "Попробуйте ещё раз:",
            reply_markup=CANCEL,
        )
        return
    if chat.type not in ("channel", "supergroup"):
        await message.answer(
            "❌ Это не канал. Отправьте @username или ID канала:", reply_markup=CANCEL
        )
        return
    await state.update_data(
        title=chat.title or raw,
        chat_id=chat.id,
        username=chat.username,
        invite_link=chat.invite_link,
    )
    await state.set_state(ChSG.link)
    found = f"Найден канал: <b>{esc(chat.title or raw)}</b>"
    if chat.username:
        found += f"\nПодпись по умолчанию будет: https://t.me/{chat.username}"
    await message.answer(
        f"{found}\n\n2️⃣ Отправьте ссылку для кнопки «Подписаться» (https://...)\n"
        "или «-», чтобы использовать ссылку по умолчанию:",
        reply_markup=CANCEL,
    )


@router.message(ChSG.link, F.text)
async def ch_link(message: Message, session, state: FSMContext) -> None:
    raw = message.text.strip()
    data = await state.get_data()
    await state.clear()

    url: str | None = None
    if raw not in {"-", "—"}:
        if not raw.startswith(("http://", "https://")):
            await state.set_state(ChSG.link)
            await message.answer("❌ Ссылка должна начинаться с https:// . Попробуйте ещё раз:", reply_markup=CANCEL)
            return
        url = raw
    elif data.get("username"):
        url = f"https://t.me/{data['username']}"
    elif data.get("invite_link"):
        url = data["invite_link"]

    if not url:
        await state.set_state(ChSG.link)
        await message.answer(
            "❌ У приватного канала без username нужна ссылка-приглашение.\nОтправьте ссылку:",
            reply_markup=CANCEL,
        )
        return

    channel, created = await channels_svc.add_channel(
        session,
        title=data["title"],
        chat_id=data["chat_id"],
        username=data.get("username"),
        url=url,
    )
    await session.commit()
    prefix = "✅ Канал добавлен!" if created else "⚠️ Этот канал уже был добавлен."
    await message.answer(
        f"{prefix}\n\n{channel_card(channel)}\n\n"
        "⚠️ Не забудьте назначить бота администратором канала.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="⬅️ К каналам", callback_data="adm:ch")]]
        ),
    )


# ---------- Список / карточка ----------

@router.callback_query(F.data == "adm:ch:list")
async def cb_list(callback: CallbackQuery, session) -> None:
    await callback.answer()
    if not callback.message:
        return
    channels = await channels_svc.get_all_channels(session)
    if not channels:
        await safe_edit(
            callback.message,
            "📢 Каналы не добавлены.",
            InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="adm:ch")]]
            ),
        )
        return
    rows = [
        [InlineKeyboardButton(text=f"{'✅' if c.is_active else '⛔'} {c.title[:30]}", callback_data=f"adm:ch:item:{c.id}")]
        for c in channels
    ]
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="adm:ch")])
    await safe_edit(
        callback.message,
        f"📢 <b>Список каналов</b> ({len(channels)})",
        InlineKeyboardMarkup(inline_keyboard=rows),
    )


@router.callback_query(F.data.startswith("adm:ch:item:"))
async def cb_item(callback: CallbackQuery, session) -> None:
    await callback.answer()
    if not callback.message:
        return
    channel = await channels_svc.get_by_id(session, parse_int(callback.data.rsplit(":", 1)[-1]) or 0)
    if channel is None:
        return
    await safe_edit(callback.message, channel_card(channel), item_kb(channel.id, channel.is_active))


@router.callback_query(F.data.startswith("adm:ch:tg:"))
async def cb_toggle(callback: CallbackQuery, session) -> None:
    await callback.answer()
    if not callback.message:
        return
    channel = await channels_svc.get_by_id(session, parse_int(callback.data.rsplit(":", 1)[-1]) or 0)
    if channel is None:
        return
    await channels_svc.toggle_active(session, channel.id)
    await session.commit()
    await safe_edit(callback.message, channel_card(channel), item_kb(channel.id, channel.is_active))


@router.callback_query(F.data.startswith("adm:ch:rmok:"))
async def cb_delete_ok(callback: CallbackQuery, session) -> None:
    await callback.answer()
    if not callback.message:
        return
    deleted = await channels_svc.delete_channel(session, parse_int(callback.data.rsplit(":", 1)[-1]) or 0)
    await session.commit()
    if deleted:
        await safe_edit(
            callback.message,
            "✅ Канал удалён.",
            InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="⬅️ К каналам", callback_data="adm:ch")]]
            ),
        )


@router.callback_query(F.data.startswith("adm:ch:rm:"))
async def cb_delete(callback: CallbackQuery, session) -> None:
    await callback.answer()
    if not callback.message:
        return
    channel = await channels_svc.get_by_id(session, parse_int(callback.data.rsplit(":", 1)[-1]) or 0)
    if channel is None:
        return
    await safe_edit(
        callback.message,
        f"⚠️ Удалить канал <b>{esc(channel.title)}</b>?",
        InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🗑 Да, удалить", callback_data=f"adm:ch:rmok:{channel.id}")],
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="adm:ch:list")],
            ]
        ),
    )


# ---------- Проверка настроек ----------

@router.callback_query(F.data == "adm:ch:check")
async def cb_check(callback: CallbackQuery, session, bot: Bot) -> None:
    await callback.answer("Проверяю…")
    if not callback.message:
        return
    channels = await channels_svc.get_all_channels(session)
    if not channels:
        await safe_edit(
            callback.message,
            "📢 Каналы не добавлены.",
            InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="adm:ch")]]
            ),
        )
        return
    report = await channels_svc.check_channels(bot, channels)
    await safe_edit(
        callback.message,
        "🔄 <b>Проверка настроек каналов</b>\n\n" + "\n".join(esc(r) for r in report),
        InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="⬅️ К каналам", callback_data="adm:ch")]]
        ),
    )
