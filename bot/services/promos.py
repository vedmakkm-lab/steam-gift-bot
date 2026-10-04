"""Сервис промокодов.

Награда: дополнительные выдачи Steam-аккаунта (reward_type='extra_claims').
Защита:
  * уникальный индекс (promo_id, telegram_id) — один пользователь один раз;
  * атомарный UPDATE со счётчиком активаций — лимит не будет превышен при гонке.
"""
from __future__ import annotations

import logging
import random
import string
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import Promo, PromoUse, User
from bot.utils.timefmt import utcnow

logger = logging.getLogger(__name__)

REASON_NOT_FOUND = "not_found"
REASON_INACTIVE = "inactive"
REASON_EXPIRED = "expired"
REASON_MAX_REACHED = "max_reached"
REASON_ALREADY_USED = "already_used"
REASON_OK = "ok"

_ALPHABET = string.ascii_uppercase + string.digits


def normalize_code(code: str) -> str:
    return code.strip().upper()


def generate_code(length: int = 8) -> str:
    return "".join(random.choices(_ALPHABET, k=length))


async def get_by_id(session: AsyncSession, promo_id: int) -> Promo | None:
    res = await session.execute(select(Promo).where(Promo.id == promo_id))
    return res.scalar_one_or_none()


async def get_by_code(session: AsyncSession, code: str) -> Promo | None:
    res = await session.execute(select(Promo).where(Promo.code == normalize_code(code)))
    return res.scalar_one_or_none()


async def get_all(session: AsyncSession) -> list[Promo]:
    res = await session.execute(select(Promo).order_by(Promo.id.desc()))
    return list(res.scalars().all())


async def create_promo(
    session: AsyncSession,
    code: str,
    amount: int,
    max_activations: int | None,
    days: int | None,
) -> Promo:
    promo = Promo(
        code=normalize_code(code),
        reward_type="extra_claims",
        reward_amount=amount,
        max_activations=max_activations if max_activations and max_activations > 0 else None,
        expires_at=utcnow() + timedelta(days=days) if days and days > 0 else None,
        is_active=True,
    )
    session.add(promo)
    await session.flush()
    logger.info(
        "Создан промокод %s (+%s выдач, лимит %s, срок %s дн.)",
        promo.code, amount, max_activations, days,
    )
    return promo


async def toggle_active(session: AsyncSession, promo_id: int) -> None:
    promo = await get_by_id(session, promo_id)
    if promo is not None:
        promo.is_active = not promo.is_active


async def delete_promo(session: AsyncSession, promo_id: int) -> bool:
    promo = await get_by_id(session, promo_id)
    if promo is None:
        return False
    await session.delete(promo)
    logger.info("Удалён промокод %s", promo.code)
    return True


async def activate(
    session: AsyncSession, user: User, code: str
) -> tuple[bool, str, int]:
    """Активация промокода. Возвращает (успех, причина, начислено_выдач).

    ВАЖНО: коммит выполняет вызывающий код; при IntegrityError (гонка двух
    параллельных активаций одним пользователем) нужно откатить и сообщить
    об уже использованном промокоде.
    """
    code = normalize_code(code)
    if not code:
        return False, REASON_NOT_FOUND, 0

    promo = await get_by_code(session, code)
    if promo is None:
        return False, REASON_NOT_FOUND, 0
    if not promo.is_active:
        return False, REASON_INACTIVE, 0
    now = utcnow()
    if promo.expires_at is not None and now > promo.expires_at:
        return False, REASON_EXPIRED, 0

    # Уже использовал этот промокод?
    res = await session.execute(
        select(PromoUse.id).where(
            PromoUse.promo_id == promo.id, PromoUse.telegram_id == user.telegram_id
        )
    )
    if res.first() is not None:
        return False, REASON_ALREADY_USED, 0

    # Атомарно занять слот активации (лимит не будет превышен при гонке).
    res = await session.execute(
        update(Promo)
        .where(
            Promo.id == promo.id,
            (Promo.max_activations.is_(None)) | (Promo.activations_count < Promo.max_activations),
        )
        .values(activations_count=Promo.activations_count + 1)
    )
    if not res.rowcount:
        return False, REASON_MAX_REACHED, 0

    if promo.reward_type == "extra_claims":
        user.extra_claims += promo.reward_amount
    else:
        logger.warning("Неизвестный тип награды промокода: %s", promo.reward_type)

    session.add(PromoUse(promo_id=promo.id, telegram_id=user.telegram_id, created_at=now))
    logger.info(
        "Промокод %s активирован пользователем %s (+%s выдач)",
        promo.code, user.telegram_id, promo.reward_amount,
    )
    return True, REASON_OK, promo.reward_amount
