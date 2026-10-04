"""Админ: общая статистика и история выдач."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from bot.services import accounts as accounts_svc
from bot.services import donations as donations_svc
from bot.services import history as history_svc
from bot.services import users as users_svc
from bot.utils.pagination import nav_kb
from bot.utils.telegram import esc, parse_int, safe_edit
from bot.utils.timefmt import fmt_dt

router = Router(name="admin:stats")


@router.callback_query(F.data == "adm:stats")
async def cb_stats(callback: CallbackQuery, session) -> None:
    await callback.answer()
    if not callback.message:
        return
    u = await users_svc.users_stats(session)
    h = await history_svc.issues_stats(session)
    total_accounts = await accounts_svc.count_accounts(session)
    d = await donations_svc.donations_stats(session)

    await safe_edit(
        callback.message,
        "📊 <b>Статистика</b>\n\n"
        f"👥 Всего пользователей: <b>{u['total']}</b>\n"
        f"🆕 Новых сегодня: <b>{u['new_today']}</b>\n"
        f"🎮 Всего Steam-аккаунтов: <b>{total_accounts}</b>\n"
        f"🎁 Всего выдач: <b>{h['total']}</b>\n"
        f"📅 Выдач сегодня: <b>{h['today']}</b>\n"
        f"📅 Выдач за неделю: <b>{h['week']}</b>\n"
        f"📅 Выдач за месяц: <b>{h['month']}</b>\n"
        f"🎟 Активаций промокодов: <b>{u['promo_activations']}</b>\n"
        f"⭐ Всего получено Stars: <b>{d['stars_total']}</b> ({d['count']} платежей)\n"
        f"💰 Сумма пожертвований: <b>{d['stars_total']} ⭐</b>",
        InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="⬅️ В админ-панель", callback_data="adm:home")]]
        ),
    )


@router.callback_query(F.data.startswith("adm:hist:"))
async def cb_history(callback: CallbackQuery, session) -> None:
    await callback.answer()
    if not callback.message:
        return
    page = parse_int(callback.data.rsplit(":", 1)[-1]) or 1
    items, page, total_pages = await history_svc.get_page(session, page)
    if not items:
        text = "📜 История выдач пуста."
    else:
        lines = ["📜 <b>История выдач</b>\n"]
        for it in items:
            username = f"@{esc(it.username)}" if it.username else "—"
            lines.append(
                f"#{it.id} | {fmt_dt(it.created_at)}\n"
                f"👤 {username} ({it.telegram_id}) → 🎮 #{it.account_id or '—'} ({esc(it.account_login or '—')}) | {it.type_label}"
            )
        text = "\n".join(lines)
    await safe_edit(
        callback.message,
        text,
        nav_kb("adm:hist", page, total_pages, "adm:home"),
    )
