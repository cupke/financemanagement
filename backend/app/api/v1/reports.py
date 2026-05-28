"""Роутер /reports: агрегированные данные для страницы отчётов и графиков.

Эндпоинт /overview отдаёт всё под страницу одним запросом (BFF-паттерн):
  - summary           — сводка-цифры за период (доход/расход/разница/средний расход);
  - points            — по «корзинам» времени доход/расход/баланс (столбцы и линия);
  - expense_by_category / income_by_category — структура расходов и доходов (кольца);
  - capital_by_account — текущий баланс по счетам (кольцо «где лежат деньги»).

Период задаётся диапазоном дат from_date..to_date; гранулярность «корзин»
(день/неделя/месяц) подбирается автоматически. Опциональный account_id — фильтр
по одному счёту.

Валюта отчёта: в режиме одного счёта — валюта этого счёта (USD-карта → суммы в $);
в режиме «все счета» — рубли (иначе разновалютные счета не сложить на графике).
Поле currency в ответе говорит фронту, в чём считать. Переводы в другой валюте
пересчитываются в валюту отчёта по курсу ЦБ.
"""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models.account import Account
from app.db.models.category import Category
from app.db.models.exchange_rate import ExchangeRate
from app.db.models.transaction import Transaction
from app.db.models.user import User
from app.db.session import get_session


router = APIRouter(prefix="/reports", tags=["reports"])

_MONTH_SHORT = [
    "", "янв", "фев", "мар", "апр", "май", "июн",
    "июл", "авг", "сен", "окт", "ноя", "дек",
]

_DAY_MAX = 45    # до 45 дней — по дням
_WEEK_MAX = 186  # до ~6 месяцев — по неделям, дальше — по месяцам


class BucketPoint(BaseModel):
    label: str = Field(..., description="Подпись корзины, напр. «5 май» или «май 2025»")
    income: Decimal
    expense: Decimal
    net: Decimal = Field(..., description="Доход минус расход за корзину")
    balance: Decimal = Field(..., description="Баланс на конец корзины (с учётом переводов)")


class CategorySlice(BaseModel):
    category_id: int
    category_name: str
    amount: Decimal


class AccountCapital(BaseModel):
    account_id: int
    account_name: str
    balance: Decimal


class ReportsSummary(BaseModel):
    total_income: Decimal
    total_expense: Decimal
    net: Decimal = Field(..., description="Доход минус расход за период")
    avg_expense_per_bucket: Decimal = Field(
        ..., description="Средний расход на одну корзину (день/неделю/месяц — см. granularity)"
    )


class ReportsOverview(BaseModel):
    from_date: date
    to_date: date
    account_id: int | None = Field(None, description="None — все счета")
    currency: str = Field(..., description="Валюта всех сумм в ответе (напр. RUB, USD)")
    granularity: str = Field(..., description="day | week | month")
    summary: ReportsSummary
    points: list[BucketPoint]
    expense_by_category: list[CategorySlice]
    income_by_category: list[CategorySlice]
    capital_by_account: list[AccountCapital]


