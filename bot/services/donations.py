"""Сервис пожертвований (Telegram Stars)."""
from __future__ import annotations

import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import Payment
from bot.utils.timefmt import utcnow

logger = logging.getLogger(__name__)


async def record_payment(
    session: AsyncSession,
    telegram_id: int,
    username: str | None,
    stars: int,
    charge_id: str,
    payload: str | None,
) -> Payment | None:
    """Записать платёж. Возвращает None, если платёж уже записан (повторная доставка)."""
    existing = await session.execute(
        select(Payment).where(Payment.charge_id == charge_id)
    )
    if existing.scalar_one_or_none() is not None:
        logger.warning("Повторная запись платежа %s — игнорирую", charge_id)
        return None
    payment = Payment(
        telegram_id=telegram_id,
        username=username,
        stars=stars,
        charge_id=charge_id,
        payload=payload,
    )
    session.add(payment)
    await session.flush()
    logger.info("Платёж: user=%s stars=%s charge=%s", telegram_id, stars, charge_id)
    return payment


async def get_recent(session: AsyncSession, limit: int = 10) -> list[Payment]:
    res = await session.execute(
        select(Payment).order_by(Payment.created_at.desc()).limit(limit)
    )
    return list(res.scalars().all())


async def donations_stats(session: AsyncSession) -> dict:
    stars_total = (await session.execute(select(func.coalesce(func.sum(Payment.stars), 0)))).scalar_one()
    count = (await session.execute(select(func.count(Payment.id)))).scalar_one()
    today_start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_stars = (
        await session.execute(
            select(func.coalesce(func.sum(Payment.stars), 0)).where(Payment.created_at >= today_start)
        )
    ).scalar_one()
    today_count = (
        await session.execute(
            select(func.count(Payment.id)).where(Payment.created_at >= today_start)
        )
    ).scalar_one()
    return {
        "stars_total": stars_total,
        "count": count,
        "today_stars": today_stars,
        "today_count": today_count,
    }
