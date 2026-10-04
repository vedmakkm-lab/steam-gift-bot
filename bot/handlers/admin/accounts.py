"""Админ: управление Steam-аккаунтами (добавление, массовая загрузка, список,
изменение, удаление, статистика, история)."""
from __future__ import annotations

import io
import logging
import re

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.keyboards.admin import cancel_kb
from bot.services import accounts as accounts_svc
from bot.services import history as history_svc
from bot.states import AccSG, BulkSG, EditSG
from bot.utils.pagination import nav_kb, short
from bot.utils.telegram import esc, parse_int, safe_edit
from bot.utils.timefmt import fmt_dt

router = Router(name="admin:accounts")
logger = logging.getLogger(__name__)

BULK_FORMAT_HELP = (
    "📥 <b>Массовая загрузка</b>\n\n"
    "Пришлите .txt файл в одном из форматов.\n\n"
    "<b>Формат 1 — по строке на аккаунт:</b>\n"
    "<code>login:password</code>\n"
    "<code>login:password | Game 1, Game 2, Game 3</code>\n\n"
    "<b>Формат 2 — блоками (как в вашем файле):</b>\n"
    "<code>Логин: login</code>\n"
    "<code>Пароль: password</code>\n"
    "<code>Игры: Game 1, Game 2</code>\n\n"
    "Также понимает английские ключи (Login/Password/Games). "
    "«Игры: Не указано» сохранится без списка игр."
)

# Блок-формат: "Логин: ...", "Пароль: ...", "Игры: ..." (RU/EN, ':' или '=')
_BLOCK_KEY_RE = re.compile(
    r"^\s*(логин|login|пароль|password|pass|игры|games)\s*[:=]\s*(.*)$",
    re.IGNORECASE,
)
_LOGIN_KEYS = {"логин", "login"}
_PASSWORD_KEYS = {"пароль", "password", "pass"}
_GAMES_KEYS = {"игры", "games"}


def _clean_block_games(raw: str) -> str:
    """Чистит список игр из блок-формата: убирает '\\', пустые части и 'Не указано'."""
    games: list[str] = []
    for part in raw.split(","):
        part = part.strip().strip("\\").strip().lstrip("+").strip()
        if not part or part.lower() == "не указано" or part.lower() == "not specified":
            continue
        if part not in games:
            games.append(part)
    return "\n".join(games)


def _parse_block_format(text: str) -> tuple[list[tuple[str, str, str]], list[tuple[int, str]]]:
    """Разбор блок-формата: Логин/Пароль/Игры (список игр может идти и продолжением)."""
    items: list[tuple[str, str, str]] = []
    invalid: list[tuple[int, str]] = []
    login: str | None = None
    password: str | None = None
    games_raw: list[str] = []
    start_line = 0

    def flush() -> None:
        nonlocal login, password, games_raw, start_line
        if login and password:
            items.append((login, password, _clean_block_games(", ".join(games_raw))))
        elif login or password or games_raw:
            invalid.append((start_line or 0, f"{login or '—'} / {password or '—'}"))
        login, password, games_raw, start_line = None, None, [], 0

    for line_no, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        match = _BLOCK_KEY_RE.match(line)
        if match:
            key, value = match.group(1).lower(), match.group(2).strip()
            if key in _LOGIN_KEYS:
                flush()
                login = value
                start_line = line_no
            elif key in _PASSWORD_KEYS:
                if login is None:
                    invalid.append((line_no, line[:60]))
                else:
                    password = value
            elif key in _GAMES_KEYS:
                if login is None:
                    invalid.append((line_no, line[:60]))
                else:
                    games_raw.append(value)
        else:
            # строка-продолжение (например, список игр перенесён на следующую строку)
            if login is not None and password is not None:
                games_raw.append(line)
            else:
                invalid.append((line_no, line[:60]))
    flush()
    return items, invalid

CANCEL = cancel_kb()


