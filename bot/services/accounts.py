"""Сервис Steam-аккаунтов.

Steam-аккаунты ОБЩИЕ: выдача не удаляет и не помечает их — меняются только
счётчики статистики (issues_count / last_issue_at). Удаление — только
явное действие администратора.
"""
from __future__ import annotations

import logging

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import IssueHistory, SteamAccount
from bot.utils.timefmt import utcnow

logger = logging.getLogger(__name__)

ALLOWED_FIELDS = {"login", "password", "games"}


def normalize_games_csv(raw: str) -> str:
    """'Game 1, Game 2' -> многострочная строка для хранения."""
    games = [g.strip() for g in raw.split(",")]
    return "\n".join(g for g in games if g)


async def has_any_account(session: AsyncSession) -> bool:
    res = await session.execute(select(SteamAccount.id).limit(1))
    return res.first() is not None


async def count_accounts(session: AsyncSession) -> int:
    return (await session.execute(select(func.count(SteamAccount.id)))).scalar_one()


async def get_random_account(session: AsyncSession) -> SteamAccount | None:
    """Случайный аккаунт. Аккаунты общие — ничего не фильтруем и не помечаем."""
    res = await session.execute(select(SteamAccount).order_by(func.random()).limit(1))
    return res.scalar_one_or_none()


async def get_by_id(session: AsyncSession, account_id: int) -> SteamAccount | None:
    res = await session.execute(select(SteamAccount).where(SteamAccount.id == account_id))
    return res.scalar_one_or_none()


async def create_account(session: AsyncSession, login: str, password: str, games: str) -> SteamAccount:
    account = SteamAccount(login=login.strip(), password=password.strip(), games=games)
    session.add(account)
    await session.flush()
    logger.info("Добавлен аккаунт #%s (%s)", account.id, account.login)
    return account


async def bulk_create_accounts(
    session: AsyncSession, items: list[tuple[str, str, str]]
) -> tuple[int, int]:
    """Массовое добавление: [(login, password, games)]. Каждый аккаунт — отдельная запись.

    Дубликат — совпадение ПАРЫ логин+пароль (регистр логина не учитывается,
    как в Steam). Один логин с разными паролями добавляется отдельными
    записями. Возвращает (добавлено, пропущено_дубликатов).
    """
    if not items:
        return 0, 0
    logins_lower = [login.lower() for login, _, _ in items]
    res = await session.execute(
        select(SteamAccount.login, SteamAccount.password).where(
            func.lower(SteamAccount.login).in_(logins_lower)
        )
    )
    existing = {(login.lower(), password) for login, password in res.all()}

    added = 0
    skipped = 0
    seen: set[tuple[str, str]] = set()
    for login, password, games in items:
        key = (login.lower(), password)
        if key in existing or key in seen:
            skipped += 1
            continue
        seen.add(key)
        session.add(
            SteamAccount(login=login, password=password, games=games)
        )
        added += 1
    await session.flush()
    logger.info("Массовая загрузка: добавлено %s, пропущено дубликатов %s", added, skipped)
    return added, skipped


async def get_page(
    session: AsyncSession, page: int, per_page: int = 8
) -> tuple[list[SteamAccount], int, int]:
    total = await count_accounts(session)
    total_pages = max(1, -(-total // per_page))
    page = min(max(1, page), total_pages)
    res = await session.execute(
        select(SteamAccount)
        .order_by(SteamAccount.id)
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    return list(res.scalars().all()), page, total_pages


async def update_field(session: AsyncSession, account_id: int, field: str, value: str) -> bool:
    if field not in ALLOWED_FIELDS:
        return False
    res = await session.execute(
        update(SteamAccount).where(SteamAccount.id == account_id).values({field: value.strip()})
    )
    return bool(res.rowcount)


async def delete_account(session: AsyncSession, account_id: int) -> bool:
    """Удаление ТОЛЬКО по действию администратора. История выдач сохраняется
    (в issue_history остаётся snapshot логина, account_id обнуляется через SET NULL)."""
    res = await session.execute(delete(SteamAccount).where(SteamAccount.id == account_id))
    logger.info("Админ удалил аккаунт #%s", account_id)
    return bool(res.rowcount)


async def accounts_stats(session: AsyncSession) -> dict:
    total = await count_accounts(session)
    games_rows = (await session.execute(select(SteamAccount.games))).scalars().all()
    games_total = sum(len([g for g in row.splitlines() if g.strip()]) for row in games_rows)
    issues_total = (await session.execute(select(func.count(IssueHistory.id)))).scalar_one()

    top = (
        await session.execute(
            select(SteamAccount)
            .where(SteamAccount.issues_count > 0)
            .order_by(SteamAccount.issues_count.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    last_issue_at = (
        await session.execute(select(func.max(SteamAccount.last_issue_at)))
    ).scalar_one_or_none()

    return {
        "total": total,
        "games_total": games_total,
        "issues_total": issues_total,
        "top": top,
        "last_issue_at": last_issue_at,
    }
