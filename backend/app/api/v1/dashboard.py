"""Роутер /dashboard: агрегированная сводка для главной страницы.

Один эндпоинт возвращает три виджета сразу — чтобы фронт делал ровно
один HTTP-запрос вместо трёх (общий капитал, расходы за месяц, топ-3
категорий). Это типовой паттерн «BFF endpoint» — данные «под форму».
"""
from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models.account import Account
from app.db.models.category import Category
from app.db.models.exchange_rate import ExchangeRate
from app.db.models.transaction import Transaction
from app.db.models.user import User
from app.db.session import get_session


router = APIRouter(prefix="/dashboard", tags=["dashboard"])


class CategorySpending(BaseModel):
    category_id: int
    category_name: str
    spent_rub: Decimal = Field(..., description="Потрачено в RUB за текущий месяц")


class DashboardSummary(BaseModel):
    total_capital_rub: Decimal = Field(
        ..., description="Сумма балансов всех счетов в RUB по курсу ЦБ"
    )
    accounts_count: int
    spent_this_month_rub: Decimal = Field(
        ..., description="Все расходы за текущий месяц в RUB"
    )
    transactions_this_month: int
    top_categories: list[CategorySpending] = Field(
        ..., description="Топ-3 категории расходов за текущий месяц"
    )


@router.get(
    "/summary",
    response_model=DashboardSummary,
    summary="Сводка для главной страницы",
)
async def get_summary(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> DashboardSummary:
    now = datetime.now(timezone.utc)
    month_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)

    # 1. Все счета пользователя — для общего капитала.
    accounts = list(
        (
            await session.scalars(
                select(Account).where(Account.owner_id == current_user.id)
            )
        ).all()
    )

    # 2. Кеш курсов на сегодня (по уникальным валютам счетов и транзакций).
    rate_cache: dict[tuple[str, date], Decimal] = {}

    async def to_rub(amount: Decimal, currency: str, when: date) -> Decimal:
        currency = currency.upper()
        if currency == "RUB":
            return amount
        key = (currency, when)
        if key not in rate_cache:
            rate = await session.scalar(
                select(ExchangeRate.vunit_rate)
                .where(ExchangeRate.char_code == currency)
                .where(ExchangeRate.rate_date <= when)
                .order_by(ExchangeRate.rate_date.desc())
                .limit(1)
            )
            rate_cache[key] = rate or Decimal("0")
        return amount * rate_cache[key]

    total_capital = Decimal("0")
    today = now.date()
    for acc in accounts:
        total_capital += await to_rub(acc.balance, acc.currency_code, today)
    total_capital = total_capital.quantize(Decimal("0.01"))

    # 3. Расходы за текущий месяц.
    expenses = (
        await session.execute(
            select(
                Transaction.amount,
                Transaction.currency_code,
                Transaction.occurred_at,
                Transaction.category_id,
            )
            .where(Transaction.owner_id == current_user.id)
            .where(Transaction.kind == "expense")
            .where(Transaction.occurred_at >= month_start)
        )
    ).all()

    spent_total = Decimal("0")
    spent_by_category: dict[int, Decimal] = {}
    for amount, currency, occurred_at, category_id in expenses:
        in_rub = await to_rub(amount, currency, occurred_at.date())
        spent_total += in_rub
        if category_id is not None:
            spent_by_category[category_id] = (
                spent_by_category.get(category_id, Decimal("0")) + in_rub
            )
    spent_total = spent_total.quantize(Decimal("0.01"))

    # 4. Топ-3 категории.
    top_ids = sorted(spent_by_category.keys(), key=lambda cid: -spent_by_category[cid])[:3]
    top_categories: list[CategorySpending] = []
    if top_ids:
        name_rows = (
            await session.execute(
                select(Category.id, Category.name).where(Category.id.in_(top_ids))
            )
        ).all()
        name_by_id = {cid: name for cid, name in name_rows}
        for cid in top_ids:
            top_categories.append(
                CategorySpending(
                    category_id=cid,
                    category_name=name_by_id.get(cid, "—"),
                    spent_rub=spent_by_category[cid].quantize(Decimal("0.01")),
                )
            )

    return DashboardSummary(
        total_capital_rub=total_capital,
        accounts_count=len(accounts),
        spent_this_month_rub=spent_total,
        transactions_this_month=len(expenses),
        top_categories=top_categories,
    )
