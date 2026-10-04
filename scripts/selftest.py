"""Самопроверка ключевой логики бота на временной SQLite-базе.

Проверяет: выдачу, ограничение «1 бесплатная выдача», промокоды (лимит,
повторная активация), конкурентное списание прав, сброс выдач, сохранность
Steam-аккаунтов после выдач.

Запуск: python scripts/selftest.py
"""
from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete, select  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker  # noqa: E402

from bot.database.engine import build_engine  # noqa: E402
from bot.database.models import Base, IssueHistory, SteamAccount  # noqa: E402
from bot.services import accounts as accounts_svc  # noqa: E402
from bot.services import issuing  # noqa: E402
from bot.services import promos as promos_svc  # noqa: E402
from bot.services import users as users_svc  # noqa: E402

PASSED = 0
FAILED = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global PASSED, FAILED
    if condition:
        PASSED += 1
        print(f"  ✅ {name}")
    else:
        FAILED += 1
        print(f"  ❌ {name} {detail}")


async def run() -> int:
    tmp = tempfile.mkdtemp()
    # Используем боевой build_engine: WAL + busy_timeout (как в продакшене)
    engine = build_engine(f"sqlite+aiosqlite:///{tmp}/test.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(engine, expire_on_commit=False)

    async with sm() as s:
        # --- Подготовка: 3 аккаунта и пользователь ---
        for i in range(1, 4):
            await accounts_svc.create_account(s, f"acc{i}", f"pass{i}", f"Game {i}A\nGame {i}B")
        user = await users_svc.get_or_create_user(s, 1001, "tester")
        await s.commit()
        print("Подготовка (3 аккаунта, 1 пользователь)")

        # --- 1. Бесплатная выдача ---
        r1 = await issuing.issue_account(s, 1001, "tester")
        check("Бесплатная выдача успешна", r1.status == "ok" and r1.issue_type == "free")
        check("Аккаунт выдан со списком игр", bool(r1.account and r1.account.games_list))

        # --- 2. Повторная попытка без прав ---
        r2 = await issuing.issue_account(s, 1001, "tester")
        check("Повторная выдача отклонена", r2.status == "no_rights")

        # --- 3. Выдача не удаляет и не помечает аккаунт ---
        count = await accounts_svc.count_accounts(s)
        check("Все 3 аккаунта остались в базе", count == 3)
        all_accs = (await s.execute(select(SteamAccount))).scalars().all()
        check("Счётчик выдач аккаунта увеличился", sum(a.issues_count for a in all_accs) == 1)
        hist = (await s.execute(select(IssueHistory))).scalars().all()
        check("Выдача записана в историю", len(hist) == 1 and hist[0].issue_type == "free")

        # --- 4. Промокод: лимит активаций ---
        promo = await promos_svc.create_promo(s, "FREE5", amount=5, max_activations=1, days=None)
        await s.commit()
        ok, reason, granted = await promos_svc.activate(s, user, " free5 ")  # регистр и пробелы
        await s.commit()
        check("Промокод активирован (без учета регистра)", ok and reason == "ok" and granted == 5)
        fresh = await users_svc.get_by_telegram_id(s, 1001)
        check("extra_claims = 5", fresh.extra_claims == 5)

        ok2, reason2, _ = await promos_svc.activate(s, fresh, "FREE5")
        check("Повторная активация отклонена", not ok2 and reason2 == promos_svc.REASON_ALREADY_USED)

        user2 = await users_svc.get_or_create_user(s, 1002, "other")
        await s.commit()
        ok3, reason3, _ = await promos_svc.activate(s, user2, "FREE5")
        await s.commit()
        check("Лимит активаций исчерпан", not ok3 and reason3 == promos_svc.REASON_MAX_REACHED)
        p_fresh = await promos_svc.get_by_id(s, promo.id)
        check("Счётчик активаций = 1", p_fresh.activations_count == 1)

        # --- 5. Выдача через промокод ---
        r3 = await issuing.issue_account(s, 1001, "tester")
        check("Выдача по промокоду успешна", r3.status == "ok" and r3.issue_type == "promo")
        fresh = await users_svc.get_by_telegram_id(s, 1001)
        check("Списан 1 доп. выдача (осталось 4)", fresh.extra_claims_used == 1 and fresh.extra_left == 4)

        # --- 6. Конкурентные запросы: только extra=1, два параллельных списания ---
        # Сначала закрываем бесплатную выдачу пользователя 1002,
        # чтобы оставалось ровно одно право (extra=1).
        await users_svc.consume_right(s, 1002)  # -> "free"
        await users_svc.grant_extra_claims(s, 1002, 1)
        await s.commit()

        # Реалистичная гонка: вторая сессия ждёт освобождения блокировки
        # (busy_timeout), затем условный UPDATE переоценивает WHERE
        # по закоммиченным данным и возвращает 0 строк.
        async with sm() as s1, sm() as s2:
            r_a = await users_svc.consume_right(s1, 1002)
            task_b = asyncio.create_task(users_svc.consume_right(s2, 1002))
            await asyncio.sleep(0.1)  # s2 уже ждёт блокировку
            await s1.commit()         # короткая транзакция, как в боте
            r_b = await task_b
        results = sorted([x for x in (r_a, r_b) if x])
        check(
            "Параллельные запросы списали ровно одно право",
            results == ["promo"] and (r_a, r_b) == ("promo", None),
            f"получено: {r_a!r}, {r_b!r}",
        )
        u2 = await users_svc.get_by_telegram_id(s, 1002)
        check("extra_claims_used = 1 (без двойного списания)", u2.extra_claims_used == 1)

        # --- 7. Выдача при пустой базе: право не списывается ---
        await users_svc.grant_extra_claims(s, 1002, 1)
        await s.commit()
        await s.execute(delete(SteamAccount))
        await s.commit()
        r4 = await issuing.issue_account(s, 1002, "other")
        check("Нет аккаунтов -> no_accounts", r4.status == "no_accounts")
        u2 = await users_svc.get_by_telegram_id(s, 1002)
        check("Право не списано при no_accounts", u2.extra_claims_used == 1)

        # --- 8. Массовая загрузка и сброс выдач ---
        # acc1/acc2 были удалены ранее, поэтому все три строки новые;
        # третья строка — точный повтор второй (пара логин+пароль).
        added, skipped = await accounts_svc.bulk_create_accounts(
            s,
            [
                ("acc1", "p1", "G1"),
                ("acc2", "p2", ""),
                ("acc2", "p2", ""),
                ("ACC1", "p1", "G1"),  # тот же логин (регистр) и пароль — дубликат
            ],
        )
        await s.commit()
        check("Массовая загрузка: 2 добавлено, 2 дубликата пропущено", (added, skipped) == (2, 2))
        # Один логин с ДРУГИМ паролем — отдельный аккаунт, добавляется.
        added2, skipped2 = await accounts_svc.bulk_create_accounts(
            s, [("acc1", "new_password", "G9")]
        )
        await s.commit()
        check("Логин с другим паролем добавляется отдельным аккаунтом", (added2, skipped2) == (1, 0))
        affected = await users_svc.reset_all_free_claims(s)
        await s.commit()
        check("Сброс затронул пользователей", affected >= 2)
        r5 = await issuing.issue_account(s, 1001, "tester")
        check("После сброса бесплатная выдача снова доступна", r5.status == "ok" and r5.issue_type == "free")

        hist_count = len((await s.execute(select(IssueHistory))).scalars().all())
        # Выдачи: free (шаг 1) + promo (шаг 5) + free после сброса (шаг 8).
        # Шаг 6 списывал право через consume_right без выдачи — в историю не пишется.
        check("История выдач сохранилась и пополнилась", hist_count == 3)

        # --- 9. Парсер файла загрузки: оба формата ---
        from bot.handlers.admin.accounts import parse_bulk_text

        block_text = (
            "Логин: user1\n"
            "Пароль: pass1\n"
            "Игры: Game A, Game B, \\\n"
            "\n"
            "Логин: user2\n"
            "Пароль: pass2\n"
            "Игры: Не указано\n"
            "\n"
            "Логин: user3\n"
            "Пароль: pass3\n"
        )
        block_items, block_invalid = parse_bulk_text(block_text)
        check(
            "Блок-формат (Логин/Пароль/Игры) распознан",
            len(block_items) == 3 and not block_invalid,
            f"items={len(block_items)}, invalid={len(block_invalid)}",
        )
        check(
            "Игры из блока очищены (без '\\', 'Не указано' -> пусто)",
            block_items[0][2] == "Game A\nGame B" and block_items[1][2] == "" and block_items[2][2] == "",
            f"games={block_items[0][2]!r}",
        )
        line_items, line_invalid = parse_bulk_text("l:p | G1, G2\nbadline\n")
        check(
            "Построчный формат работает",
            len(line_items) == 1 and line_items[0][2] == "G1\nG2" and len(line_invalid) == 1,
        )

    await engine.dispose()
    print(f"\nИтог: {PASSED} прошло, {FAILED} упало")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
