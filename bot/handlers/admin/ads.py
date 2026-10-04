"""Админ: рекламные блоки (текст + inline-кнопка со ссылкой)."""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.keyboards.admin import cancel_kb
from bot.services import ads as ads_svc
from bot.states import AdSG
from bot.utils.telegram import esc, parse_int, safe_edit
from bot.utils.timefmt import fmt_dt

router = Router(name="admin:ads")
logger = logging.getLogger(__name__)

CANCEL = cancel_kb()


def ad_card(ad) -> str:
    button = f"«{esc(ad.button_text)}» → {esc(ad.url)}" if ad.button_text and ad.url else "—"
    status = "✅ активен" if ad.is_active else "⛔ отключён"
    return (
        f"📢 <b>Рекламный блок #{ad.id}</b>\n\n"
        f"Текст:\n{esc(ad.text)}\n\n"
        f"🔘 Кнопка: {button}\n"
        f"Статус: {status}\n"
        f"➕ Создан: {fmt_dt(ad.created_at)}"
    )


def item_kb(ad_id: int, is_active: bool) -> InlineKeyboardMarkup:
    toggle_text = "🚫 Отключить" if is_active else "✅ Включить"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=toggle_text, callback_data=f"adm:ads:tg:{ad_id}")],
            [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"adm:ads:rm:{ad_id}")],
            [InlineKeyboardButton(text="⬅️ К списку", callback_data="adm:ads:list")],
        ]
    )


@router.callback_query(F.data == "adm:ads")
async def cb_menu(callback: CallbackQuery, session) -> None:
    await callback.answer()
    if not callback.message:
        return
    ads = await ads_svc.get_all(session)
    active = sum(1 for a in ads if a.is_active)
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Создать блок", callback_data="adm:ads:new")],
            [InlineKeyboardButton(text="📋 Список блоков", callback_data="adm:ads:list")],
            [InlineKeyboardButton(text="⬅️ В админ-панель", callback_data="adm:home")],
        ]
    )
    await safe_edit(
        callback.message,
        f"📢 <b>Реклама</b>\n\nВсего блоков: {len(ads)} | Активных: {active}\n\n"
        "Активные блоки показываются в главном меню и после выдачи аккаунта.",
        kb,
    )


@router.callback_query(F.data == "adm:ads:new")
async def cb_new(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(AdSG.text)
    if callback.message:
        await safe_edit(
            callback.message,
            "📢 <b>Создание рекламного блока</b>\n\n1️⃣ Отправьте текст рекламы:",
            CANCEL,
        )


@router.message(AdSG.text, F.text)
async def ad_text_step(message: Message, state: FSMContext) -> None:
    await state.update_data(text=message.text.strip())
    await state.set_state(AdSG.button)
    await message.answer(
        "2️⃣ Отправьте текст inline-кнопки (или «-», если кнопка не нужна):",
        reply_markup=CANCEL,
    )


@router.message(AdSG.button, F.text)
async def ad_button_step(message: Message, session, state: FSMContext) -> None:
    button = message.text.strip()
    if button in {"-", "—"}:
        data = await state.get_data()
        await state.clear()
        ad = await ads_svc.create_ad(session, data["text"], None, None)
        await session.commit()
        await message.answer(
            f"✅ Рекламный блок создан!\n\n{ad_card(ad)}",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="⬅️ К рекламе", callback_data="adm:ads")]]
            ),
        )
        return
    await state.update_data(button=button)
    await state.set_state(AdSG.url)
    await message.answer("3️⃣ Отправьте ссылку для кнопки (https://...):", reply_markup=CANCEL)


@router.message(AdSG.url, F.text)
async def ad_url_step(message: Message, session, state: FSMContext) -> None:
    url = message.text.strip()
    if not url.startswith(("http://", "https://")):
        await message.answer("❌ Ссылка должна начинаться с https:// . Попробуйте ещё раз:", reply_markup=CANCEL)
        return
    data = await state.get_data()
    await state.clear()
    ad = await ads_svc.create_ad(session, data["text"], data["button"], url)
    await session.commit()
    await message.answer(
        f"✅ Рекламный блок создан!\n\n{ad_card(ad)}",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="⬅️ К рекламе", callback_data="adm:ads")]]
        ),
    )


@router.callback_query(F.data == "adm:ads:list")
async def cb_list(callback: CallbackQuery, session) -> None:
    await callback.answer()
    if not callback.message:
        return
    ads = await ads_svc.get_all(session)
    if not ads:
        await safe_edit(
            callback.message,
            "📢 Рекламных блоков пока нет.",
            InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="adm:ads")]]
            ),
        )
        return
    rows = [
        [InlineKeyboardButton(text=f"{'✅' if a.is_active else '⛔'} #{a.id} {a.text[:24]}", callback_data=f"adm:ads:item:{a.id}")]
        for a in ads
    ]
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="adm:ads")])
    await safe_edit(
        callback.message,
        f"📢 <b>Рекламные блоки</b> ({len(ads)})",
        InlineKeyboardMarkup(inline_keyboard=rows),
    )


@router.callback_query(F.data.startswith("adm:ads:item:"))
async def cb_item(callback: CallbackQuery, session) -> None:
    await callback.answer()
    if not callback.message:
        return
    ad = await ads_svc.get_by_id(session, parse_int(callback.data.rsplit(":", 1)[-1]) or 0)
    if ad is None:
        return
    await safe_edit(callback.message, ad_card(ad), item_kb(ad.id, ad.is_active))


@router.callback_query(F.data.startswith("adm:ads:tg:"))
async def cb_toggle(callback: CallbackQuery, session) -> None:
    await callback.answer()
    if not callback.message:
        return
    ad = await ads_svc.get_by_id(session, parse_int(callback.data.rsplit(":", 1)[-1]) or 0)
    if ad is None:
        return
    await ads_svc.toggle_active(session, ad.id)
    await session.commit()
    await safe_edit(callback.message, ad_card(ad), item_kb(ad.id, ad.is_active))


@router.callback_query(F.data.startswith("adm:ads:rmok:"))
async def cb_delete_ok(callback: CallbackQuery, session) -> None:
    await callback.answer()
    if not callback.message:
        return
    deleted = await ads_svc.delete_ad(session, parse_int(callback.data.rsplit(":", 1)[-1]) or 0)
    await session.commit()
    if deleted:
        await safe_edit(
            callback.message,
            "✅ Рекламный блок удалён.",
            InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="⬅️ К рекламе", callback_data="adm:ads")]]
            ),
        )


@router.callback_query(F.data.startswith("adm:ads:rm:"))
async def cb_delete(callback: CallbackQuery, session) -> None:
    await callback.answer()
    if not callback.message:
        return
    ad = await ads_svc.get_by_id(session, parse_int(callback.data.rsplit(":", 1)[-1]) or 0)
    if ad is None:
        return
    await safe_edit(
        callback.message,
        f"⚠️ Удалить рекламный блок #{ad.id}?",
        InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🗑 Да, удалить", callback_data=f"adm:ads:rmok:{ad.id}")],
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="adm:ads:list")],
            ]
        ),
    )