def account_card(acc) -> str:
    games = ", ".join(acc.games_list) if acc.games_list else "—"
    return (
        f"🎮 <b>Аккаунт #{acc.id}</b>\n\n"
        f"🔑 Логин: <code>{esc(acc.login)}</code>\n"
        f"🔒 Пароль: <code>{esc(acc.password)}</code>\n"
        f"🎮 Игры: {esc(games)}\n\n"
        f"📊 Выдач: {acc.issues_count}\n"
        f"🕓 Последняя выдача: {fmt_dt(acc.last_issue_at)}\n"
        f"➕ Добавлен: {fmt_dt(acc.added_at)}"
    )


def edit_card_kb(account_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔑 Логин", callback_data=f"adm:acc:editf:{account_id}:login"),
                InlineKeyboardButton(text="🔒 Пароль", callback_data=f"adm:acc:editf:{account_id}:password"),
            ],
            [InlineKeyboardButton(text="🎮 Игры", callback_data=f"adm:acc:editf:{account_id}:games")],
            [InlineKeyboardButton(text="⬅️ К выбору аккаунта", callback_data="adm:acc:editp:1")],
        ]
    )


def parse_bulk_text(text: str) -> tuple[list[tuple[str, str, str]], list[tuple[int, str]]]:
    """Разбор .txt. Поддерживает два формата:

    1) Блоками: 'Логин: ...' / 'Пароль: ...' / 'Игры: ...' (RU или EN ключи);
    2) По строке на аккаунт: 'login:password' или 'login:password | Game 1, Game 2'.
    """
    if re.search(r"^\s*(логин|login)\s*[:=]", text, re.IGNORECASE | re.MULTILINE):
        return _parse_block_format(text)

    items: list[tuple[str, str, str]] = []
    invalid: list[tuple[int, str]] = []
    for line_no, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        if "|" in line:
            creds, _, games_part = line.partition("|")
            games = accounts_svc.normalize_games_csv(games_part)
        else:
            creds, games = line, ""
        login, sep, password = creds.strip().partition(":")
        if not sep or not login.strip() or not password.strip():
            invalid.append((line_no, line[:60]))
            continue
        items.append((login.strip(), password.strip(), games))
    return items, invalid


# ---------- Раздел ----------

@router.callback_query(F.data == "adm:acc")
async def cb_menu(callback: CallbackQuery, session) -> None:
    await callback.answer()
    if not callback.message:
        return
    total = await accounts_svc.count_accounts(session)
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить аккаунт", callback_data="adm:acc:add")],
            [InlineKeyboardButton(text="📥 Массовая загрузка", callback_data="adm:acc:bulk")],
            [InlineKeyboardButton(text="📋 Список аккаунтов", callback_data="adm:acc:list:1")],
            [InlineKeyboardButton(text="✏️ Изменить аккаунт", callback_data="adm:acc:editp:1")],
            [InlineKeyboardButton(text="🗑 Удалить аккаунт", callback_data="adm:acc:delp:1")],
            [InlineKeyboardButton(text="📊 Статистика", callback_data="adm:acc:stats")],
            [InlineKeyboardButton(text="📜 История выдач", callback_data="adm:acc:hist:1")],
            [InlineKeyboardButton(text="⬅️ В админ-панель", callback_data="adm:home")],
        ]
    )
    await safe_edit(
        callback.message,
        f"🎮 <b>Steam-аккаунты</b>\n\nВсего в базе: <b>{total}</b>\n\n"
        "Аккаунты общие: выдача никогда не удаляет их автоматически.",
        kb,
    )


# ---------- Добавление ----------

