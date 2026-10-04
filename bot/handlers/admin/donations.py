"""Админ: пожертвования (статистика) и возврат Stars (/refund)."""
from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.services import donations as donations_svc
from bot.utils.telegram import esc, safe_edit
from bot.utils.timefmt import fmt_dt

router = Router(name="admin:donations")
logger = logging.getLogger(__name__)


@router.callback_query(F.data == "adm:don")
async def cb_donations(callback: CallbackQuery, session) -> None:
    await callback.answer()
    if not callback.message:
        return
    stats = await donations_svc.donations_stats(session)
    recent = await donations_svc.get_recent(session, limit=10)

    lines = [
        "💰 <b>Пожертвования</b>\n",
        f"⭐ Всего Stars: <b>{stats['stars_total']}</b>",
        f"🧾 Платежей: <b>{stats['count']}</b>",
        f"📅 Сегодня: <b>{stats['today_stars']} ⭐</b> ({stats['today_count']} платежей)",
    ]
    if recent:
        lines.append("\n<b>Последние платежи:</b>")
        for p in recent:
            username = f"@{esc(p.username)}" if p.username else "—"
            lines.append(f"• {username} ({p.telegram_id}) — {p.stars}⭐ — {fmt_dt(p.created_at)}")
    else:
        lines.append("\nПлатежей пока нет.")

    await safe_edit(
        callback.message,
        "\n".join(lines),
        InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="⬅️ В админ-панель", callback_data="adm:home")]]
        ),
    )


@router.message(Command("refund"))
async def cmd_refund(message: Message, session, bot: Bot) -> None:
    """/refund <telegram_payment_charge_id> — вернуть Stars пользователю."""
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer("Использование: <code>/refund &lt;charge_id&gt;</code>")
        return
    charge_id = parts[1].strip()
    payments = await donations_svc.get_recent(session, limit=100)
    payment = next((p for p in payments if p.charge_id == charge_id), None)
    if payment is None:
        await message.answer("❌ Платёж не найден среди последних 100. Проверьте charge_id.")
        return
    try:
        await bot.refund_star_payment(
            user_id=payment.telegram_id,
            telegram_payment_charge_id=payment.charge_id,
        )
    except TelegramAPIError as e:
        logger.warning("Возврат %s не удался: %s", charge_id, e)
        await message.answer(f"❌ Возврат не удался: {esc(e)}")
        return
    logger.info("Возврат Stars: charge=%s user=%s", charge_id, payment.telegram_id)
    await message.answer(
        f"✅ Возврат выполнен: {payment.stars}⭐ пользователю {payment.telegram_id}."
    )
