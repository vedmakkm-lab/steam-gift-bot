"""SQLAlchemy-модели (2.0 style, async).

Все даты хранятся в UTC (наивные datetime). Датавремени по умолчанию
ставится на стороне Python — это даёт одинаковое поведение SQLite и PostgreSQL.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from bot.utils.timefmt import utcnow


class Base(DeclarativeBase):
    pass


class User(Base):
    """Пользователь бота.

    ВАЖНО: ограничение «1 бесплатная выдача» относится к пользователю,
    а НЕ к Steam-аккаунту.
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(255))
    free_claim_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    extra_claims: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    extra_claims_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    last_issue_at: Mapped[datetime | None] = mapped_column(DateTime)

    @property
    def extra_left(self) -> int:
        return max(0, self.extra_claims - self.extra_claims_used)

    def has_right(self) -> bool:
        return not self.free_claim_used or self.extra_left > 0


class SteamAccount(Base):
    """Steam-аккаунт. Общий: НЕ удаляется и не меняет статус после выдачи."""

    __tablename__ = "steam_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    login: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    password: Mapped[str] = mapped_column(String(255), nullable=False)
    games: Mapped[str] = mapped_column(Text, nullable=False, default="")
    added_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    issues_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_issue_at: Mapped[datetime | None] = mapped_column(DateTime)

    @property
    def games_list(self) -> list[str]:
        return [g.strip() for g in self.games.splitlines() if g.strip()]


class IssueHistory(Base):
    """История выдач. Никогда не удаляется автоматически."""

    __tablename__ = "issue_history"
    __table_args__ = (
        Index("ix_issue_history_created_at", "created_at"),
    )

    ISSUE_TYPE_LABELS = {
        "free": "free",
        "promo": "promo",
        "admin": "admin/reset",
    }

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    username: Mapped[str | None] = mapped_column(String(255))
    account_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("steam_accounts.id", ondelete="SET NULL")
    )
    account_login: Mapped[str | None] = mapped_column(String(255))
    issue_type: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    @property
    def type_label(self) -> str:
        return self.ISSUE_TYPE_LABELS.get(self.issue_type, self.issue_type)


class Promo(Base):
    """Промокод. reward_type сейчас поддерживает 'extra_claims'; схема расширяемая."""

    __tablename__ = "promos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    reward_type: Mapped[str] = mapped_column(String(32), nullable=False, default="extra_claims")
    reward_amount: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    max_activations: Mapped[int | None] = mapped_column(Integer)
    activations_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class PromoUse(Base):
    """Активация промокода пользователем. Защита от повторной активации."""

    __tablename__ = "promo_uses"
    __table_args__ = (
        UniqueConstraint("promo_id", "telegram_id", name="uq_promo_uses_promo_user"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    promo_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("promos.id", ondelete="CASCADE"), nullable=False
    )
    telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class Channel(Base):
    """Обязательный канал для подписки."""

    __tablename__ = "channels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    chat_id: Mapped[int | None] = mapped_column(BigInteger)
    username: Mapped[str | None] = mapped_column(String(64))
    url: Mapped[str] = mapped_column(String(512), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    @property
    def target(self) -> str | int:
        """Цель для get_chat_member: числовой id или @username."""
        if self.chat_id:
            return self.chat_id
        if self.username:
            return f"@{self.username.lstrip('@')}"
        return self.url


class Payment(Base):
    """Платёж Telegram Stars (пожертвование)."""

    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    username: Mapped[str | None] = mapped_column(String(255))
    stars: Mapped[int] = mapped_column(Integer, nullable=False)
    charge_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    payload: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class Ad(Base):
    """Рекламный блок (текст + опциональная inline-кнопка со ссылкой)."""

    __tablename__ = "ads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    button_text: Mapped[str | None] = mapped_column(String(64))
    url: Mapped[str | None] = mapped_column(String(512))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class BotSetting(Base):
    """Key-value настройки бота (например, размеры пожертвований)."""

    __tablename__ = "bot_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
