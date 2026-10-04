"""Админ: настройки (суммы пожертвований) и сброс выдач."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.config import get_settings
from bot.keyboards.admin import cancel_kb
from bot.services import settings as settings_svc
from bot.services import users as users_svc
from bot.states import DonSetSG
from bot.utils.telegram import esc, parse_int, safe_edit

router = Router(name="admin:settings")

CANCEL = cancel_kb()


async def settings_view(session) -> tuple[str, InlineKeyboardMarkup]:
    presets = await settings_svc.get_donation_presets(session)
    cfg = get_settings()
    db_kind = cfg.database_url.split("://")[0]
    preset_buttons = [
        InlineKeyboardButton(text=f"✖️ {v}", callback_data=f"adm:set:drm:{v}")
        for v in presets
    ]
    kb_rows = [
        [InlineKeyboardButton(text="➕ Добавить сумму доната", callback_data="adm:set:dadd")],
        preset_buttons,
        [InlineKeyboardButton(text="♻️ Сбросить к стандартным", callback_data="adm:set:dreset")],
        [InlineKeyboardButton(text="⬅️ В админ-панель", callback_data="adm:home")],
    ]
    text = (
        "⚙️ <b>Настройки</b>\n\n"
        f"💳 Kaspi: <code>{esc(cfg.kaspi_number)}</code>\n"
        f"🕒 Таймзона: <code>{esc(cfg.display_tz)}</code>\n"
        f"🗄 Тип БД: <code>{esc(db_kind)}</code>\n"
        f"👑 Администраторов: <b>{len(cfg.admin_id_list)}</b>\n\n"
        f"⭐ Суммы пожертвований (нажмите на сумму, чтобы удалить):\n<b>{', '.join(map(str, presets))}</b>"
    )
    return text, InlineKeyboardMarkup(inline_keyboard=kb_rows)


@router.callback_query(F.data == "adm:set")
async def cb_menu(callback: CallbackQuery, session) -> None:
    await callback.answer()
    if callback.message:
        text, kb = await settings_view(session)
        await safe_edit(callback.message, text, kb)


@router.callback_query(F.data == "adm:set:dadd")
async def cb_add_amount(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(DonSetSG.amount)
    if callback.message:
        await safe_edit(callback.message, "⭐ Отправьте сумму в Stars (число > 0):", CANCEL)


@router.message(DonSetSG.amount, F.text)
async def add_amount(message: Message, session, state: FSMContext) -> None:
    amount = parse_int(message.text)
    await state.clear()
    if amount is None or amount <= 0:
        await message.answer("❌ Введите число больше 0.")
        return
    presets = await settings_svc.get_donation_presets(session)
    if amount not in presets:
        presets.append(amount)
    await settings_svc.set_donation_presets(session, presets)
    await session.commit()
    text, kb = await settings_view(session)
    await message.answer(f"✅ Сумма добавлена.\n\n{text}", reply_markup=kb)


@router.callback_query(F.data.startswith("adm:set:drm:"))
async def cb_remove_amount(callback: CallbackQuery, session) -> None:
    await callback.answer()
    if not callback.message:
        return
    value = parse_int(callback.data.rsplit(":", 1)[-1])
    if value is None:
        return
    presets = await settings_svc.get_donation_presets(session)
    presets = [v for v in presets if v != value]
    if not presets:
        await callback.answer("Должна остаться хотя бы одна сумма", show_alert=True)
        return
    await settings_svc.set_donation_presets(session, presets)
    await session.commit()
    text, kb = await settings_view(session)
    await safe_edit(callback.message, text, kb)


@router.callback_query(F.data == "adm:set:dreset")
async def cb_reset_amounts(callback: CallbackQuery, session) -> None:
    await callback.answer("Сброшено к стандартным")
    defaults = get_settings().donation_preset_list or [25, 50, 100, 250, 500]
    await settings_svc.set_donation_presets(session, defaults)
    await session.commit()
    if callback.message:
        text, kb = await settings_view(session)
        await safe_edit(callback.message, text, kb)


# ---------- Сброс выдач ----------

RESET_CONFIRM_TEXT = (
    "⚠️ <b>Внимание!</b>\n\n"
    "Это позволит пользователям снова использовать свою бесплатную выдачу.\n\n"
    "История предыдущих выдач при этом сохраняется."
)


@router.callback_query(F.data == "adm:reset")
async def cb_reset(callback: CallbackQuery) -> None:
    await callback.answer()
    if not callback.message:
        return
    await safe_edit(
        callback.message,
        RESET_CONFIRM_TEXT,
        InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✅ Сбросить", callback_data="adm:reset:ok")],
                [InlineKeyboardButton(text="❌ Отмена", callback_data="adm:home")],
            ]
        ),
    )


@router.callback_query(F.data == "adm:reset:ok")
async def cb_reset_ok(callback: CallbackQuery, session) -> None:
    await callback.answer()
    if not callback.message:
        return
    affected = await users_svc.reset_all_free_claims(session)
    await session.commit()
    await safe_edit(
        callback.message,
        f"✅ <b>Готово!</b> Сброшено пользователей: <b>{affected}</b>\n\n"
        "• free_claim_used = false у всех пользователей\n"
        "• Пользователи снова могут получить бесплатный аккаунт\n"
        "• Steam-аккаунты не изменены\n"
        "• История выдач сохранена",
        InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="⬅️ В админ-панель", callback_data="adm:home")]]
        ),
    )
