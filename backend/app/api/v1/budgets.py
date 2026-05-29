"""Роутер /budgets: лимиты расходов по категориям на конкретный месяц.

Каждый бюджет привязан к одной expense-категории и одному календарному
месяцу. Это даёт пользователю гибкость планирования сезонных расходов:
например, в августе бюджет «Развлечения» = 20 000 ₽ (отпуск), а в обычные
месяцы — 5 000 ₽; в декабре есть бюджет «Подарки», а в остальные месяцы
его нет вообще.

GET /budgets?year=&month= отдаёт бюджеты только за выбранный месяц с
прогрессом — потрачено в RUB, процент использования, статус (ok/warning/
exceeded). Расходы в иностранных валютах пересчитываются по курсу ЦБ РФ
на дату операции (см. _convert_to_rub ниже).

Иерархия категорий: бюджет на «Еду» учитывает траты во всех её
подкатегориях («Продукты», «Кафе», «Доставка»). Спускаемся по дереву
через BFS-обход в памяти по plain-списку категорий юзера.

Все эндпоинты требуют авторизации и фильтруют по owner_id (защита от
IDOR — OWASP A01). Тот же паттерн 404-вместо-403, что и в других роутерах.
"""
from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import and_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models.budget import Budget
from app.db.models.category import Category
from app.db.models.exchange_rate import ExchangeRate
from app.db.models.transaction import Transaction
from app.db.models.user import User
from app.db.session import get_session
from app.schemas.budget import (
    BudgetCreate,
    BudgetRead,
    BudgetUpdate,
    BudgetWithProgress,
)


router = APIRouter(prefix="/budgets", tags=["budgets"])


@router.post(
    "",
    response_model=BudgetRead,
    status_code=status.HTTP_201_CREATED,
    summary="Создать бюджет на категорию на конкретный месяц",
)
async def create_budget(
    payload: BudgetCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Budget:
    # Категория должна быть наша и расходная. 400 — это ошибка валидации
    # входа, не «ресурс не найден».
    category = await session.get(Category, payload.category_id)
    if category is None or category.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Категория не найдена",
        )
    if category.kind != "expense":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Бюджет можно установить только для расходной категории",
        )

    budget = Budget(
        owner_id=current_user.id,
        category_id=payload.category_id,
        amount=payload.amount,
        period_year=payload.period_year,
        period_month=payload.period_month,
    )
    session.add(budget)
    try:
        await session.commit()
    except IntegrityError:
        # UNIQUE (owner, category, year, month) — на эту категорию
        # в этом месяце уже есть бюджет.
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Бюджет для этой категории на выбранный месяц уже существует",
        ) from None
    await session.refresh(budget)
    return budget