@router.callback_query(F.data == "adm:acc:add")
async def cb_add(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(AccSG.login)
    if callback.message:
        await safe_edit(callback.message, "➕ <b>Добавление аккаунта</b>\n\n1️⃣ Отправьте логин:", CANCEL)


@router.message(AccSG.login, F.text)
async def add_login(message: Message, state: FSMContext) -> None:
    await state.update_data(login=message.text.strip())
    await state.set_state(AccSG.password)
    await message.answer("2️⃣ Отправьте пароль:", reply_markup=CANCEL)


@router.message(AccSG.password, F.text)
async def add_password(message: Message, state: FSMContext) -> None:
    await state.update_data(password=message.text.strip())
    await state.set_state(AccSG.games)
    await message.answer(
        "3️⃣ Перечислите игры на аккаунте через запятую\n(или отправьте «-», если игр нет):",
        reply_markup=CANCEL,
    )


@router.message(AccSG.games, F.text)
async def add_games(message: Message, session, state: FSMContext) -> None:
    raw = message.text.strip()
    games = "" if raw in {"-", "—"} else accounts_svc.normalize_games_csv(raw)
    data = await state.get_data()
    await state.clear()

    account = await accounts_svc.create_account(
        session, data["login"], data["password"], games
    )
    await session.commit()
    await message.answer(
        f"✅ Аккаунт добавлен!\n\n{account_card(account)}",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="⬅️ К аккаунтам", callback_data="adm:acc")]]
        ),
    )


# ---------- Массовая загрузка ----------

@router.callback_query(F.data == "adm:acc:bulk")
async def cb_bulk(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(BulkSG.file)
    if callback.message:
        await safe_edit(callback.message, BULK_FORMAT_HELP, CANCEL)


@router.message(BulkSG.file, F.document)
async def bulk_file(message: Message, session, state: FSMContext) -> None:
    doc = message.document
    if not doc.file_name or not doc.file_name.lower().endswith((".txt", ".csv", ".log")):
        await message.answer("❌ Нужен текстовый файл (.txt). Попробуйте ещё раз.", reply_markup=CANCEL)
        return
    if (doc.file_size or 0) > 2_000_000:
        await message.answer("❌ Файл слишком большой (максимум 2 МБ).", reply_markup=CANCEL)
        return

    file_obj = await message.bot.download(doc, destination=io.BytesIO())
    text = file_obj.getvalue().decode("utf-8", errors="replace").lstrip("\ufeff")

    items, invalid = parse_bulk_text(text)
    added, skipped = await accounts_svc.bulk_create_accounts(session, items)
    await session.commit()
    await state.clear()

    lines = [
        "📥 <b>Массовая загрузка завершена</b>\n",
        f"✅ Добавлено: <b>{added}</b>",
        f"⏭ Пропущено (уже есть в базе или повтор в файле): <b>{skipped}</b>",
        f"❌ Ошибочных строк: <b>{len(invalid)}</b>",
    ]
    if invalid:
        lines.append("\nПервые ошибочные строки:")
        lines.extend(f"• строка {n}: <code>{esc(s)}</code>" for n, s in invalid[:5])
    lines.append(
        "\nℹ️ Дубликат — совпадение пары логин+пароль (регистр логина не важен). "
        "Один логин с разными паролями добавляется как отдельный аккаунт. "
        "Каждый аккаунт сохранён отдельной записью."
    )
    await message.answer(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="⬅️ К аккаунтам", callback_data="adm:acc")]]
        ),
    )


@router.message(BulkSG.file)
async def bulk_not_file(message: Message) -> None:
    await message.answer("❌ Пожалуйста, отправьте файл (.txt).", reply_markup=CANCEL)


# ---------- Список ----------

@router.callback_query(F.data.startswith("adm:acc:list:"))
async def cb_list(callback: CallbackQuery, session) -> None:
    await callback.answer()
    if not callback.message:
        return
    page = parse_int(callback.data.rsplit(":", 1)[-1]) or 1
    items, page, total_pages = await accounts_svc.get_page(session, page)
    if not items:
        await safe_edit(callback.message, "📋 Аккаунтов пока нет.", nav_kb("adm:acc:list", 1, 1, "adm:acc"))
        return
    lines = [f"📋 <b>Аккаунты</b> — всего {await accounts_svc.count_accounts(session)}\n"]
    lines.extend(f"#{a.id} — <code>{esc(a.login)}</code> — 📤 {a.issues_count}" for a in items)
    await safe_edit(
        callback.message,
        "\n".join(lines),
        nav_kb("adm:acc:list", page, total_pages, "adm:acc"),
    )


