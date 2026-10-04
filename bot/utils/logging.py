"""Настройка логирования: консоль + ротация файлов."""
from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

from bot.config import get_settings


def setup_logging() -> None:
    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console = logging.StreamHandler()
    console.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(console)

    # Файловые логи — если файловая система позволяет писать (на части
    # бесплатных хостингов контейнер read-only, тогда остаётся консоль).
    try:
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            log_dir / "bot.log",
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setFormatter(fmt)
        root.addHandler(file_handler)
    except OSError:
        pass

    # Слишком болтливые библиотеки — на уровень WARNING
    for noisy in ("aiogram.event", "aiosqlite", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
