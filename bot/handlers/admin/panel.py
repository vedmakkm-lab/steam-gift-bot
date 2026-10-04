"""Вход в админ-панель и общие колбэки (домой / отмена)."""
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.keyboards.admin import admin_panel_kb
from bot.utils.telegram import safe_edit

router = Router(name="admin:panel")

PANEL_TEXT = "🛠 <b>Админ-панель</b>\n\nВыберите раздел:"


@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(PANEL_TEXT, reply_markup=admin_panel_kb())


@router.callback_query(F.data == "adm:home")
async def cb_home(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    if callback.message:
        await safe_edit(callback.message, PANEL_TEXT, admin_panel_kb())


@router.callback_query(F.data == "cancel:admin")
async def cb_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer("Действие отменено")
    if callback.message:
        await safe_edit(callback.message, PANEL_TEXT, admin_panel_kb())
