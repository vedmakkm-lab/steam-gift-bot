"""Админ: пользователи (статистика, поиск, карточка, действия)."""
from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.handlers.user import account_text
from bot.keyboards.admin import cancel_kb
from bot.services import issuing
from bot.services import users as users_svc
from bot.services import history as history_svc
from bot.states import UsersSG
from bot.utils.telegram import esc, parse_int, safe_edit
from bot.utils.timefmt import fmt_dt

router = Router(name="admin:users")
logger = logging.getLogger(__name__)

CANCEL = cancel_kb()


def user_card(user, issues: list, total_issues: int) -> str:
    free_line = "использована" if user.free_claim_used else "доступна ✅"
    username = f"@{esc(user.username)}" if user.username else "—"
    lines = [
        "👤 <b>Пользователь</b>\n",
        f"🆔 Telegram ID: <code>{user.telegram_id}</code>",
        f"👤 Username: {username}",
        f"📅 Регистрация: {fmt_dt(user.created_at)}",
        f"🎁 Бесплатная выдача: {free_line}",
        f"🎟 Доп. выдачи: {user.extra_claims_used} из {user.extra_claims} (доступно {user.extra_left})",
        f"📊 Всего получено аккаунтов: {total_issues}",
        f"🕓 Последняя выдача: {fmt_dt(user.last_issue_at)}",
    ]
    if issues:
        lines.append("\n📜 Последние выдачи:")
        for h in issues:
            lines.append(
                f"• {fmt_dt(h.created_at)} — #{h.account_id or '—'} ({esc(h.account_login or '—')}) — {h.type_label}"
            )
    return "\n".join(lines)


def user_actions_kb(telegram_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="➕1 выдача", callback_data=f"adm:users:g1:{telegram_id}"),
                InlineKeyboardButton(text="➕5 выдач", callback_data=f"adm:users:g5:{telegram_id}"),
            ],
            [InlineKeyboardButton(text="🎁 Выдать аккаунт вручную", callback_data=f"adm:users:ga:{telegram_id}")],
            [InlineKeyboardButton(text="🔄 Сбросить бесплатную выдачу", callback_data=f"adm:users:rf1:{telegram_id}")],
            [InlineKeyboardButton(text="⬅️ В раздел", callback_data="adm:users")],
        ]
    )


async def send_user_card(session, telegram_id: int) -> str | None:
    """Рендер карточки пользователя. Возвращает текст или None, если не найден."""
    user = await users_svc.get_by_telegram_id(session, telegram_id)
    if user is None:
        return None
    issues = await history_svc.recent_for_user(session, telegram_id)
    total = await history_svc.count_for_user(session, telegram_id)
    return user_card(user, issues, total)


@router.callback_query(F.data == "adm:users")
async def cb_menu(callback: CallbackQuery, session) -> None:
    await callback.answer()
    if not callback.message:
        return
    stats = await users_svc.users_stats(session)
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔍 Найти по Telegram ID", callback_data="adm:users:find")],
            [InlineKeyboardButton(text="⬅️ В админ-панель", callback_data="adm:home")],
        ]
    )
    await safe_edit(
        callback.message,
        "👥 <b>Пользователи</b>\n\n"
        f"Всего пользователей: <b>{stats['total']}</b>\n"
        f"Получили бесплатный аккаунт: <b>{stats['free_used']}</b>\n"
        f"С дополнительными выдачами: <b>{stats['with_extra']}</b>\n"
        f"Активаций промокодов: <b>{stats['promo_activations']}</b>",
        kb,
    )