@router.get(
    "/overview",
    response_model=ReportsOverview,
    summary="Данные для графиков отчётов за произвольный период",
)
async def get_overview(
    from_date: date | None = Query(None, description="Начало периода (YYYY-MM-DD)"),
    to_date: date | None = Query(None, description="Конец периода (YYYY-MM-DD), включительно"),
    account_id: int | None = Query(None, description="Фильтр по счёту; не указан — все"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ReportsOverview:
    today = datetime.now(timezone.utc).date()
    if to_date is None:
        to_date = today
    if from_date is None:
        from_date = to_date - timedelta(days=182)  # ~6 месяцев по умолчанию
    if from_date > to_date:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "from_date позже to_date")

    span = (to_date - from_date).days

    # --- Гранулярность и «корзины» времени ---------------------------------
    if span <= _DAY_MAX:
        granularity, step = "day", 1
    elif span <= _WEEK_MAX:
        granularity, step = "week", 7
    else:
        granularity, step = "month", 0

    labels: list[str] = []
    if granularity in ("day", "week"):
        n_buckets = span // step + 1
        starts = [from_date + timedelta(days=i * step) for i in range(n_buckets)]
        labels = [f"{d.day} {_MONTH_SHORT[d.month]}" for d in starts]

        def to_idx(when: date) -> int | None:
            if when < from_date or when > to_date:
                return None
            i = (when - from_date).days // step
            return i if 0 <= i < n_buckets else None
    else:
        months_list: list[tuple[int, int]] = []
        yy, mm = from_date.year, from_date.month
        while (yy, mm) <= (to_date.year, to_date.month):
            months_list.append((yy, mm))
            mm += 1
            if mm == 13:
                mm, yy = 1, yy + 1
        n_buckets = len(months_list)
        labels = [f"{_MONTH_SHORT[m]} {y}" for (y, m) in months_list]
        month_index = {(y, m): i for i, (y, m) in enumerate(months_list)}

        def to_idx(when: date) -> int | None:
            return month_index.get((when.year, when.month))

    range_start = datetime(from_date.year, from_date.month, from_date.day, tzinfo=timezone.utc)
    range_end_excl = (
        datetime(to_date.year, to_date.month, to_date.day, tzinfo=timezone.utc)
        + timedelta(days=1)
    )

    # 1. Счета в области отчёта.
    acc_stmt = select(Account).where(Account.owner_id == current_user.id)
    if account_id is not None:
        acc_stmt = acc_stmt.where(Account.id == account_id)
    accounts = list((await session.scalars(acc_stmt)).all())
    if account_id is not None and not accounts:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Счёт не найден")
    scope_ids = {a.id for a in accounts}

    # Валюта отчёта: один счёт — его валюта; все счета — рубли.
    display_currency = accounts[0].currency_code.upper() if account_id is not None else "RUB"

    # 2. Курсы (RUB за единицу валюты) + конверсия в валюту отчёта.
    rate_cache: dict[tuple[str, date], Decimal] = {}

    async def rate_of(currency: str, when: date) -> Decimal:
        currency = currency.upper()
        if currency == "RUB":
            return Decimal("1")
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
        return rate_cache[key]

    async def convert(amount: Decimal, from_currency: str, when: date) -> Decimal:
        """Сумму из from_currency — в валюту отчёта по курсу на дату when."""
        from_currency = from_currency.upper()
        if from_currency == display_currency:
            return amount
        in_rub = amount * await rate_of(from_currency, when)
        if display_currency == "RUB":
            return in_rub
        drate = await rate_of(display_currency, when)
        return Decimal("0") if drate == 0 else in_rub / drate

    # 3. Базовый капитал области + текущие балансы по счетам.
    baseline = Decimal("0")
    capital_by_account: list[AccountCapital] = []
    for a in accounts:
        baseline += await convert(a.opening_balance, a.currency_code, a.opening_date.date())
        capital_by_account.append(
            AccountCapital(
                account_id=a.id,
                account_name=a.name,
                balance=(await convert(a.balance, a.currency_code, today)).quantize(Decimal("0.01")),
            )
        )

    # 4. Доходы/расходы за период (столбцы, категории, сводка).
    inc_exp_stmt = (
        select(
            Transaction.kind,
            Transaction.amount,
            Transaction.currency_code,
            Transaction.occurred_at,
            Transaction.category_id,
        )
        .where(Transaction.owner_id == current_user.id)
        .where(Transaction.kind.in_(("income", "expense")))
        .where(Transaction.occurred_at >= range_start)
        .where(Transaction.occurred_at < range_end_excl)
    )
    if account_id is not None:
        inc_exp_stmt = inc_exp_stmt.where(Transaction.account_id == account_id)
    inc_exp_rows = (await session.execute(inc_exp_stmt)).all()

    income_by_bucket = [Decimal("0")] * n_buckets
    expense_by_bucket = [Decimal("0")] * n_buckets
    expense_by_cat: dict[int, Decimal] = {}
    income_by_cat: dict[int, Decimal] = {}

    for kind, amount, currency, occurred_at, category_id in inc_exp_rows:
        idx = to_idx(occurred_at.date())
        if idx is None:
            continue
        val = await convert(amount, currency, occurred_at.date())
        if kind == "income":
            income_by_bucket[idx] += val
            if category_id is not None:
                income_by_cat[category_id] = income_by_cat.get(category_id, Decimal("0")) + val
        else:
            expense_by_bucket[idx] += val
            if category_id is not None:
                expense_by_cat[category_id] = expense_by_cat.get(category_id, Decimal("0")) + val

    # 5. Линия реального баланса: все операции (включая переводы) до конца периода.
    #    Перевод двигает источник (-) и получателя (+).
    bal_stmt = select(
        Transaction.kind,
        Transaction.amount,
        Transaction.currency_code,
        Transaction.occurred_at,
        Transaction.account_id,
        Transaction.transfer_account_id,
    ).where(Transaction.owner_id == current_user.id)
    if account_id is not None:
        bal_stmt = bal_stmt.where(
            or_(
                Transaction.account_id == account_id,
                Transaction.transfer_account_id == account_id,
            )
        )
    bal_rows = (await session.execute(bal_stmt)).all()

    pre_range = Decimal("0")
    delta_by_bucket = [Decimal("0")] * n_buckets
    for kind, amount, currency, occurred_at, acc_id, transfer_acc_id in bal_rows:
        val = await convert(amount, currency, occurred_at.date())
        delta = Decimal("0")
        if acc_id in scope_ids:
            if kind == "income":
                delta += val
            elif kind == "expense":
                delta -= val
            elif kind == "transfer":
                delta -= val
        if kind == "transfer" and transfer_acc_id in scope_ids:
            delta += val
        if delta == 0:
            continue
        if occurred_at < range_start:
            pre_range += delta
        elif occurred_at < range_end_excl:
            idx = to_idx(occurred_at.date())
            if idx is not None:
                delta_by_bucket[idx] += delta

    # 6. Собираем ряд корзин.
    points: list[BucketPoint] = []
    running = baseline + pre_range
    total_income = Decimal("0")
    total_expense = Decimal("0")
    for i in range(n_buckets):
        income = income_by_bucket[i].quantize(Decimal("0.01"))
        expense = expense_by_bucket[i].quantize(Decimal("0.01"))
        total_income += income
        total_expense += expense
        running = running + delta_by_bucket[i]
        points.append(
            BucketPoint(
                label=labels[i],
                income=income,
                expense=expense,
                net=(income - expense).quantize(Decimal("0.01")),
                balance=running.quantize(Decimal("0.01")),
            )
        )

    # 7. Категории — имена + сортировка по убыванию.
    async def build_slices(totals: dict[int, Decimal]) -> list[CategorySlice]:
        if not totals:
            return []
        ids = list(totals.keys())
        rows = (
            await session.execute(
                select(Category.id, Category.name).where(Category.id.in_(ids))
            )
        ).all()
        names = {cid: name for cid, name in rows}
        return [
            CategorySlice(
                category_id=cid,
                category_name=names.get(cid, "—"),
                amount=totals[cid].quantize(Decimal("0.01")),
            )
            for cid in sorted(ids, key=lambda c: -totals[c])
        ]

    expense_slices = await build_slices(expense_by_cat)
    income_slices = await build_slices(income_by_cat)

    total_income = total_income.quantize(Decimal("0.01"))
    total_expense = total_expense.quantize(Decimal("0.01"))
    # Средний расход на одну корзину (день/неделю/месяц — по granularity). Так
    # цифра честная для любого периода, а не «врёт в месяц» на коротком окне.
    avg_expense = (total_expense / Decimal(n_buckets)).quantize(Decimal("0.01"))

    return ReportsOverview(
        from_date=from_date,
        to_date=to_date,
        account_id=account_id,
        currency=display_currency,
        granularity=granularity,
        summary=ReportsSummary(
            total_income=total_income,
            total_expense=total_expense,
            net=(total_income - total_expense).quantize(Decimal("0.01")),
            avg_expense_per_bucket=avg_expense,
        ),
        points=points,
        expense_by_category=expense_slices,
        income_by_category=income_slices,
        capital_by_account=capital_by_account,
    )
