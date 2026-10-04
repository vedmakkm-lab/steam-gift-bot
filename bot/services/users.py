"""Сервис пользователей.

Ключевая логика прав на получение:
  * 1 Telegram-пользователь = 1 бесплатная выдача (free_claim_used);
  * дополнительные выдачи — promo (extra_claims / extra_claims_used).

Списание прав выполнено атомарными UPDATE с условием: даже при параллельных
запросах у пользователя спишется не больше прав, чем у него есть.
"""
from __future__ import annotations

import logging

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import IssueHistory, PromoUse, User
from bot.utils.timefmt import utcnow

logger = logging.getLogger(__name__)


async def get_or_create_user(session: AsyncSession, telegram_id: int, username: str | None) -> User:
    res = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = res.scalar_one_or_none()
    if user is None:
        user = User(telegram_id=telegram_id, username=username)
        session.add(user)
        await session.flush()
        logger.info("Новый пользователь: %s (@%s)", telegram_id, username)
    elif user.username != username:
        user.username = username
    return user


async def get_by_telegram_id(session: AsyncSession, telegram_id: int) -> User | None:
    """Читает актуальное состояние из БД (populate_existing обновляет кэш сессии)."""
    res = await session.execute(
        select(User)
        .where(User.telegram_id == telegram_id)
        .execution_options(populate_existing=True)
    )
    return res.scalar_one_or_none()


async def consume_right(session: AsyncSession, telegram_id: int) -> str | None:
    """Атомарно списать право на выдачу. Возвращает 'free' | 'promo' | None.

    Сначала списывается бесплатная выдача, затем — дополнительные.
    Конкурентные запросы безопасны: условный UPDATE списывает не более
    одного права даже при гонке.
    """
    now = utcnow()
    res = await session.execute(
        update(User)
        .where(User.telegram_id == telegram_id, User.free_claim_used.is_(False))
        .values(free_claim_used=True, last_issue_at=now)
    )
    if res.rowcount:
        return "free"

    res = await session.execute(
        update(User)
        .where(User.telegram_id == telegram_id, User.extra_claims > User.extra_claims_used)
        .values(extra_claims_used=User.extra_claims_used + 1, last_issue_at=now)
    )
    if res.rowcount:
        return "promo"
    return None


async def reset_all_free_claims(session: AsyncSession) -> int:
    """Сброс free_claim_used у ВСЕХ пользователей. История не трогается."""
    res = await session.execute(
        update(User).where(User.free_claim_used.is_(True)).values(free_claim_used=False)
    )
    logger.info("Сброс бесплатных выдач: затронуто пользователей: %s", res.rowcount)
    return res.rowcount


async def reset_user_free_claim(session: AsyncSession, telegram_id: int) -> bool:
    res = await session.execute(
        update(User)
        .where(User.telegram_id == telegram_id, User.free_claim_used.is_(True))
        .values(free_claim_used=False)
    )
    return bool(res.rowcount)


async def grant_extra_claims(session: AsyncSession, telegram_id: int, amount: int) -> None:
    res = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = res.scalar_one_or_none()
    if user is None:
        return
    user.extra_claims += amount


async def users_stats(session: AsyncSession) -> dict:
    total = (await session.execute(select(func.count(User.id)))).scalar_one()
    free_used = (
        await session.execute(select(func.count(User.id)).where(User.free_claim_used.is_(True)))
    ).scalar_one()
    with_extra = (
        await session.execute(select(func.count(User.id)).where(User.extra_claims > 0))
    ).scalar_one()
    promo_activations = (await session.execute(select(func.count(PromoUse.id)))).scalar_one()
    new_today = (
        await session.execute(
            select(func.count(User.id)).where(
                User.created_at >= utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            )
        )
    ).scalar_one()
    return {
        "total": total,
        "free_used": free_used,
        "with_extra": with_extra,
        "promo_activations": promo_activations,
        "new_today": new_today,
    }