# ---------- Изменение ----------

@router.callback_query(F.data.startswith("adm:acc:editp:"))
async def cb_edit_pick(callback: CallbackQuery, session) -> None:
    await callback.answer()
    if not callback.message:
        return
    page = parse_int(callback.data.rsplit(":", 1)[-1]) or 1
    items, page, total_pages = await accounts_svc.get_page(session, page)
    if not items:
        await safe_edit(callback.message, "📋 Аккаунтов пока нет.", nav_kb("adm:acc:editp", 1, 1, "adm:acc"))
        return
    rows = [
        [InlineKeyboardButton(text=f"✏️ #{a.id} {short(a.login)}", callback_data=f"adm:acc:edit:{a.id}")]
        for a in items
    ]
    markup = InlineKeyboardMarkup(inline_keyboard=rows + nav_kb("adm:acc:editp", page, total_pages, "adm:acc").inline_keyboard)
    await safe_edit(callback.message, "✏️ Выберите аккаунт для изменения:", markup)


@router.callback_query(F.data.startswith("adm:acc:edit:"))
async def cb_edit(callback: CallbackQuery, session) -> None:
    await callback.answer()
    if not callback.message:
        return
    account_id = parse_int(callback.data.rsplit(":", 1)[-1])
    account = await accounts_svc.get_by_id(session, account_id) if account_id else None
    if account is None:
        await callback.answer("❌ Аккаунт не найден", show_alert=True)
        return
    await safe_edit(callback.message, account_card(account), edit_card_kb(account.id))


@router.callback_query(F.data.startswith("adm:acc:editf:"))
async def cb_edit_field(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    parts = callback.data.split(":")
    # adm:acc:editf:{id}:{field}
    account_id, field = parse_int(parts[3]), parts[4]
    if account_id is None or field not in accounts_svc.ALLOWED_FIELDS:
        return
    await state.set_state(EditSG.value)
    await state.update_data(acc_id=account_id, field=field)
    prompts = {
        "login": "🔑 Отправьте новый логин:",
        "password": "🔒 Отправьте новый пароль:",
        "games": "🎮 Отправьте игры через запятую (или «-», чтобы очистить):",
    }
    if callback.message:
        await safe_edit(callback.message, prompts[field], CANCEL)


@router.message(EditSG.value, F.text)
async def edit_value(message: Message, session, state: FSMContext) -> None:
    raw = message.text.strip()
    data = await state.get_data()
    await state.clear()
    field = data["field"]
    value = "" if field == "games" and raw in {"-", "—"} else (
        accounts_svc.normalize_games_csv(raw) if field == "games" else raw
    )
    ok = await accounts_svc.update_field(session, data["acc_id"], field, value)
    await session.commit()
    account = await accounts_svc.get_by_id(session, data["acc_id"])
    if not ok or account is None:
        await message.answer("❌ Не удалось сохранить. Аккаунт не найден.")
        return
    await message.answer(f"✅ Сохранено!\n\n{account_card(account)}", reply_markup=edit_card_kb(account.id))


# ---------- Удаление ----------

@router.callback_query(F.data.startswith("adm:acc:delp:"))
async def cb_del_pick(callback: CallbackQuery, session) -> None:
    await callback.answer()
    if not callback.message:
        return
    page = parse_int(callback.data.rsplit(":", 1)[-1]) or 1
    items, page, total_pages = await accounts_svc.get_page(session, page)
    if not items:
        await safe_edit(callback.message, "📋 Аккаунтов пока нет.", nav_kb("adm:acc:delp", 1, 1, "adm:acc"))
        return
    rows = [
        [InlineKeyboardButton(text=f"🗑 #{a.id} {short(a.login)}", callback_data=f"adm:acc:del:{a.id}")]
        for a in items
    ]
    markup = InlineKeyboardMarkup(inline_keyboard=rows + nav_kb("adm:acc:delp", page, total_pages, "adm:acc").inline_keyboard)
    await safe_edit(callback.message, "🗑 Выберите аккаунт для удаления:", markup)


@router.callback_query(F.data.startswith("adm:acc:del:"))
async def cb_del_confirm(callback: CallbackQuery, session) -> None:
    await callback.answer()
    if not callback.message:
        return
    account_id = parse_int(callback.data.rsplit(":", 1)[-1])
    account = await accounts_svc.get_by_id(session, account_id) if account_id else None
    if account is None:
        await callback.answer("❌ Аккаунт не найден", show_alert=True)
        return
    await safe_edit(
        callback.message,
        f"⚠️ <b>Удалить аккаунт #{account.id} ({esc(account.login)})?</b>\n\n"
        "Действие необратимо. История выдач при этом сохранится.",
        InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🗑 Да, удалить", callback_data=f"adm:acc:delok:{account.id}")],
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="adm:acc:delp:1")],
            ]
        ),
    )


