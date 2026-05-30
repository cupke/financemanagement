"""Регресс-тест на конкурентный POST /run (находка R1).

Два одновременных прогона движка повторяющихся операций ОДНОГО пользователя
не должны задваивать операции и баланс. Сериализацию обеспечивает
pg_advisory_xact_lock(owner_id) в run_due: второй прогон ждёт коммита первого,
затем перечитывает правила с уже сдвинутым next_run_at и создаёт 0 операций.

Тест PostgreSQL-специфичен: advisory-lock'ов в SQLite нет, поэтому на SQLite
он пропускается (там гонки в одном процессе и так не возникает).
"""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.api.v1.recurring_transactions import run_due
from app.db.models.account import Account
from app.db.models.recurring_transaction import RecurringTransaction
from app.db.models.transaction import Transaction
from app.db.models.user import User
from app.security import hash_password
from tests.conftest import TestSessionLocal, test_engine


async def test_concurrent_run_does_not_double_post() -> None:
    if test_engine.dialect.name != "postgresql":
        pytest.skip("Сериализация через pg_advisory_xact_lock — только PostgreSQL")

    # Пользователь + счёт (opening_date в прошлом, чтобы операции влияли на баланс)
    # + ежедневное правило со стартом 3 дня назад. Один /run создал бы 4 операции
    # (-3, -2, -1 день и сегодня), баланс уменьшился бы на 4×100 = 400.
    async with TestSessionLocal() as s:
        user = User(email="concurrency@example.com", password_hash=hash_password("x" * 10))
        s.add(user)
        await s.flush()
        account = Account(
            owner_id=user.id,
            name="Карта",
            opening_balance=0,
            opening_date=datetime(2020, 1, 1, tzinfo=timezone.utc),
            balance=0,
            currency_code="RUB",
        )
        s.add(account)
        await s.flush()
        start = datetime.now(timezone.utc) - timedelta(days=3)
        rule = RecurringTransaction(
            owner_id=user.id,
            name="Кофе",
            kind="expense",
            account_id=account.id,
            amount=100,
            currency_code="RUB",
            frequency="daily",
            interval=1,
            start_at=start,
            next_run_at=start,
            is_active=True,
        )
        s.add(rule)
        await s.commit()
        user_id = user.id
        account_id = account.id

    # Два независимых прогона «одновременно», каждый в своей сессии/транзакции.
    async with TestSessionLocal() as sa, TestSessionLocal() as sb:
        user_a = await sa.get(User, user_id)
        user_b = await sb.get(User, user_id)
        await asyncio.gather(run_due(user_a, sa), run_due(user_b, sb))

    # Без сериализации тут было бы 8 операций и баланс -800. С advisory-lock'ом —
    # ровно одна серия: 4 операции, баланс -400.
    async with TestSessionLocal() as s:
        tx_count = await s.scalar(
            select(func.count())
            .select_from(Transaction)
            .where(Transaction.owner_id == user_id)
        )
        account = await s.get(Account, account_id)

    assert tx_count == 4
    assert account.balance == -400
