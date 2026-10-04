"""Смена видимости репозитория на публичную через API (токен с Administration)."""
import asyncio
import sys
from pathlib import Path

import aiohttp

LINES = (Path(__file__).resolve().parent.parent / ".gh_token").read_text(encoding="utf-8").split()
TOKEN2 = LINES[-1].strip()
HEADERS = {
    "Authorization": f"Bearer {TOKEN2}",
    "User-Agent": "deploy",
    "Accept": "application/vnd.github+json",
}


async def main() -> None:
    async with aiohttp.ClientSession() as s:
        async with s.request(
            "PATCH",
            "https://api.github.com/repos/vedmakkm-lab/steam-gift-bot",
            headers=HEADERS,
            json={"private": False},
        ) as r:
            d = await r.json()
            print("status:", r.status, "| private:", d.get("private"), "| visibility:", d.get("visibility"))


asyncio.run(main())
