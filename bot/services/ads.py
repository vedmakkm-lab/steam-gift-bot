"""Сервис рекламных блоков."""
from __future__ import annotations

import logging
import random

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import Ad

logger = logging.getLogger(__name__)


async def get_all(session: AsyncSession) -> list[Ad]:
    res = await session.execute(select(Ad).order_by(Ad.id))
    return list(res.scalars().all())


async def get_active(session: AsyncSession) -> list[Ad]:
    res = await session.execute(select(Ad).where(Ad.is_active.is_(True)))
    return list(res.scalars().all())


async def get_random_active(session: AsyncSession) -> Ad | None:
    ads = await get_active(session)
    return random.choice(ads) if ads else None


async def get_by_id(session: AsyncSession, ad_id: int) -> Ad | None:
    res = await session.execute(select(Ad).where(Ad.id == ad_id))
    return res.scalar_one_or_none()


async def create_ad(session: AsyncSession, text: str, button_text: str | None, url: str | None) -> Ad:
    ad = Ad(text=text.strip(), button_text=button_text, url=url, is_active=True)
    session.add(ad)
    await session.flush()
    logger.info("Создан рекламный блок #%s", ad.id)
    return ad


async def toggle_active(session: AsyncSession, ad_id: int) -> None:
    ad = await get_by_id(session, ad_id)
    if ad is not None:
        ad.is_active = not ad.is_active


async def delete_ad(session: AsyncSession, ad_id: int) -> bool:
    ad = await get_by_id(session, ad_id)
    if ad is None:
        return False
    await session.delete(ad)
    logger.info("Удалён рекламный блок #%s", ad_id)
    return True
