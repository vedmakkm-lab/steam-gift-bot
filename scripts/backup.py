"""Резервное копирование базы данных.

SQLite — файл копируется в backups/.
PostgreSQL — pg_dump в custom-формат (нужен установленный pg_dump).

Использование: python scripts/backup.py
Cron-пример (каждый день в 04:00): 0 4 * * * cd /opt/steam-gift-bot && python scripts/backup.py
"""
from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.config import get_settings  # noqa: E402


def backup_sqlite(url: str, target_dir: Path) -> Path:
    # sqlite+aiosqlite:///./bot.db -> ./bot.db
    db_path = Path(url.split("///", 1)[-1])
    if not db_path.exists():
        raise FileNotFoundError(f"Файл БД не найден: {db_path}")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = target_dir / f"bot_{stamp}.db"
    shutil.copy2(db_path, target)
    return target


def backup_postgres(url: str, target_dir: Path) -> Path:
    parsed = urlparse(url.replace("postgresql+asyncpg://", "postgresql://"))
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = target_dir / f"bot_{stamp}.dump"
    if parsed.password:
        os.environ["PGPASSWORD"] = parsed.password
    cmd = [
        "pg_dump",
        f"--host={parsed.hostname or 'localhost'}",
        f"--port={parsed.port or 5432}",
        f"--username={parsed.username or 'postgres'}",
        "--format=custom",
        "--file", str(target),
        parsed.path.lstrip("/"),
    ]
    subprocess.run(cmd, check=True)
    return target


async def main() -> None:
    settings = get_settings()
    target_dir = Path("backups")
    target_dir.mkdir(exist_ok=True)
    url = settings.database_url
    if url.startswith("sqlite"):
        path = backup_sqlite(url, target_dir)
    else:
        path = backup_postgres(url, target_dir)
    print(f"✅ Бэкап создан: {path}")


if __name__ == "__main__":
    asyncio.run(main())
