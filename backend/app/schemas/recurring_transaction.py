"""Pydantic-схемы правила повторяющейся операции."""
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Те же жёсткие перечисления, что и в модели/транзакциях.
RecurringKind = Literal["income", "expense", "transfer"]
RecurrenceFrequency = Literal["daily", "weekly", "monthly", "yearly"]


class RecurringTransactionCreate(BaseModel):
    """Тело POST /recurring-transactions.

    Инварианты (дублируют CHECK на БД и логику Transaction):
    - amount > 0, interval >= 1;
    - для transfer: transfer_account_id обязателен, category_id запрещён,
      transfer_account_id != account_id;
    - для income/expense: transfer_account_id запрещён;
    - end_at, если задан, не раньше start_at.
    """
    name: str = Field(..., min_length=1, max_length=100)
    kind: RecurringKind
    account_id: int
    amount: Decimal = Field(..., gt=0, description="Положительная сумма")
    currency_code: str | None = Field(
        default=None,
        min_length=3,
        max_length=3,
        description="Код валюты ISO 4217. Если не задан — берётся из счёта.",
    )
    category_id: int | None = Field(
        default=None,
        description="Категория. Для перевода обязательно null.",
    )
    transfer_account_id: int | None = Field(
        default=None,
        description="Счёт-получатель для перевода. Только для kind='transfer'.",
    )
    note: str | None = Field(default=None, max_length=500)
    frequency: RecurrenceFrequency
    interval: int = Field(
        default=1, ge=1, description="Каждые N периодов (1 = каждый)."
    )
    start_at: datetime = Field(
        ..., description="Дата/время первой операции (ISO 8601)."
    )
    end_at: datetime | None = Field(
        default=None, description="Дата окончания. null = бессрочно."
    )

    @model_validator(mode="after")
    def _check_shape(self) -> "RecurringTransactionCreate":
        if self.kind == "transfer":
            if self.transfer_account_id is None:
                raise ValueError("Перевод требует transfer_account_id")
            if self.category_id is not None:
                raise ValueError("Перевод не может иметь категорию")
            if self.transfer_account_id == self.account_id:
                raise ValueError(
                    "Источник и получатель перевода должны различаться"
                )
        else:
            if self.transfer_account_id is not None:
                raise ValueError(
                    "transfer_account_id допустим только для kind='transfer'"
                )
        if self.end_at is not None and self.end_at < self.start_at:
            raise ValueError("Дата окончания не может быть раньше даты начала")
        return self


class RecurringTransactionUpdate(BaseModel):
    """Тело PATCH /recurring-transactions/{id}.

    Правим только «безопасные» для движка поля: имя, сумму, заметку,
    частоту/интервал, дату окончания и флаг активности. Менять тип, счета или
    категорию запрещаем — это по сути «другое правило»; для такого пользователь
    создаёт новое (тот же приём, что в PATCH транзакции). Поля опциональны;
    обновляются только переданные (model_fields_set в роутере).
    """
    name: str | None = Field(default=None, min_length=1, max_length=100)
    amount: Decimal | None = Field(default=None, gt=0)
    note: str | None = Field(default=None, max_length=500)
    frequency: RecurrenceFrequency | None = None
    interval: int | None = Field(default=None, ge=1)
    end_at: datetime | None = None
    is_active: bool | None = None


class RecurringTransactionRead(BaseModel):
    """Что отдаём в ответе API."""
    id: int
    owner_id: int
    name: str
    kind: RecurringKind
    account_id: int
    amount: Decimal
    currency_code: str
    category_id: int | None
    transfer_account_id: int | None
    note: str | None
    frequency: RecurrenceFrequency
    interval: int
    start_at: datetime
    end_at: datetime | None
    next_run_at: datetime
    last_run_at: datetime | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RunResult(BaseModel):
    """Итог прогона до-генерации POST /recurring-transactions/run."""
    created: int = Field(description="Сколько операций сгенерировано")
    rules_processed: int = Field(description="Сколько правил было назревших")
    deactivated: int = Field(
        description="Сколько правил завершилось (перешагнули дату окончания)"
    )
