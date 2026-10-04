"""Работа со временем: единое UTC-хранилище + форматирование в таймзоне из .env."""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from bot.config import get_settings


def utcnow() -> datetime:
    """Наивный datetime в UTC (единый формат хранения для SQLite и PostgreSQL)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def fmt_dt(dt: datetime | None, with_time: bool = True) -> str:
    if dt is None:
        return "—"
    try:
        tz = ZoneInfo(get_settings().display_tz)
    except Exception:
        tz = timezone.utc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    local = dt.astimezone(tz)
    return local.strftime("%d.%m.%Y %H:%M") if with_time else local.strftime("%d.%m.%Y")


def fmt_today_bounds() -> tuple[datetime, datetime]:
    """Границы «сегодня» (UTC, наивные) для статистики."""
    now = utcnow()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, now
