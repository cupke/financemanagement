"""Pydantic-схемы транзакции для запросов и ответов API."""
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


  # Жёсткое перечисление — Pydantic вернёт 422 при любом другом значении kind.
TransactionKind = Literal["income", "expense", "transfer"]


class TransactionUpdate(BaseModel):
        """Тело запроса PATCH /transactions/{id}.

        Сознательное ограничение MVP: PATCH правит ТОЛЬКО поля, не влияющие
        на балансы счетов — category_id, occurred_at, note. Изменение суммы,
        счёта, типа или счёта-получателя — через DELETE + POST новой операции
        (см. docstring модуля app.api.v1.transactions). Это исключает целый
        класс багов «рассинхрон баланса и истории».

        Все поля опциональны. Семантика:
        - поле НЕ передано в JSON   → не обновляем (старое значение остаётся);
        - поле передано как null    → обнуляем (например, снять категорию);
        - поле передано со значением → обновляем.

        Различение «не передано» и «передано null» — через model_fields_set
        в эндпоинте. Pydantic по умолчанию не различает эти случаи в значении
        атрибута (и там, и там получится None).
        """
        category_id: int | None = None
        occurred_at: datetime | None = None
        note: str | None = Field(default=None, max_length=500)

class TransactionCreate(BaseModel):
      """Тело запроса POST /transactions.

      Бизнес-инварианты, которые проверяет model_validator:
      - amount > 0 (через Field(gt=0));
      - для перевода: transfer_account_id обязателен, category_id запрещён,
        transfer_account_id != account_id;
      - для income/expense: transfer_account_id запрещён.

      Эти же инварианты дублируются на уровне БД CHECK-констрейнтами —
      Pydantic даёт понятный 422, БД защищает от багов в коде.
      """
      kind: TransactionKind
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
          description="Счёт-получатель для перевода. Обязателен только для kind='transfer'.",
      )
      occurred_at: datetime = Field(
          ...,
          description="Когда операция фактически произошла (ISO 8601).",
      )
      note: str | None = Field(default=None, max_length=500)

      @model_validator(mode="after")
      def _check_shape(self) -> "TransactionCreate":
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
          return self


class TransactionRead(BaseModel):
      """Что отдаём в ответе API."""
      id: int
      owner_id: int
      account_id: int
      kind: TransactionKind
      amount: Decimal
      currency_code: str
      category_id: int | None
      transfer_account_id: int | None
      occurred_at: datetime
      note: str | None
      created_at: datetime
      updated_at: datetime

      model_config = ConfigDict(from_attributes=True)