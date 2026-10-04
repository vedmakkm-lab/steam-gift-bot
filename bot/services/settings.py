"""Сервис настроек бота (key-value в таблице bot_settings)."""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import get_settings
from bot.database.models import BotSetting

logger = logging.getLogger(__name__)

KEY_DONATION_PRESETS = "donation_presets"


async def get_value(session: AsyncSession, key: str) -> str | None:
    res = await session.execute(select(BotSetting).where(BotSetting.key == key))
    row = res.scalar_one_or_none()
    return row.value if row else None


async def set_value(session: AsyncSession, key: str, value: str) -> None:
    res = await session.execute(select(BotSetting).where(BotSetting.key == key))
    row = res.scalar_one_or_none()
    if row is None:
        session.add(BotSetting(key=key, value=value))
    else:
        row.value = value


async def get_donation_presets(session: AsyncSession) -> list[int]:
    """Размеры пожертвований; если не настроены — берутся из .env и сохраняются."""
    raw = await get_value(session, KEY_DONATION_PRESETS)
    if raw is None:
        raw = ",".join(str(v) for v in get_settings().donation_preset_list)
        await set_value(session, KEY_DONATION_PRESETS, raw)
    values: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit() and int(part) > 0:
            values.append(int(part))
    return sorted(set(values)) or [25, 50, 100, 250, 500]


async def set_donation_presets(session: AsyncSession, values: list[int]) -> None:
    clean = sorted({v for v in values if v > 0})
    await set_value(session, KEY_DONATION_PRESETS, ",".join(str(v) for v in clean))
    logger.info("Настроены суммы пожертвований: %s", clean)
