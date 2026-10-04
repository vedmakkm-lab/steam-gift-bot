"""Конфигурация бота. Все секреты берутся из переменных окружения / файла .env."""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


def _parse_int_list(raw: str) -> list[int]:
    values: list[int] = []
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            values.append(int(part))
        except ValueError:
            continue
    return values


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    bot_token: str = ""
    database_url: str = "sqlite+aiosqlite:///./bot.db"
    admin_ids: str = ""
    display_tz: str = "UTC"
    kaspi_number: str = "7 708 130 1674"
    donation_presets: str = "25,50,100,250,500"
    log_level: str = "INFO"
    # Порт mini-HTTP-сервера health-check (нужен для HF Spaces / Render: 7860).
    # 0 = выключен (локальный запуск).
    health_port: int = 0

    # ===== Webhook-режим (для Render и других PaaS) =====
    # Полный URL вебхука, например https://steam-gift-bot.onrender.com/webhook.
    # Пусто = long polling (локальный запуск).
    webhook_url: str = ""
    # Порт HTTP-сервера (Render подставляет переменную PORT автоматически).
    port: int = 8080
    webhook_path: str = "/webhook"
    # Секрет для проверки заголовка X-Telegram-Bot-Api-Secret-Token.
    webhook_secret: str = ""
    # WEBHOOK_REGISTER=false — не вызывать set_webhook (для локальных тестов).
    webhook_register: bool = True

    @property
    def admin_id_list(self) -> list[int]:
        return _parse_int_list(self.admin_ids)

    @property
    def donation_preset_list(self) -> list[int]:
        values = [v for v in _parse_int_list(self.donation_presets) if v > 0]
        return sorted(set(values))


@lru_cache
def get_settings() -> Settings:
    return Settings()
