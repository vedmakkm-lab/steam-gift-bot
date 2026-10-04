"""Сервис обязательных каналов и проверки подписки."""
from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramAPIError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import Channel

logger = logging.getLogger(__name__)

_SUBSCRIBED_STATUSES = {
    ChatMemberStatus.MEMBER,
    ChatMemberStatus.ADMINISTRATOR,
    ChatMemberStatus.CREATOR,
}


async def get_all_channels(session: AsyncSession) -> list[Channel]:
    res = await session.execute(select(Channel).order_by(Channel.id))
    return list(res.scalars().all())


async def get_active_channels(session: AsyncSession) -> list[Channel]:
    res = await session.execute(
        select(Channel).where(Channel.is_active.is_(True)).order_by(Channel.id)
    )
    return list(res.scalars().all())


async def get_by_id(session: AsyncSession, channel_id: int) -> Channel | None:
    res = await session.execute(select(Channel).where(Channel.id == channel_id))
    return res.scalar_one_or_none()


async def add_channel(
    session: AsyncSession,
    title: str,
    chat_id: int | None,
    username: str | None,
    url: str,
) -> Channel:
    channel = Channel(title=title, chat_id=chat_id, username=username, url=url, is_active=True)
    session.add(channel)
    await session.flush()
    logger.info("Добавлен канал: %s (%s)", title, url)
    return channel


async def toggle_active(session: AsyncSession, channel_id: int) -> None:
    channel = await get_by_id(session, channel_id)
    if channel is not None:
        channel.is_active = not channel.is_active


async def delete_channel(session: AsyncSession, channel_id: int) -> bool:
    channel = await get_by_id(session, channel_id)
    if channel is None:
        return False
    await session.delete(channel)
    logger.info("Удалён канал: %s", channel.title)
    return True


async def get_not_subscribed(
    bot: Bot, channels: list[Channel], user_id: int
) -> list[Channel]:
    """Каналы, на которые пользователь НЕ подписан (или бот не смог проверить)."""
    not_subscribed: list[Channel] = []
    for channel in channels:
        try:
            member = await bot.get_chat_member(channel.target, user_id)
            is_member = member.status in _SUBSCRIBED_STATUSES or getattr(
                member, "is_member", True
            )
            if not is_member:
                not_subscribed.append(channel)
        except TelegramAPIError as e:
            # Канал недоступен боту (например, бот не администратор) —
            # безопаснее считать, что подписки нет, и показать канал.
            logger.warning(
                "Не удалось проверить подписку на %s (%s): %s",
                channel.title, channel.target, e,
            )
            not_subscribed.append(channel)
    return not_subscribed


async def check_channels(bot: Bot, channels: list[Channel]) -> list[str]:
    """Диагностика настроек: доступен ли канал и может ли бот проверять подписку."""
    report: list[str] = []
    for channel in channels:
        target = channel.target
        try:
            chat = await bot.get_chat(target)
            try:
                me_member = await bot.get_chat_member(chat.id, bot.id)
                ok = me_member.status in _SUBSCRIBED_STATUSES
            except TelegramAPIError:
                ok = False
            status_text = (
                "✅ бот может проверять подписку"
                if ok
                else "⚠️ бот НЕ администратор канала — проверка подписки работать не будет"
            )
            report.append(f"📢 {chat.title or target} — {status_text}")
        except TelegramAPIError as e:
            report.append(f"📢 {channel.title} — ❌ канал недоступен для бота ({e})")
    return report
