"""Админ: промокоды (создание, список, вкл/выкл, удаление)."""
from __future__ import annotations

import logging

from sqlalchemy.exc import IntegrityError
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.keyboards.admin import cancel_kb
from bot.services import promos as promos_svc
from bot.states import PromoSG
from bot.utils.telegram import esc, parse_int, safe_edit
from bot.utils.timefmt import fmt_dt

router = Router(name="admin:promos")
logger = logging.getLogger(__name__)

CANCEL = cancel_kb()


def promo_card(promo) -> str:
    limit = f"{promo.activations_count} / {promo.max_activations}" if promo.max_activations else f"{promo.activations_count} / ∞"
    expires = fmt_dt(promo.expires_at) if promo.expires_at else "бессрочно"
    status = "✅ активен" if promo.is_active else "⛔ отключён"
    return (
        f"🎟 <b>Промокод {esc(promo.code)}</b>\n\n"
        f"🎁 Награда: +{promo.reward_amount} доп. выдач\n"
        f"📊 Активаций: {limit}\n"
        f"🗓 Истекает: {expires}\n"
        f"Статус: {status}\n"
        f"➕ Создан: {fmt_dt(promo.created_at)}"
    )


def item_kb(promo_id: int, is_active: bool) -> InlineKeyboardMarkup:
    toggle_text = "🚫 Отключить" if is_active else "✅ Включить"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=toggle_text, callback_data=f"adm:promo:tg:{promo_id}")],
            [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"adm:promo:rm:{promo_id}")],
            [InlineKeyboardButton(text="⬅️ К списку", callback_data="adm:promo:list")],
        ]
    )


@router.callback_query(F.data == "adm:promo")
async def cb_menu(callback: CallbackQuery, session) -> None:
    await callback.answer()
    if not callback.message:
        return
    promos = await promos_svc.get_all(session)
    active = sum(1 for p in promos if p.is_active)
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎟 Создать промокод", callback_data="adm:promo:new")],
            [InlineKeyboardButton(text="📋 Список промокодов", callback_data="adm:promo:list")],
            [InlineKeyboardButton(text="⬅️ В админ-панель", callback_data="adm:home")],
        ]
    )
    await safe_edit(
        callback.message,
        f"🎟 <b>Промокоды</b>\n\nВсего: {len(promos)} | Активных: {active}",
        kb,
    )


# ---------- Создание ----------

@router.callback_query(F.data == "adm:promo:new")
async def cb_new(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(PromoSG.code)
    if callback.message:
        await safe_edit(
            callback.message,
            "🎟 <b>Создание промокода</b>\n\n1️⃣ Отправьте код промокода\n(или «gen» — сгенерировать автоматически):",
            CANCEL,
        )


@router.message(PromoSG.code, F.text)
async def promo_code(message: Message, state: FSMContext) -> None:
    code = message.text.strip()
    if code.lower() == "gen":
        code = promos_svc.generate_code()
    await state.update_data(code=code)
    await state.set_state(PromoSG.amount)
    await message.answer(
        f"Код: <code>{esc(code)}</code>\n\n2️⃣ Сколько дополнительных выдач даёт промокод? (число > 0):",
        reply_markup=CANCEL,
    )


@router.message(PromoSG.amount, F.text)
async def promo_amount(message: Message, state: FSMContext) -> None:
    amount = parse_int(message.text)
    if amount is None or amount <= 0 or amount > 10000:
        await message.answer("❌ Введите число от 1 до 10000:", reply_markup=CANCEL)
        return
    await state.update_data(amount=amount)
    await state.set_state(PromoSG.max_uses)
    await message.answer("3️⃣ Максимальное количество активаций (0 — без лимита):", reply_markup=CANCEL)


@router.message(PromoSG.max_uses, F.text)
async def promo_max_uses(message: Message, state: FSMContext) -> None:
    max_uses = parse_int(message.text)
    if max_uses is None or max_uses < 0:
        await message.answer("❌ Введите число (0 — без лимита):", reply_markup=CANCEL)
        return
    await state.update_data(max_uses=max_uses)
    await state.set_state(PromoSG.days)
    await message.answer("4️⃣ Срок действия в днях (0 — бессрочно):", reply_markup=CANCEL)


@router.message(PromoSG.days, F.text)
async def promo_days(message: Message, session, state: FSMContext) -> None:
    days = parse_int(message.text)
    if days is None or days < 0:
        await message.answer("❌ Введите число (0 — бессрочно):", reply_markup=CANCEL)
        return
    data = await state.get_data()
    code, amount, max_uses = data["code"], data["amount"], data["max_uses"]
    if await promos_svc.get_by_code(session, code) is not None:
        await state.set_state(PromoSG.code)
        await message.answer("❌ Промокод с таким кодом уже существует. Отправьте другой код:", reply_markup=CANCEL)
        return
    data["days"] = days
    limit = str(max_uses) if max_uses else "∞"
    expires = f"{days} дн." if days else "бессрочно"
    await state.set_state(None)
    await state.set_data(data)
    await message.answer(
        "🎟 <b>Новый промокод</b>\n\n"
        f"Код: <code>{esc(code)}</code>\n"
        f"Награда: +{amount} доп. выдач\n"
        f"Лимит активаций: {limit}\n"
        f"Срок действия: {expires}\n\n"
        "Создать?",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✅ Создать", callback_data="adm:promo:save")],
                [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel:admin")],
            ]
        ),
    )


