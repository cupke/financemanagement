"""Pydantic-схемы счёта для запросов и ответов API."""
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


  # Тип счёта — Literal обеспечивает строгую валидацию на уровне OpenAPI-схемы.
  # Значения совпадают с SAEnum в модели Account.
AccountKind = Literal["card", "cash", "savings", "credit", "e_wallet", "other"]


class AccountCreate(BaseModel):
      """Тело запроса POST /accounts.

      owner_id не передаётся клиентом — он берётся из JWT текущего пользователя.
      Это защита от IDOR: даже если злоумышленник попытается подложить чужой
      owner_id, он будет проигнорирован.

      opening_balance — то, что у пользователя на счёте НА opening_date
      (обычно «сейчас» = сегодня). Дальше любая транзакция с occurred_at
      >= opening_date наращивает или уменьшает balance. См. vkr/02_design.md.
      """
      name: str = Field(..., min_length=1, max_length=100, description="Название счёта")
      kind: AccountKind = Field(
          default="other",
          description="Тип счёта: card, cash, savings, credit, e_wallet, other.",
      )
      note: str | None = Field(
          default=None, max_length=500, description="Произвольная заметка пользователя"
      )
      opening_balance: Decimal = Field(
          default=Decimal("0"),
          description="Сколько на счету на opening_date (обычно — сейчас)",
      )
      opening_date: datetime | None = Field(
          default=None,
          description=(
              "Дата снимка opening_balance. Если null — будет проставлено NOW() "
              "в роутере. Обычно равно сегодняшнему моменту."
          ),
      )
      currency_code: str = Field(
          default="RUB",
          min_length=3,
          max_length=3,
          description="Код валюты ISO 4217 (RUB, USD, EUR, ...)",
      )


class AccountUpdate(BaseModel):
      """Тело запроса PATCH /accounts/{id}.

      Все поля опциональны: клиент шлёт только то, что хочет изменить.
      Для FastAPI это интерпретируется через `model_dump(exclude_unset=True)`
      в роутере — обновляем только заданные ключи.

      note может быть передан как `null` — это означает «очистить заметку».

      Поле `balance` УБРАНО намеренно: текущий баланс — производное от
      opening_balance + транзакций. Чтобы «выставить» баланс — поменять
      opening_balance (а при необходимости и opening_date). Тогда роутер
      пересчитает balance заново по формуле.
      """
      name: str | None = Field(default=None, min_length=1, max_length=100)
      kind: AccountKind | None = None
      note: str | None = Field(default=None, max_length=500)
      opening_balance: Decimal | None = None
      opening_date: datetime | None = None
      currency_code: str | None = Field(default=None, min_length=3, max_length=3)


class AccountRead(BaseModel):
      """Что отдаём в ответе API.

      balance — текущий (кешируемый); opening_balance + opening_date —
      «снимок», поверх которого считается balance. Клиент может показать
      пользователю и то, и другое (UX-помощь: «на opening_date было X»).
      """
      id: int
      owner_id: int
      name: str
      kind: AccountKind
      note: str | None
      opening_balance: Decimal
      opening_date: datetime
      balance: Decimal
      currency_code: str
      created_at: datetime
      updated_at: datetime

      model_config = ConfigDict(from_attributes=True)