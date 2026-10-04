"""Хендлеры пользователя: /start, выдача аккаунта, подписки, донаты, промокоды."""
from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice, Message, PreCheckoutQuery

from bot.config import get_settings
from bot.database.models import Ad, User
from bot.keyboards import user as kb
from bot.middlewares.throttling import ThrottlingMiddleware  # noqa: F401
from bot.services import accounts as accounts_svc
from bot.services import ads as ads_svc
from bot.services import channels as channels_svc
from bot.services import donations as donations_svc
from bot.services import issuing
from bot.services import promos as promos_svc
from bot.services import settings as settings_svc
from bot.services import users as users_svc
from bot.states import UserSG
from bot.utils.telegram import esc, safe_edit

router = Router(name="user")
logger = logging.getLogger(__name__)

MAIN_MENU_TEXT = (
    "⚠️ <b>ВНИМАНИЕ</b>\n"
    "Steam-аккаунт можно получить бесплатно только 1 раз на одного пользователя.\n"
    "Для получения аккаунта необходимо подписаться на указанные каналы."
)

NO_ACCOUNTS_TEXT = (
    "❌ В данный момент доступных аккаунтов нет.\n"
    "Попробуйте позже."
)

ALREADY_GOT_TEXT = (
    "❌ Вы уже получали Steam-аккаунт.\n"
    "Бесплатная выдача для вашего аккаунта уже использована.\n\n"
    "🎟 Есть промокод? Нажмите «🎟 Ввести промокод», чтобы получить дополнительные выдачи."
)

ISSUED_TEXT = "🎉 <b>Аккаунт выдан!</b> Данные в следующем сообщении 👇"

SUBSCRIBE_TEXT = (
    "📢 Для получения аккаунта подпишитесь на каналы:\n\n"
    "Нажмите «Подписаться» у каждого канала, затем нажмите «✅ Проверить подписку»."
)


async def render_main_menu(session, with_ad: bool = True) -> tuple[str, InlineKeyboardMarkup]:
    ad: Ad | None = await ads_svc.get_random_active(session) if with_ad else None
    text = MAIN_MENU_TEXT
    if ad:
        text += f"\n\n{esc(ad.text)}"
    return text, kb.main_menu_kb(ad)


def account_text(account) -> str:
    games = account.games_list
    games_block = "\n".join(f"<code>{esc(g)}</code>" for g in games) if games else "<i>не указаны</i>"
    return (
        "🎮 <b>Ваш Steam-аккаунт</b>\n\n"
        f"🔑 Логин: <code>{esc(account.login)}</code>\n"
        f"🔒 Пароль: <code>{esc(account.password)}</code>\n\n"
        "🎮 <b>Игры на аккаунте:</b>\n"
        f"{games_block}"
    )


def ad_text(ad: Ad) -> str:
    return esc(ad.text)


@router.message(CommandStart())
async def cmd_start(message: Message, session, state: FSMContext) -> None:
    await state.clear()
    text, keyboard = await render_main_menu(session)
    await message.answer(text, reply_markup=keyboard)


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, session, state: FSMContext) -> None:
    await state.clear()
    if message.from_user and message.from_user.id in get_settings().admin_id_list:
        await message.answer("🛠 <b>Админ-панель</b>", reply_markup=kb_admin_panel())
    else:
        text, keyboard = await render_main_menu(session)
        await message.answer(text, reply_markup=keyboard)


def kb_admin_panel():
    from bot.keyboards.admin import admin_panel_kb

    return admin_panel_kb()


@router.message(Command("admin"))
async def cmd_admin_denied(message: Message) -> None:
    # Реальная админ-панель доступна только администраторам (роутер admin).
    await message.answer("⛔ У вас нет доступа к админ-панели.")


@router.callback_query(F.data == "noop")
async def cb_noop(callback: CallbackQuery) -> None:
    await callback.answer()


@router.callback_query(F.data == "menu:home")
async def cb_home(callback: CallbackQuery, session, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    if callback.message:
        text, keyboard = await render_main_menu(session)
        await safe_edit(callback.message, text, keyboard)


@router.callback_query(F.data.in_({"menu:get", "sub:check"}))
async def cb_get_account(callback: CallbackQuery, session, user: User, state: FSMContext, bot: Bot) -> None:
    """Главный сценарий: проверки -> случайная выдача."""
    await state.clear()
    await callback.answer()
    if not callback.message:
        return

    # Шаг 1. Есть ли аккаунты в базе
    if not await accounts_svc.has_any_account(session):
        await safe_edit(callback.message, NO_ACCOUNTS_TEXT, kb.back_kb())
        return

    # Шаг 2. Подписка на обязательные каналы
    channels = await channels_svc.get_active_channels(session)
    if channels:
        not_subscribed = await channels_svc.get_not_subscribed(bot, channels, callback.from_user.id)
        if not_subscribed:
            await safe_edit(callback.message, SUBSCRIBE_TEXT, kb.channels_kb(not_subscribed))
            return

    # Шаг 3. Право на получение (перечитываем пользователя — данные могли измениться)
    fresh = await users_svc.get_by_telegram_id(session, callback.from_user.id) or user
    if not fresh.has_right():
        await safe_edit(callback.message, ALREADY_GOT_TEXT, kb.back_kb())
        return

    # Шаг 4. Случайная выдача (аккаунт остаётся в базе)
    result = await issuing.issue_account(session, fresh.telegram_id, fresh.username)
    if result.status == "no_accounts":
        await safe_edit(callback.message, NO_ACCOUNTS_TEXT, kb.back_kb())
        return
    if result.status == "no_rights":
        await safe_edit(callback.message, ALREADY_GOT_TEXT, kb.back_kb())
        return

    await safe_edit(callback.message, ISSUED_TEXT, kb.back_kb())
    assert result.account is not None
    await callback.message.answer(account_text(result.account))

    ad = await ads_svc.get_random_active(session)
    if ad:
        markup = None
        if ad.button_text and ad.url:
            markup = InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text=ad.button_text, url=ad.url)]]
            )
        await callback.message.answer(ad_text(ad), reply_markup=markup)