@router.callback_query(F.data == "adm:promo:save")
async def promo_save(callback: CallbackQuery, session, state: FSMContext) -> None:
    await callback.answer()
    data = await state.get_data()
    if "code" not in data:
        await callback.answer("Данные потеряны, создайте промокод заново", show_alert=True)
        return
    try:
        promo = await promos_svc.create_promo(
            session,
            code=data["code"],
            amount=data["amount"],
            max_activations=data["max_uses"] or None,
            days=data["days"] or None,
        )
        await session.commit()
    except IntegrityError:
        await session.rollback()
        await callback.answer("❌ Промокод с таким кодом уже существует", show_alert=True)
        return
    await state.clear()
    if callback.message:
        await safe_edit(
            callback.message,
            f"✅ Промокод создан!\n\n{promo_card(promo)}",
            InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="⬅️ К промокодам", callback_data="adm:promo")]]
            ),
        )


# ---------- Список / карточка ----------

@router.callback_query(F.data == "adm:promo:list")
async def cb_list(callback: CallbackQuery, session) -> None:
    await callback.answer()
    if not callback.message:
        return
    promos = await promos_svc.get_all(session)
    if not promos:
        await safe_edit(
            callback.message,
            "🎟 Промокодов пока нет.",
            InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="adm:promo")]]
            ),
        )
        return
    lines = [f"🎟 <b>Промокоды</b> ({len(promos)})\n"]
    for p in promos[:25]:
        status = "✅" if p.is_active else "⛔"
        limit = f"/{p.max_activations}" if p.max_activations else ""
        lines.append(f"• <code>{esc(p.code)}</code> — +{p.reward_amount} — {p.activations_count}{limit} — {status}")
    rows = [
        [InlineKeyboardButton(text=p.code, callback_data=f"adm:promo:item:{p.id}")]
        for p in promos[:25]
    ]
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="adm:promo")])
    await safe_edit(callback.message, "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data.startswith("adm:promo:item:"))
async def cb_item(callback: CallbackQuery, session) -> None:
    await callback.answer()
    if not callback.message:
        return
    promo = await promos_svc.get_by_id(session, parse_int(callback.data.rsplit(":", 1)[-1]) or 0)
    if promo is None:
        await callback.answer("❌ Не найден", show_alert=True)
        return
    await safe_edit(callback.message, promo_card(promo), item_kb(promo.id, promo.is_active))


@router.callback_query(F.data.startswith("adm:promo:tg:"))
async def cb_toggle(callback: CallbackQuery, session) -> None:
    await callback.answer()
    if not callback.message:
        return
    promo = await promos_svc.get_by_id(session, parse_int(callback.data.rsplit(":", 1)[-1]) or 0)
    if promo is None:
        return
    await promos_svc.toggle_active(session, promo.id)
    await session.commit()
    await safe_edit(callback.message, promo_card(promo), item_kb(promo.id, promo.is_active))


@router.callback_query(F.data.startswith("adm:promo:rmok:"))
async def cb_delete_ok(callback: CallbackQuery, session) -> None:
    await callback.answer()
    if not callback.message:
        return
    deleted = await promos_svc.delete_promo(session, parse_int(callback.data.rsplit(":", 1)[-1]) or 0)
    await session.commit()
    if deleted:
        await safe_edit(
            callback.message,
            "✅ Промокод удалён.",
            InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="⬅️ К промокодам", callback_data="adm:promo")]]
            ),
        )


@router.callback_query(F.data.startswith("adm:promo:rm:"))
async def cb_delete(callback: CallbackQuery, session) -> None:
    await callback.answer()
    if not callback.message:
        return
    promo = await promos_svc.get_by_id(session, parse_int(callback.data.rsplit(":", 1)[-1]) or 0)
    if promo is None:
        return
    await safe_edit(
        callback.message,
        f"⚠️ Удалить промокод <code>{esc(promo.code)}</code>?\nАктивации пользователей при этом удалятся.",
        InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🗑 Да, удалить", callback_data=f"adm:promo:rmok:{promo.id}")],
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="adm:promo:list")],
            ]
        ),
    )
