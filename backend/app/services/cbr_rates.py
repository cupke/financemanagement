"""Сервис курсов валют ЦБ РФ.

  Что делает:
  1. По запросу даёт «актуальные курсы ЦБ» — из БД, если они там уже есть,
     иначе скачивает XML с cbr.ru, парсит, кладёт в БД, возвращает.
  2. Парсит фид https://www.cbr.ru/scripts/XML_daily.asp — открытый XML,
     обновляется один раз в рабочий день, не требует ключей.

  Архитектурный шаблон — cache-aside (Fowler, Patterns of EAA / GoF аналог Proxy):
      приложение само управляет кешем, обращаясь сначала к нему, а в случае
      промаха — к источнику, и сразу же дописывает результат в кеш.
  В разделе 3 ВКР это удобный конкретный пример паттерна.

  Поведение, на которое стоит обратить внимание:
  - ЦБ публикует курсы по будням после ~11:30 MSK. В выходные и праздники
    атрибут Date в XML равен последнему рабочему дню — это не баг, это правило ЦБ.
  - Кодировка фида — windows-1251. Если читать байты как UTF-8, кириллица
    ('Доллар США') превратится в кракозябры. Поэтому используем `response.content`
    (байты) + `ET.fromstring(...)`, а не `response.text`.
  - Значения в XML записаны через запятую («74,2963»). Переводим в точку
    перед `Decimal(...)`, иначе получим InvalidOperation.
  """
from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from decimal import Decimal

import httpx
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.exchange_rate import ExchangeRate


logger = logging.getLogger(__name__)


  # Официальный URL дневного фида ЦБ. Открытый, без авторизации.
CBR_DAILY_URL = "https://www.cbr.ru/scripts/XML_daily.asp"

  # Таймаут на запрос к ЦБ. 10 секунд — компромисс: сеть может тормозить,
  # но и блокировать API-запрос пользователя надолго мы не хотим.
CBR_TIMEOUT_SECONDS = 10.0


@dataclass(frozen=True)
class ParsedRate:
      """Один курс из XML-фида ЦБ — DTO до записи в БД."""
      char_code: str
      num_code: str
      name: str
      nominal: int
      value: Decimal
      vunit_rate: Decimal


@dataclass(frozen=True)
class ParsedFeed:
      """Результат разбора XML-фида: дата ЦБ + список курсов."""
      rate_date: date
      rates: tuple[ParsedRate, ...]


def _parse_cbr_decimal(raw: str) -> Decimal:
      """Перевод '74,2963' в Decimal('74.2963').

      Decimal обязателен (не float), иначе при сложении/умножении балансов
      появится «копеечная ошибка» — известная ловушка финансовых систем.
      """
      return Decimal(raw.replace(",", ".").strip())


def parse_cbr_xml(xml_bytes: bytes) -> ParsedFeed:
      """Разобрать байты ответа cbr.ru в структурированный ParsedFeed.

      Берём `bytes`, а не `str`, чтобы ElementTree сам прочитал заявленную в
      XML-декларации кодировку (windows-1251). Передавать декодированную
      строку — частая ошибка, ломающая кириллицу.
      """
      root = ET.fromstring(xml_bytes)
      date_attr = root.attrib.get("Date")
      if not date_attr:
          raise ValueError("В XML ЦБ нет атрибута Date у корневого ValCurs")
      # Формат ЦБ — DD.MM.YYYY.
      rate_date = datetime.strptime(date_attr, "%d.%m.%Y").date()

      parsed: list[ParsedRate] = []
      for valute in root.findall("Valute"):
          char_code = (valute.findtext("CharCode") or "").strip()
          num_code = (valute.findtext("NumCode") or "").strip()
          name = (valute.findtext("Name") or "").strip()
          nominal_raw = (valute.findtext("Nominal") or "").strip()
          value_raw = (valute.findtext("Value") or "").strip()
          # VunitRate появился в фиде ЦБ относительно недавно — в очень старых
          # ответах его может не быть; считаем сами как fallback.
          vunit_raw = (valute.findtext("VunitRate") or "").strip()

          if not (char_code and value_raw and nominal_raw):
              logger.warning("Пропуск Valute без обязательных полей: %s", valute.attrib)
              continue

          nominal = int(nominal_raw)
          value = _parse_cbr_decimal(value_raw)
          vunit_rate = (
              _parse_cbr_decimal(vunit_raw) if vunit_raw else (value / Decimal(nominal))
          )

          parsed.append(
              ParsedRate(
                  char_code=char_code,
                  num_code=num_code,
                  name=name,
                  nominal=nominal,
                  value=value,
                  vunit_rate=vunit_rate,
              )
          )

      if not parsed:
          raise ValueError("В XML ЦБ не нашлось ни одной валюты")

      return ParsedFeed(rate_date=rate_date, rates=tuple(parsed))


