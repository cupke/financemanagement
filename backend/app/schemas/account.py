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
      """
      name: str = Field(..., min_length=1, max_length=100, description="Название счёта")
      kind: AccountKind = Field(
          default="other",
          description="Тип счёта: card, cash, savings, credit, e_wallet, other.",
      )
      note: str | None = Field(
          default=None, max_length=500, description="Произвольная заметка пользователя"
      )
      balance: Decimal = Field(default=Decimal("0"), description="Начальный баланс")
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
      """
      name: str | None = Field(default=None, min_length=1, max_length=100)
      kind: AccountKind | None = None
      note: str | None = Field(default=None, max_length=500)
      balance: Decimal | None = None
      currency_code: str | None = Field(default=None, min_length=3, max_length=3)


class AccountRead(BaseModel):
      """Что отдаём в ответе API."""
      id: int
      owner_id: int
      name: str
      kind: AccountKind
      note: str | None
      balance: Decimal
      currency_code: str
      created_at: datetime
      updated_at: datetime

      model_config = ConfigDict(from_attributes=True)