@router.callback_query(F.data.startswith("adm:acc:delok:"))
async def cb_del_ok(callback: CallbackQuery, session) -> None:
    await callback.answer()
    if not callback.message:
        return
    account_id = parse_int(callback.data.rsplit(":", 1)[-1])
    deleted = await accounts_svc.delete_account(session, account_id) if account_id else False
    await session.commit()
    if deleted:
        await safe_edit(
            callback.message,
            f"✅ Аккаунт #{account_id} удалён.\nИстория выдач сохранена.",
            InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="⬅️ К аккаунтам", callback_data="adm:acc")]]
            ),
        )
    else:
        await callback.answer("❌ Аккаунт не найден", show_alert=True)


# ---------- Статистика ----------

@router.callback_query(F.data == "adm:acc:stats")
async def cb_stats(callback: CallbackQuery, session) -> None:
    await callback.answer()
    if not callback.message:
        return
    stats = await accounts_svc.accounts_stats(session)
    top = stats["top"]
    top_line = f"#{top.id} ({esc(top.login)}) — {top.issues_count} выдач" if top else "—"
    await safe_edit(
        callback.message,
        "📊 <b>Статистика аккаунтов</b>\n\n"
        f"Всего аккаунтов: <b>{stats['total']}</b>\n"
        f"Игр всего (позиций): <b>{stats['games_total']}</b>\n"
        f"Всего выдач: <b>{stats['issues_total']}</b>\n"
        f"Самый популярный: <b>{top_line}</b>\n"
        f"Последняя выдача: <b>{fmt_dt(stats['last_issue_at'])}</b>",
        InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="⬅️ К аккаунтам", callback_data="adm:acc")]]
        ),
    )


# ---------- История выдач аккаунтов ----------

@router.callback_query(F.data.startswith("adm:acc:hist:"))
async def cb_hist(callback: CallbackQuery, session) -> None:
    await callback.answer()
    if not callback.message:
        return
    page = parse_int(callback.data.rsplit(":", 1)[-1]) or 1
    items, page, total_pages = await history_svc.get_page(session, page)
    if not items:
        text = "📜 История выдач пуста."
    else:
        lines = ["📜 <b>История выдач</b>\n"]
        lines.extend(
            f"#{h.id} | {fmt_dt(h.created_at)}\n"
            f"👤 @{h.username or '—'} ({h.telegram_id}) → 🎮 #{h.account_id or '—'} ({esc(h.account_login or '—')}) | {h.type_label}"
            for h in items
        )
        text = "\n".join(lines)
    await safe_edit(
        callback.message,
        text,
        nav_kb("adm:acc:hist", page, total_pages, "adm:acc"),
    )
