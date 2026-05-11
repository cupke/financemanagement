"""Pydantic-схемы курсов валют ЦБ РФ для REST-ответов."""
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class RateRead(BaseModel):
      """Один курс в ответе API.

      Decimal в JSON сериализуется как строка — это правильное поведение для
      финансовых сумм (frontend сам решит, как форматировать; точность не
      теряется при передаче по сети, как было бы с float).
      """

      char_code: str = Field(..., description="Буквенный код ISO 4217, например USD")
      num_code: str = Field(..., description="Цифровой код ISO 4217, например 840")
      name: str = Field(..., description="Название валюты на русском")
      nominal: int = Field(..., description="За сколько единиц приводится курс")
      value: Decimal = Field(..., description="Курс за `nominal` единиц, рублей")
      vunit_rate: Decimal = Field(..., description="Курс за 1 единицу, рублей")
      rate_date: date = Field(..., description="Дата, на которую ЦБ установил курс")

      model_config = ConfigDict(from_attributes=True)


class RatesListResponse(BaseModel):
      """Обёртка над списком курсов: добавляет метаданные (дата + момент кеша)."""

      rate_date: date = Field(..., description="Дата ЦБ, на которую все курсы в списке")
      fetched_at: datetime = Field(..., description="Когда сервер последний раз скачивал курсы")
      items: list[RateRead] = Field(..., description="Курсы, отсортированы по char_code")