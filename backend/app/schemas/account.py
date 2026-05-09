"""Pydantic-схемы счёта для запросов и ответов API."""
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class AccountCreate(BaseModel):
      """Тело запроса POST /accounts.

      owner_id не передаётся клиентом — он берётся из JWT текущего пользователя.
      Это защита от IDOR: даже если злоумышленник попытается подложить чужой
      owner_id, он будет проигнорирован.
      """
      name: str = Field(..., min_length=1, max_length=100, description="Название счёта")
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
      """
      name: str | None = Field(default=None, min_length=1, max_length=100)
      balance: Decimal | None = None
      currency_code: str | None = Field(default=None, min_length=3, max_length=3)


class AccountRead(BaseModel):
      """Что отдаём в ответе API. Содержит owner_id для прозрачности —
      клиент видит, что счёт точно его (полезно при отладке)."""
      id: int
      owner_id: int
      name: str
      balance: Decimal
      currency_code: str
      created_at: datetime
      updated_at: datetime

      model_config = ConfigDict(from_attributes=True)