async def fetch_cbr_feed(client: httpx.AsyncClient | None = None) -> ParsedFeed:
      """Скачать и разобрать сегодняшний фид ЦБ."""
      own_client = client is None
      if own_client:
          client = httpx.AsyncClient(timeout=CBR_TIMEOUT_SECONDS)
      try:
          response = await client.get(CBR_DAILY_URL)
          response.raise_for_status()
          # Именно .content (bytes), не .text — см. docstring модуля.
          return parse_cbr_xml(response.content)
      finally:
          if own_client:
              await client.aclose()


async def _save_rates(session: AsyncSession, feed: ParsedFeed) -> None:
      """UPSERT всех курсов одним запросом.

      Используем PostgreSQL-специфичный INSERT ... ON CONFLICT DO UPDATE, чтобы:
      1. Не падать с IntegrityError, если эта дата уже в БД (повторный фетч).
      2. Перезаписать значение, если ЦБ выпустил корректировку.
      """
      if not feed.rates:
          return

      rows = [
          {
              "char_code": r.char_code,
              "num_code": r.num_code,
              "name": r.name,
              "nominal": r.nominal,
              "value": r.value,
              "vunit_rate": r.vunit_rate,
              "rate_date": feed.rate_date,
          }
          for r in feed.rates
      ]

      stmt = pg_insert(ExchangeRate).values(rows)
      stmt = stmt.on_conflict_do_update(
          constraint="uq_exchange_rates_code_date",
          set_={
              "num_code": stmt.excluded.num_code,
              "name": stmt.excluded.name,
              "nominal": stmt.excluded.nominal,
              "value": stmt.excluded.value,
              "vunit_rate": stmt.excluded.vunit_rate,
          },
      )
      await session.execute(stmt)
      await session.commit()


async def _load_rates(session: AsyncSession, on_date: date) -> list[ExchangeRate]:
      """Прочитать курсы за конкретную дату, отсортированные по char_code."""
      result = await session.execute(
          select(ExchangeRate)
          .where(ExchangeRate.rate_date == on_date)
          .order_by(ExchangeRate.char_code)
      )
      return list(result.scalars().all())


async def _load_latest_rates(session: AsyncSession) -> list[ExchangeRate]:
      """Самая поздняя дата, что вообще есть в БД, и все курсы на неё."""
      latest_date = await session.scalar(
          select(ExchangeRate.rate_date).order_by(ExchangeRate.rate_date.desc()).limit(1)
      )
      if latest_date is None:
          return []
      return await _load_rates(session, on_date=latest_date)


async def get_rates_for_today(
      session: AsyncSession,
      today: date | None = None,
  ) -> list[ExchangeRate]:
      """Cache-aside: вернуть актуальные курсы.

      Критерий «свежести» кеша — момент последнего успешного фетча у ЦБ,
      а не дата курса. Это важно для выходных и праздников: ЦБ в эти дни
      отдаёт курс последнего рабочего дня (rate_date < today), и если бы
      мы сравнивали по rate_date, то каждый запрос в выходной снова бил
      бы в ЦБ. Сравнение по fetched_at эту проблему закрывает —
      мы ходим в ЦБ ровно один раз в календарные сутки.

      Алгоритм:
      1. Если в БД есть хоть одна запись, сделанная сегодня (fetched_at
         сегодня в 00:00 UTC или позже), — отдаём содержимое БД.
      2. Иначе — идём в ЦБ, сохраняем, отдаём.
      3. Если у ЦБ сеть упала — отдаём последний кеш (graceful degradation).
         При совсем пустой БД — пробрасываем ошибку.
      """
      if today is None:
          today = date.today()

      # Граница «сегодня» с явной таймзоной — иначе SQLAlchemy не сравнит
      # naive-datetime с timezone-aware колонкой `fetched_at`.
      today_start = datetime.combine(today, time.min, tzinfo=timezone.utc)
      last_fetch = await session.scalar(select(func.max(ExchangeRate.fetched_at)))

      if last_fetch is not None and last_fetch >= today_start:
          return await _load_latest_rates(session)

      try:
          feed = await fetch_cbr_feed()
      except (httpx.HTTPError, ValueError, ET.ParseError) as exc:
          logger.warning("ЦБ недоступен (%s), отдаём последний кеш", exc)
          fallback = await _load_latest_rates(session)
          if fallback:
              return fallback
          raise

      await _save_rates(session, feed)
      return await _load_latest_rates(session)


async def get_rate_by_code(
      session: AsyncSession,
      char_code: str,
  ) -> ExchangeRate | None:
      """Найти актуальный курс по буквенному коду (USD, EUR, ...).

      char_code регистронезависимый.
      """
      char_code = char_code.upper().strip()
      rates = await get_rates_for_today(session)
      return next((r for r in rates if r.char_code == char_code), None)


__all__ = [
      "CBR_DAILY_URL",
      "ParsedRate",
      "ParsedFeed",
      "parse_cbr_xml",
      "fetch_cbr_feed",
      "get_rates_for_today",
      "get_rate_by_code",
  ]