@router.callback_query(F.data == "menu:donate")
async def cb_donate(callback: CallbackQuery, session) -> None:
    await callback.answer()
    if not callback.message:
        return
    presets = await settings_svc.get_donation_presets(session)
    text = (
        f"💳 Kaspi: <code>{esc(get_settings().kaspi_number)}</code>\n\n"
        "⭐ Или поддержите бота Telegram Stars — выберите сумму:"
    )
    await safe_edit(callback.message, text, kb.donate_kb(presets))


@router.callback_query(F.data.startswith("don:buy:"))
async def cb_donate_buy(callback: CallbackQuery, bot: Bot) -> None:
    if not callback.message:
        return
    amount_raw = callback.data.rsplit(":", 1)[-1]
    if not amount_raw.isdigit() or not (1 <= int(amount_raw) <= 100000):
        await callback.answer("❌ Некорректная сумма", show_alert=True)
        return
    amount = int(amount_raw)
    try:
        await bot.send_invoice(
            chat_id=callback.message.chat.id,
            title=f"Поддержка бота — {amount}⭐",
            description="Спасибо за поддержку проекта! 💛",
            payload=f"donate:{amount}",
            provider_token="",  # Telegram Stars (XTR) работает без платёжного провайдера
            currency="XTR",
            prices=[LabeledPrice(label=f"{amount} Stars", amount=amount)],
        )
    except TelegramAPIError as e:
        logger.warning("Не удалось создать счёт Stars: %s", e)
        await callback.answer("❌ Не удалось создать счёт. Попробуйте позже.", show_alert=True)
        return
    await callback.answer("Счёт создан 👇")


@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery) -> None:
    if query.invoice_payload.startswith("donate:"):
        await query.answer(ok=True)
    else:
        await query.answer(ok=False, error_message="Неверный платёж. Попробуйте ещё раз.")


@router.message(F.successful_payment)
async def on_successful_payment(message: Message, session) -> None:
    sp = message.successful_payment
    await donations_svc.record_payment(
        session,
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        stars=sp.total_amount,
        charge_id=sp.telegram_payment_charge_id,
        payload=sp.invoice_payload,
    )
    try:
        await session.commit()
    except Exception:  # noqa: BLE001 — повторная доставка события
        await session.rollback()
    await message.answer(
        f"✅ Оплата получена: <b>{sp.total_amount} ⭐</b>\nСпасибо за поддержку! 💛"
    )


@router.callback_query(F.data == "menu:promo")
async def cb_promo(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(UserSG.promo_code)
    if callback.message:
        await safe_edit(
            callback.message,
            "🎟 Введите промокод:",
            kb.promo_input_kb(),
        )


@router.callback_query(F.data == "promo:cancel")
async def cb_promo_cancel(callback: CallbackQuery, session, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    if callback.message:
        text, keyboard = await render_main_menu(session)
        await safe_edit(callback.message, text, keyboard)


@router.message(UserSG.promo_code, F.text)
async def process_promo(message: Message, session, user: User, state: FSMContext) -> None:
    code = message.text.strip()
    await state.clear()

    ok, reason, granted = await promos_svc.activate(session, user, code)
    if ok:
        try:
            await session.commit()
        except Exception:  # noqa: BLE001 — гонка: промокод уже активирован этим пользователем
            await session.rollback()
            ok, reason, granted = False, promos_svc.REASON_ALREADY_USED, 0

    if ok:
        result_text = (
            "✅ <b>Промокод активирован!</b>\n"
            f"🎁 Начислено дополнительных получений: <b>{granted}</b>"
        )
    else:
        texts = {
            promos_svc.REASON_NOT_FOUND: "❌ Промокод не найден.",
            promos_svc.REASON_INACTIVE: "❌ Промокод больше не активен.",
            promos_svc.REASON_EXPIRED: "❌ Срок действия промокода истёк.",
            promos_svc.REASON_MAX_REACHED: "❌ Лимит активаций промокода исчерпан.",
            promos_svc.REASON_ALREADY_USED: "❌ Вы уже активировали этот промокод.",
        }
        result_text = texts.get(reason, "❌ Не удалось активировать промокод.")

    text, keyboard = await render_main_menu(session)
    await message.answer(f"{result_text}\n\n{text}", reply_markup=keyboard)
