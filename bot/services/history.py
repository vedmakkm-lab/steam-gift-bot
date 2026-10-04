"""Сервис истории выдач. История никогда не удаляется автоматически."""
from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import IssueHistory
from bot.utils.timefmt import utcnow

logger = logging.getLogger(__name__)


async def get_page(
    session: AsyncSession, page: int, per_page: int = 10
) -> tuple[list[IssueHistory], int, int]:
    total = (await session.execute(select(func.count(IssueHistory.id)))).scalar_one()
    total_pages = max(1, -(-total // per_page))
    page = min(max(1, page), total_pages)
    res = await session.execute(
        select(IssueHistory)
        .order_by(IssueHistory.created_at.desc(), IssueHistory.id.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    return list(res.scalars().all()), page, total_pages


async def count_for_user(session: AsyncSession, telegram_id: int) -> int:
    res = await session.execute(
        select(func.count(IssueHistory.id)).where(IssueHistory.telegram_id == telegram_id)
    )
    return res.scalar_one()


async def recent_for_user(
    session: AsyncSession, telegram_id: int, limit: int = 5
) -> list[IssueHistory]:
    res = await session.execute(
        select(IssueHistory)
        .where(IssueHistory.telegram_id == telegram_id)
        .order_by(IssueHistory.created_at.desc(), IssueHistory.id.desc())
        .limit(limit)
    )
    return list(res.scalars().all())


async def issues_stats(session: AsyncSession) -> dict:
    """Выдачи: всего, сегодня, за неделю, за месяц."""
    total = (await session.execute(select(func.count(IssueHistory.id)))).scalar_one()
    now = utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = now - timedelta(days=7)
    month_start = now - timedelta(days=30)

    async def count_since(bound) -> int:
        return (
            await session.execute(
                select(func.count(IssueHistory.id)).where(IssueHistory.created_at >= bound)
            )
        ).scalar_one()

    return {
        "total": total,
        "today": await count_since(today_start),
        "week": await count_since(week_start),
        "month": await count_since(month_start),
    }
