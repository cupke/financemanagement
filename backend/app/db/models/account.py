"""Модель Account — счёт пользователя FinTrack.

  Account — это «кошелёк» в широком смысле: банковская карта, наличные,
  электронный кошелёк, накопительный счёт. У одного пользователя может быть
  несколько счетов в разных валютах. Сумма всех счетов — общий капитал
  пользователя в системе.
  """
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
      DateTime,
      ForeignKey,
      Integer,
      Numeric,
      String,
      UniqueConstraint,
  )
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class Account(Base):
      """Счёт пользователя.

      Поле balance хранит текущий баланс в валюте currency_code. На MVP
      он редактируется напрямую (PATCH /accounts/{id}) — это позволяет
      скорректировать значение при первом импорте остатков. Когда появятся
      транзакции, баланс будет пересчитываться автоматически на стороне
      Transaction-сервиса.
      """
      __tablename__ = "accounts"

      id: Mapped[int] = mapped_column(Integer, primary_key=True)

      # Владелец счёта. CASCADE — удалить юзера значит удалить его счета
      # (вместе с привязанными транзакциями). index=True — частые выборки
      # «все счета этого юзера».
      owner_id: Mapped[int] = mapped_column(
          Integer,
          ForeignKey("users.id", ondelete="CASCADE"),
          nullable=False,
          index=True,
      )

      # Название счёта. 100 символов — с запасом для UTF-8 (русские буквы
      # занимают 2 байта каждая, но на длине в символах это не сказывается).
      name: Mapped[str] = mapped_column(String(100), nullable=False)

      # Текущий баланс. Numeric(15, 2) = до 13 цифр перед запятой и 2 после
      # (т.е. до 9 999 999 999 999.99 в выбранной валюте). server_default='0'
      # на случай создания через прямую вставку в БД минуя API.
      balance: Mapped[Decimal] = mapped_column(
          Numeric(15, 2), nullable=False, server_default="0"
      )

      # Код валюты ISO 4217 ("RUB", "USD", "EUR"). Пока строка с дефолтом RUB.
      # На этапе мультивалютности заменим на ForeignKey('currencies.code').
      currency_code: Mapped[str] = mapped_column(
          String(3), nullable=False, server_default="RUB"
      )

      created_at: Mapped[datetime] = mapped_column(
          DateTime(timezone=True),
          server_default=func.now(),
          nullable=False,
      )
      # onupdate=func.now() — SQLAlchemy при UPDATE сам подставит NOW().
      # server_default — для INSERT (БД проставит).
      updated_at: Mapped[datetime] = mapped_column(
          DateTime(timezone=True),
          server_default=func.now(),
          onupdate=func.now(),
          nullable=False,
      )

      # У одного юзера не может быть двух счетов с одинаковым названием.
      # У разных юзеров — может (Иван и Пётр оба могут иметь "Наличные").
      __table_args__ = (
          UniqueConstraint("owner_id", "name", name="uq_accounts_owner_name"),
      )

      def __repr__(self) -> str:
          return (
              f"<Account id={self.id} owner_id={self.owner_id} "
              f"name={self.name!r} balance={self.balance} {self.currency_code}>"
          )