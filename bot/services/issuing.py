"""Сервис выдачи аккаунтов — центральный сценарий бота.

Логика (в одной транзакции сессии):
  1. Атомарно списать право пользователя (free или promo);
  2. Выбрать случайный аккаунт;
  3. Если аккаунтов нет — откатить транзакцию (право возвращается пользователю);
  4. Записать выдачу в историю, обновить счётчики аккаунта;
  5. Зафиксировать.

Steam-аккаунт при этом НЕ удаляется и НЕ меняет статус — он остаётся общим
и может быть выдан повторно другим пользователям.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import IssueHistory, SteamAccount
from bot.services import accounts as accounts_svc
from bot.services import users as users_svc
from bot.utils.timefmt import utcnow

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class IssueResult:
    status: str  # "ok" | "no_rights" | "no_accounts"
    account: SteamAccount | None = None
    issue_type: str | None = None


async def issue_account(
    session: AsyncSession, telegram_id: int, username: str | None
) -> IssueResult:
    """Обычная выдача: бесплатная (1 раз) или за счёт дополнительных прав."""
    issue_type = await users_svc.consume_right(session, telegram_id)
    if issue_type is None:
        return IssueResult(status="no_rights")

    account = await accounts_svc.get_random_account(session)
    if account is None:
        # Нет аккаунтов — откатываем списание права, пользователь ничего не теряет.
        await session.rollback()
        return IssueResult(status="no_accounts")

    now = utcnow()
    account.issues_count += 1
    account.last_issue_at = now
    session.add(
        IssueHistory(
            telegram_id=telegram_id,
            username=username,
            account_id=account.id,
            account_login=account.login,
            issue_type=issue_type,
            created_at=now,
        )
    )
    await session.commit()
    logger.info(
        "Выдача [%s]: user=%s (@%s) -> account #%s (%s)",
        issue_type, telegram_id, username, account.id, account.login,
    )
    return IssueResult(status="ok", account=account, issue_type=issue_type)


async def force_issue(
    session: AsyncSession, telegram_id: int, username: str | None, issue_type: str = "admin"
) -> IssueResult:
    """Принудительная выдача администратором (без списания прав пользователя)."""
    account = await accounts_svc.get_random_account(session)
    if account is None:
        return IssueResult(status="no_accounts")

    now = utcnow()
    account.issues_count += 1
    account.last_issue_at = now
    session.add(
        IssueHistory(
            telegram_id=telegram_id,
            username=username,
            account_id=account.id,
            account_login=account.login,
            issue_type=issue_type,
            created_at=now,
        )
    )
    await session.commit()
    logger.info(
        "Выдача [%s]: user=%s (@%s) -> account #%s (%s)",
        issue_type, telegram_id, username, account.id, account.login,
    )
    return IssueResult(status="ok", account=account, issue_type=issue_type)
