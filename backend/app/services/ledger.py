"""Единая логика проводки сумм по балансам счетов.

Извлечено из app.api.v1.transactions, чтобы и обычные операции (роутер
/transactions), и движок повторяющихся операций (роутер
/recurring-transactions) применяли изменения баланса ОДИНАКОВО — через
один источник истины, без копипасты (принципы DRY и Single Responsibility).

Модель «opening_balance + движения» (см. vkr/02_design.md): транзакция
влияет на balance счёта ТОЛЬКО если её occurred_at >= account.opening_date.
Транзакции «до opening_date» сохраняются в истории, но баланс не двигают —
их эффект уже зашит в opening_balance.
"""
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.account import Account


def ensure_aware_utc(dt: datetime) -> datetime:
    """Если datetime naive — считаем его UTC (так же интерпретирует Postgres
    при INSERT в TIMESTAMPTZ-колонку).

    Mantine 9 присылает naive ISO-строки ("2026-04-16T17:08:00", без Z и без
    offset). Pydantic парсит их в naive datetime, а колонки в БД — TIMESTAMPTZ
    (SQLAlchemy отдаёт их aware). Прямое сравнение naive < aware в Python даёт
    TypeError. Приведение naive к UTC-aware совпадает с реальной семантикой
    хранения в Postgres.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def signed_delta_for_source(kind: str, amount: Decimal) -> Decimal:
    """Знаковое изменение баланса счёта-источника при СОЗДАНИИ транзакции.

    income → +amount (деньги пришли).
    expense → -amount (деньги ушли).
    transfer → -amount (на источнике уменьшается; счёт-получатель
               обновляется отдельным вызовом в роутере).

    При DELETE применяется противоположный знак (см. delete_transaction).
    """
    if kind == "income":
        return amount
    return -amount


async def apply_signed_delta_to_account(
    account: Account,
    delta: Decimal,
    occurred_at: datetime,
    session: AsyncSession,
) -> None:
    """Применить delta к account.balance, только если occurred_at >= opening_date.

    UPDATE через session.execute (а не присваивание в Python) атомарен на
    уровне строки в Postgres — это защищает от lost update при двух
    параллельных запросах к одному счёту.
    """
    if ensure_aware_utc(occurred_at) < account.opening_date:
        return
    await session.execute(
        update(Account)
        .where(Account.id == account.id)
        .values(balance=Account.balance + delta)
    )