@router.callback_query(F.data == "adm:users:find")
async def cb_find(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(UsersSG.tid)
    if callback.message:
        await safe_edit(callback.message, "🔍 Отправьте Telegram ID пользователя:", CANCEL)


@router.message(UsersSG.tid, F.text)
async def find_user(message: Message, session, state: FSMContext) -> None:
    tid = parse_int(message.text)
    await state.clear()
    if tid is None:
        await message.answer("❌ ID должен быть числом. Попробуйте ещё раз: /admin → Пользователи.")
        return
    text = await send_user_card(session, tid)
    if text is None:
        await message.answer(f"❌ Пользователь {tid} не найден.")
        return
    await message.answer(text, reply_markup=user_actions_kb(tid))


async def _show_user(callback: CallbackQuery, session, telegram_id: int) -> None:
    text = await send_user_card(session, telegram_id)
    if text is None:
        await callback.answer("❌ Пользователь не найден", show_alert=True)
        return
    await safe_edit(callback.message, text, user_actions_kb(telegram_id))


@router.callback_query(F.data.startswith("adm:users:item:"))
async def cb_item(callback: CallbackQuery, session) -> None:
    await callback.answer()
    if callback.message:
        await _show_user(callback, session, parse_int(callback.data.rsplit(":", 1)[-1]) or 0)


@router.callback_query(F.data.startswith("adm:users:g5:"))
async def cb_give5(callback: CallbackQuery, session) -> None:
    await callback.answer("Начислено +5 выдач")
    tid = parse_int(callback.data.rsplit(":", 1)[-1]) or 0
    await users_svc.grant_extra_claims(session, tid, 5)
    await session.commit()
    if callback.message:
        await _show_user(callback, session, tid)


@router.callback_query(F.data.startswith("adm:users:g1:"))
async def cb_give1(callback: CallbackQuery, session) -> None:
    await callback.answer("Начислена +1 выдача")
    tid = parse_int(callback.data.rsplit(":", 1)[-1]) or 0
    await users_svc.grant_extra_claims(session, tid, 1)
    await session.commit()
    if callback.message:
        await _show_user(callback, session, tid)


@router.callback_query(F.data.startswith("adm:users:ga:"))
async def cb_give_account(callback: CallbackQuery, session, bot: Bot) -> None:
    tid = parse_int(callback.data.rsplit(":", 1)[-1]) or 0
    user = await users_svc.get_by_telegram_id(session, tid)
    if user is None:
        await callback.answer("❌ Пользователь не найден", show_alert=True)
        return
    result = await issuing.force_issue(session, tid, user.username, issue_type="admin")
    if result.status == "no_accounts":
        await callback.answer("❌ В базе нет аккаунтов", show_alert=True)
        return
    await callback.answer("✅ Аккаунт выдан")
    try:
        await bot.send_message(tid, "🎁 Администратор выдал вам Steam-аккаунт!\n\n" + account_text(result.account))
    except TelegramAPIError:
        logger.warning("Не удалось уведомить пользователя %s о ручной выдаче", tid)
    if callback.message:
        await _show_user(callback, session, tid)


@router.callback_query(F.data.startswith("adm:users:rf2:"))
async def cb_reset_free_ok(callback: CallbackQuery, session) -> None:
    tid = parse_int(callback.data.rsplit(":", 1)[-1]) or 0
    reset = await users_svc.reset_user_free_claim(session, tid)
    await session.commit()
    await callback.answer("✅ Сброшено" if reset else "Нечего сбрасывать")
    if callback.message:
        await _show_user(callback, session, tid)


@router.callback_query(F.data.startswith("adm:users:rf1:"))
async def cb_reset_free(callback: CallbackQuery) -> None:
    await callback.answer()
    if not callback.message:
        return
    tid = parse_int(callback.data.rsplit(":", 1)[-1]) or 0
    await safe_edit(
        callback.message,
        f"⚠️ Сбросить бесплатную выдачу для пользователя <code>{tid}</code>?\n"
        "Он сможет снова получить бесплатный аккаунт. История сохранится.",
        InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✅ Да, сбросить", callback_data=f"adm:users:rf2:{tid}")],
                [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"adm:users:item:{tid}")],
            ]
        ),
    )
