"""Тест webhook-режима: поднимаем бота и шлём фейковое обновление Telegram."""
import asyncio
import json
import sys
import urllib.request

sys.path.insert(0, ".")

BASE = "http://127.0.0.1:8091"
SECRET = "testsecret"


def http(method: str, path: str, payload: dict | None = None) -> tuple[int, str]:
    req = urllib.request.Request(
        BASE + path,
        method=method,
        data=json.dumps(payload).encode() if payload else None,
        headers={"Content-Type": "application/json", "X-Telegram-Bot-Api-Secret-Token": SECRET},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


async def main() -> None:
    # 1. health
    status, body = await asyncio.to_thread(http, "GET", "/")
    print("GET / ->", status, body)
    assert status == 200 and body == "ok", "health failed"

    # 2. фейковый /start от пользователя 555
    update = {
        "update_id": 1,
        "message": {
            "message_id": 1,
            "date": 1759580000,
            "chat": {"id": 555, "type": "private", "first_name": "Tester"},
            "from": {"id": 555, "is_bot": False, "first_name": "Tester", "username": "tester"},
            "text": "/start",
            "entities": [{"offset": 0, "length": 6, "type": "bot_command"}],
        },
    }
    status, body = await asyncio.to_thread(http, "POST", "/webhook", update)
    print("POST /webhook ->", status, body)
    assert status == 200, "webhook failed"

    # 3. неверный секрет -> 403
    req = urllib.request.Request(
        BASE + "/webhook",
        method="POST",
        data=json.dumps(update).encode(),
        headers={"Content-Type": "application/json", "X-Telegram-Bot-Api-Secret-Token": "WRONG"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            code = r.status
    except urllib.error.HTTPError as e:
        code = e.code
    print("POST /webhook (wrong secret) ->", code)
    assert code == 403, "secret check failed"

    print("WEBHOOK_TEST_OK")


asyncio.run(main())
