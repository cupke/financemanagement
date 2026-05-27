"""Pydantic-схемы бюджета для запросов и ответов API."""
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class BudgetCreate(BaseModel):
    """Тело запроса POST /budgets.

    period_year/period_month обязательны: бюджет всегда создаётся на конкретный
    месяц. Фронт передаёт месяц, который сейчас открыт на странице бюджетов.
    """
    category_id: int = Field(
        ...,
        description="ID категории. Должна принадлежать юзеру и иметь kind='expense'.",
    )
    amount: Decimal = Field(
        ...,
        gt=0,
        decimal_places=2,
        description="Месячный лимит в RUB. Должен быть > 0.",
    )
    period_year: int = Field(..., ge=2000, le=2100)
    period_month: int = Field(..., ge=1, le=12)


class BudgetUpdate(BaseModel):
    """Тело запроса PATCH /budgets/{id}.

    Категорию и период через PATCH менять не разрешаем — это эквивалентно
    созданию нового бюджета на другую категорию или другой месяц.
    Безопаснее заставить клиента сделать DELETE + POST, чем поддерживать
    «миграцию лимита между категориями/месяцами».
    """
    amount: Decimal | None = Field(default=None, gt=0, decimal_places=2)


class BudgetRead(BaseModel):
    """Базовая форма бюджета (без вычисляемых полей)."""
    id: int
    owner_id: int
    category_id: int
    amount: Decimal
    period_year: int
    period_month: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# Статус расходования бюджета. Граничные значения совпадают с цветами
# прогресс-бара на фронте: зелёный < 70%, жёлтый 70-99%, красный >= 100%.
BudgetStatus = Literal["ok", "warning", "exceeded"]


class BudgetWithProgress(BudgetRead):
    """Бюджет с прогрессом за свой месяц.

    Считается на стороне сервера, чтобы фронт не делал N+1 запросов
    к /transactions для каждого бюджета. spent — потрачено в RUB
    с учётом конвертации валют по курсам ЦБ РФ.
    """
    spent: Decimal = Field(..., description="Потрачено в RUB за период бюджета")
    percent: float = Field(..., description="Процент использования: spent/amount*100")
    status: BudgetStatus = Field(..., description="ok / warning / exceeded")
    category_name: str = Field(..., description="Имя категории для отображения")
