"""Модель ExchangeRate — курс иностранной валюты к рублю на конкретную дату по данным ЦБ РФ.

  Зачем отдельная таблица, а не «дёрнуть ЦБ при каждом запросе»:
  1. ЦБ РФ публикует курсы раз в сутки — дёргать их на каждый рендер карточки счёта
     бессмысленно и сетево дорого; копия в БД работает мгновенно.
  2. История курсов: чтобы корректно показать, во что обходилась покупка в USD
     полгода назад, нужен курс именно на ту дату, а не сегодняшний.
  3. Доступность: если cbr.ru временно недоступен (или нас режут по сети),
     у нас всё ещё есть последний известный курс — приложение не «слепнет».

  Стратегия наполнения: cache-aside (см. `app/services/cbr_rates.py`). При первом
  обращении за день — фетчим у ЦБ, парсим XML, кладём все валюты разом в эту таблицу.
  """
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class ExchangeRate(Base):
      """Курс одной иностранной валюты к рублю на конкретную дату.

      Одна строка = (char_code, rate_date). Например, USD на 2026-05-09: 74.2963 ₽
      за 1 доллар. Уникальность пары гарантирует UniqueConstraint ниже —
      повторный фетч в тот же день делает UPSERT (или просто пропускается).
      """

      __tablename__ = "exchange_rates"

      id: Mapped[int] = mapped_column(Integer, primary_key=True)

      # Буквенный код валюты по ISO 4217 — 'USD', 'EUR', 'CNY'.
      char_code: Mapped[str] = mapped_column(String(3), nullable=False, index=True)

      # Цифровой код по ISO 4217 — '840' для USD, '978' для EUR.
      # Храним для совместимости со стандартами (в банковских выписках встречается).
      num_code: Mapped[str] = mapped_column(String(3), nullable=False)

      # Человеко-читаемое имя на русском, как его отдаёт ЦБ — 'Доллар США'.
      name: Mapped[str] = mapped_column(String(100), nullable=False)

      # За сколько единиц валюты приводится курс. Для USD это 1, для японской иены — 100.
      nominal: Mapped[int] = mapped_column(Integer, nullable=False)

      # Курс за `nominal` единиц — поле Value из XML ЦБ.
      # Numeric(20, 4) — точное число (не float!), 4 знака после запятой как в XML.
      # Для финансовых сумм float использовать НЕЛЬЗЯ: 0.1 + 0.2 != 0.3 в double.
      value: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)

      # Курс за 1 единицу — поле VunitRate из XML ЦБ. Это `value / nominal`,
      # но ЦБ считает его сам с большей точностью (до 10 знаков для мелких валют
      # типа «вьетнамский донг», у которых Nominal=10000). Храним напрямую,
      # чтобы не терять знаки на копеечных валютах.
      vunit_rate: Mapped[Decimal] = mapped_column(Numeric(20, 10), nullable=False)

      # Дата, на которую ЦБ установил этот курс (атрибут Date в корне XML).
      rate_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

      # Момент, когда мы записали строку в БД. Не равен rate_date: например,
      # курс на пятницу может прийти к нам в воскресенье. Полезно для UI
      # «обновлено N минут назад».
      fetched_at: Mapped[datetime] = mapped_column(
          DateTime(timezone=True),
          server_default=func.now(),
          nullable=False,
      )

      __table_args__ = (
          # Одна валюта × одна дата = одна строка. Защищает от дублей при
          # повторном фетче и используется в UPSERT (ON CONFLICT).
          UniqueConstraint("char_code", "rate_date", name="uq_exchange_rates_code_date"),
      )

      def __repr__(self) -> str:
          return (
              f"<ExchangeRate {self.char_code} on {self.rate_date}: "
              f"{self.value} ₽ / {self.nominal} {self.char_code}>"
          )