@router.get(
    "",
    response_model=list[BudgetWithProgress],
    summary="Список бюджетов на конкретный месяц с прогрессом",
)
async def list_budgets(
    year: int | None = Query(
        default=None,
        ge=2000,
        le=2100,
        description="Год периода. По умолчанию — текущий.",
    ),
    month: int | None = Query(
        default=None,
        ge=1,
        le=12,
        description="Месяц периода (1-12). По умолчанию — текущий.",
    ),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[BudgetWithProgress]:
    """Бюджеты пользователя на указанный месяц с расчётом потраченного.

    Возвращаются только бюджеты с точно совпадающим (period_year, period_month).
    В прошлых месяцах виден ровно тот набор, что был там создан — никакого
    «задним числом» и никакого «протягивания вперёд».

    Прогресс считается на сервере, чтобы фронт не делал отдельный запрос
    к /transactions для каждого бюджета (N+1 на главной странице).
    """
    # Период по умолчанию — текущий месяц по UTC.
    now = datetime.now(timezone.utc)
    target_year = year if year is not None else now.year
    target_month = month if month is not None else now.month

    period_start, period_end = _month_bounds(target_year, target_month)

    # 1. Бюджеты юзера на этот месяц + их категории одним JOIN'ом.
    budgets_stmt = (
        select(Budget, Category)
        .join(Category, Category.id == Budget.category_id)
        .where(Budget.owner_id == current_user.id)
        .where(Budget.period_year == target_year)
        .where(Budget.period_month == target_month)
        .order_by(Budget.id)
    )
    rows = (await session.execute(budgets_stmt)).all()

    if not rows:
        return []

    # 2. Все expense-категории юзера для построения карты потомков.
    all_categories_stmt = (
        select(Category.id, Category.parent_id)
        .where(Category.owner_id == current_user.id)
        .where(Category.kind == "expense")
    )
    cat_pairs = (await session.execute(all_categories_stmt)).all()
    children: dict[int, list[int]] = {}
    for cid, pid in cat_pairs:
        if pid is not None:
            children.setdefault(pid, []).append(cid)

    # 3. Для каждого бюджета — считаем потрачено в RUB.
    rate_cache: dict[tuple[str, date], Decimal | None] = {}
    result: list[BudgetWithProgress] = []

    for budget, category in rows:
        descendant_ids = _collect_descendants(category.id, children)

        tx_stmt = select(
            Transaction.amount,
            Transaction.currency_code,
            Transaction.occurred_at,
        ).where(
            and_(
                Transaction.owner_id == current_user.id,
                Transaction.kind == "expense",
                Transaction.category_id.in_(descendant_ids),
                Transaction.occurred_at >= period_start,
                Transaction.occurred_at < period_end,
            )
        )
        txs = (await session.execute(tx_stmt)).all()

        spent_rub = Decimal("0")
        for amount, currency_code, occurred_at in txs:
            spent_rub += await _convert_to_rub(
                amount, currency_code, occurred_at, session, rate_cache
            )
        spent_rub = spent_rub.quantize(Decimal("0.01"))

        percent = float(spent_rub / budget.amount * 100) if budget.amount else 0.0
        if percent >= 100:
            status_label = "exceeded"
        elif percent >= 70:
            status_label = "warning"
        else:
            status_label = "ok"

        result.append(
            BudgetWithProgress(
                id=budget.id,
                owner_id=budget.owner_id,
                category_id=budget.category_id,
                amount=budget.amount,
                period_year=budget.period_year,
                period_month=budget.period_month,
                created_at=budget.created_at,
                updated_at=budget.updated_at,
                spent=spent_rub,
                percent=round(percent, 1),
                status=status_label,
                category_name=category.name,
            )
        )

    return result


@router.patch(
    "/{budget_id}",
    response_model=BudgetRead,
    summary="Обновить лимит бюджета",
)
async def update_budget(
    budget_id: int,
    payload: BudgetUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Budget:
    budget = await _get_owned_budget_or_404(budget_id, current_user, session)

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(budget, field, value)

    await session.commit()
    await session.refresh(budget)
    return budget


@router.delete(
    "/{budget_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить бюджет",
)
async def delete_budget(
    budget_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    budget = await _get_owned_budget_or_404(budget_id, current_user, session)
    await session.delete(budget)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ─── Внутренние хелперы ─────────────────────────────────────────────────


async def _get_owned_budget_or_404(
    budget_id: int,
    current_user: User,
    session: AsyncSession,
) -> Budget:
    """Тот же паттерн 404-вместо-403, что и в других роутерах:
    не утекаем информацию о существовании чужих ресурсов.
    """
    budget = await session.get(Budget, budget_id)
    if budget is None or budget.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Бюджет не найден",
        )
    return budget


def _month_bounds(year: int, month: int) -> tuple[datetime, datetime]:
    """Границы календарного месяца в UTC: [start, next_start).

    Half-open интервал (< вместо <=) — стандартный приём для диапазонов
    времени, исключающий «попадание» полуночи следующего месяца в текущий период.
    """
    start = datetime(year, month, 1, tzinfo=timezone.utc)
    if month == 12:
        next_start = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        next_start = datetime(year, month + 1, 1, tzinfo=timezone.utc)
    return start, next_start


def _collect_descendants(
    root_id: int, children: dict[int, list[int]]
) -> list[int]:
    """BFS-обход дерева категорий: root + все его потомки.

    Без рекурсии — на случай глубокой иерархии, чтобы не получить RecursionError.
    """
    result = [root_id]
    seen = {root_id}  # защита от циклов в дереве (на случай кривых данных в БД)
    queue: list[int] = [root_id]
    while queue:
        current = queue.pop(0)
        for child_id in children.get(current, []):
            if child_id in seen:
                continue
            seen.add(child_id)
            result.append(child_id)
            queue.append(child_id)
    return result


async def _convert_to_rub(
    amount: Decimal,
    currency_code: str,
    occurred_at: datetime,
    session: AsyncSession,
    rate_cache: dict[tuple[str, date], Decimal | None],
) -> Decimal:
    """Перевести сумму в RUB по курсу ЦБ РФ на дату операции.

    Алгоритм:
    - RUB → возвращаем как есть (курс 1:1, не дёргаем БД).
    - Другая валюта → ищем последний курс с rate_date <= occurred_at
      (пятничный курс действует все выходные).
    - Курса нет вообще → возвращаем 0. Альтернатива «бросить ошибку»
      сломала бы весь список бюджетов из-за одной экзотической транзакции.

    rate_cache живёт в рамках одного запроса: 20 покупок в USD за месяц
    дают всего 1-2 SQL-запроса к exchange_rates.
    """
    currency_code = currency_code.upper()
    if currency_code == "RUB":
        return amount

    occurred_date = occurred_at.date()
    cache_key = (currency_code, occurred_date)
    if cache_key in rate_cache:
        cached = rate_cache[cache_key]
        return amount * cached if cached is not None else Decimal("0")

    rate = await session.scalar(
        select(ExchangeRate.vunit_rate)
        .where(ExchangeRate.char_code == currency_code)
        .where(ExchangeRate.rate_date <= occurred_date)
        .order_by(ExchangeRate.rate_date.desc())
        .limit(1)
    )
    rate_cache[cache_key] = rate

    if rate is None:
        return Decimal("0")
    return amount * rate
