"""Проверка живого бота: health-endpoint Render + getWebhookInfo Telegram."""
import asyncio
import sys
from pathlib import Path

import aiohttp

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bot.config import get_settings  # noqa: E402


async def main() -> None:
    tok = get_settings().bot_token
    base = "https://steam-gift-bot.onrender.com"
    async with aiohttp.ClientSession() as s:
        try:
            async with s.get(f"{base}/", timeout=aiohttp.ClientTimeout(total=90)) as r:
                print("health:", r.status, await r.text())
        except Exception as e:  # noqa: BLE001
            print("health error:", e)
        async with s.get(
            f"https://api.telegram.org/bot{tok}/getWebhookInfo",
            timeout=aiohttp.ClientTimeout(total=30),
        ) as r:
            d = await r.json()
            res = d.get("result", {})
            print("webhook url:", res.get("url"))
            print("last error:", res.get("last_error_message"))
            print("pending updates:", res.get("pending_update_count"))


asyncio.run(main())
